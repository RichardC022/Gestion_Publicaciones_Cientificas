"""Standard error envelope and DRF exception handling.

Every API error response uses the universal contract shared with the
successful responses (see ``config.renderers``)::

    {
        "success": false,
        "message": "La acción no es válida en el estado actual.",
        "data": null,
        "errors": [
            {
                "code": "STATE_CONFLICT",
                "message": "La acción no es válida en el estado actual.",
                "field": null,
                "details": {}
            }
        ],
        "meta": {"request_id": "..."}
    }

``ErrorCode`` holds the catalog from the plan (section 2.10) and
``DomainError`` is the base class for domain errors: raising it with a
catalog code renders through the envelope and keeps the request id of
the request that triggered it. ``exception_handler`` is registered in
``REST_FRAMEWORK["EXCEPTION_HANDLER"]``.

Invalid query parameters (for example malformed filter or pagination
values) must surface as ``ValidationError`` so the envelope renders them
with HTTP ``400``.
"""

from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404
from rest_framework import exceptions
from rest_framework.response import Response

from config.middleware import get_request_id, new_request_id

logger = logging.getLogger("config.exceptions")

_VALIDATION_MESSAGE = "Los datos enviados no son válidos."
_SERVER_ERROR_MESSAGE = "Error interno del servidor."


class ErrorCode:
    """Error codes of the domain catalog (implementation plan, section 2.10)."""

    AUTH_INVALID = "AUTH_INVALID"
    AUTH_LOCKED = "AUTH_LOCKED"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    STATE_CONFLICT = "STATE_CONFLICT"
    VERSION_CONFLICT = "VERSION_CONFLICT"
    ASSIGNMENT_CONFLICT = "ASSIGNMENT_CONFLICT"
    VERDICT_CONFLICT = "VERDICT_CONFLICT"
    CORRECTION_NOT_AUTHORIZED = "CORRECTION_NOT_AUTHORIZED"
    PDF_INVALID = "PDF_INVALID"
    PDF_TOO_LARGE = "PDF_TOO_LARGE"
    PDF_UNSUPPORTED = "PDF_UNSUPPORTED"
    STORAGE_UNAVAILABLE = "STORAGE_UNAVAILABLE"
    AUDIT_UNAVAILABLE = "AUDIT_UNAVAILABLE"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    RATE_LIMITED = "RATE_LIMITED"
    # Fallback for unclassified errors; it never carries internal details.
    SERVER_ERROR = "SERVER_ERROR"


_STATUS_BY_CODE = {
    ErrorCode.AUTH_INVALID: 401,
    ErrorCode.AUTH_LOCKED: 429,
    ErrorCode.FORBIDDEN: 403,
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.STATE_CONFLICT: 409,
    ErrorCode.VERSION_CONFLICT: 409,
    ErrorCode.ASSIGNMENT_CONFLICT: 409,
    ErrorCode.VERDICT_CONFLICT: 409,
    ErrorCode.CORRECTION_NOT_AUTHORIZED: 409,
    ErrorCode.PDF_INVALID: 400,
    ErrorCode.PDF_TOO_LARGE: 413,
    ErrorCode.PDF_UNSUPPORTED: 415,
    ErrorCode.STORAGE_UNAVAILABLE: 503,
    ErrorCode.AUDIT_UNAVAILABLE: 503,
    ErrorCode.VALIDATION_ERROR: 400,
    ErrorCode.RATE_LIMITED: 429,
    ErrorCode.SERVER_ERROR: 500,
}


class DomainError(exceptions.APIException):
    """Domain error with an explicit envelope code.

    Example::

        raise DomainError(
            "La acción no es válida en el estado actual.",
            code=ErrorCode.STATE_CONFLICT,
            details={"status": manuscript.status},
        )

    ``headers`` adds explicit response headers — for example the
    ``Retry-After`` of a ``429`` lockout (TSK-20).
    """

    status_code = 400

    def __init__(
        self,
        message: str,
        *,
        code: str = ErrorCode.VALIDATION_ERROR,
        details: Any = None,
        status_code: int | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.error_code = code
        self.error_details = {} if details is None else details
        if status_code is None:
            status_code = _STATUS_BY_CODE.get(code, 400)
        self.status_code = status_code
        self.headers = dict(headers) if headers else None
        super().__init__(message)


_TYPED_ERRORS: tuple[tuple[type[exceptions.APIException], str, str], ...] = (
    (exceptions.ValidationError, ErrorCode.VALIDATION_ERROR, _VALIDATION_MESSAGE),
    (
        exceptions.AuthenticationFailed,
        ErrorCode.AUTH_INVALID,
        "Credenciales de autenticación inválidas.",
    ),
    (exceptions.NotAuthenticated, ErrorCode.AUTH_INVALID, "No autenticado."),
    (exceptions.PermissionDenied, ErrorCode.FORBIDDEN, "Acceso denegado."),
    (exceptions.NotFound, ErrorCode.NOT_FOUND, "No encontrado."),
    (exceptions.ParseError, ErrorCode.VALIDATION_ERROR, "La solicitud está mal formada."),
    (
        exceptions.MethodNotAllowed,
        ErrorCode.VALIDATION_ERROR,
        "Método no permitido para este recurso.",
    ),
    (
        exceptions.NotAcceptable,
        ErrorCode.VALIDATION_ERROR,
        "La solicitud no puede atenderse con el formato pedido.",
    ),
    (
        exceptions.UnsupportedMediaType,
        ErrorCode.PDF_UNSUPPORTED,
        "Tipo de contenido no soportado.",
    ),
    (exceptions.Throttled, ErrorCode.RATE_LIMITED, "Demasiadas solicitudes."),
)


def _first_message(detail: Any) -> str:
    """Return the first human-readable string found in a DRF error detail."""
    if isinstance(detail, str):
        return detail
    if isinstance(detail, dict):
        for value in detail.values():
            found = _first_message(value)
            if found:
                return found
    if isinstance(detail, (list, tuple)):
        for value in detail:
            found = _first_message(value)
            if found:
                return found
    return ""


def _build_errors(code: str, message: str, details: Any) -> list[dict[str, Any]]:
    """Build the ``errors`` list of the universal contract.

    Each entry is ``{"code", "message", "field", "details"}``:

    * a validation error keyed by field yields one entry per top-level field,
      with ``details`` holding that field's original (possibly nested) detail,
      so a client can rebuild ``{field: details}`` without loss;
    * any other error yields a single entry carrying the original ``details``.
    """
    if code == ErrorCode.VALIDATION_ERROR and isinstance(details, dict) and details:
        return [
            {
                "code": code,
                "message": _first_message(value) or message,
                "field": str(field),
                "details": value,
            }
            for field, value in details.items()
        ]
    return [{"code": code, "message": message, "field": None, "details": details}]


def build_error_envelope(
    code: str, message: str, details: Any, request_id: str | None
) -> dict[str, Any]:
    """Return the universal envelope of an error response."""
    return {
        "success": False,
        "message": message,
        "data": None,
        "errors": _build_errors(code, message, details),
        "meta": {"request_id": request_id},
    }


def _message_or_default(exc: exceptions.APIException, default: str) -> str:
    """Keep a custom message, or use the Spanish default."""
    detail = getattr(exc, "detail", None)
    default_detail = getattr(type(exc), "default_detail", None)
    if isinstance(detail, str) and detail and detail != default_detail:
        return str(detail)
    return default


def _describe(exc: BaseException) -> tuple[str, str, Any]:
    """Map ``exc`` to the envelope ``(code, message, details)``."""
    if isinstance(exc, DomainError):
        return exc.error_code, str(exc.detail), exc.error_details

    if isinstance(exc, Http404):
        return ErrorCode.NOT_FOUND, "No encontrado.", {}
    if isinstance(exc, DjangoPermissionDenied):
        return ErrorCode.FORBIDDEN, "Acceso denegado.", {}

    if isinstance(exc, exceptions.ValidationError):
        detail = exc.detail
        if isinstance(detail, str):
            return ErrorCode.VALIDATION_ERROR, str(detail), {}
        return ErrorCode.VALIDATION_ERROR, _VALIDATION_MESSAGE, detail

    for exc_type, code, default_message in _TYPED_ERRORS:
        if isinstance(exc, exc_type):
            details: Any = {}
            if isinstance(exc, exceptions.UnsupportedMediaType):
                media_type = getattr(exc, "media_type", None)
                if media_type:
                    details = {"media_type": media_type}
            return code, _message_or_default(exc, default_message), details

    status_code = getattr(exc, "status_code", None)
    if isinstance(status_code, int):
        if status_code == 409:
            return (
                ErrorCode.STATE_CONFLICT,
                _message_or_default(exc, "Conflicto de estado."),
                {},
            )
        if status_code == 413:
            return (
                ErrorCode.PDF_TOO_LARGE,
                _message_or_default(exc, "El archivo supera el límite de 50 MB."),
                {},
            )
        if status_code == 429:
            return (
                ErrorCode.RATE_LIMITED,
                _message_or_default(exc, "Demasiadas solicitudes."),
                {},
            )
        if 400 <= status_code < 500:
            return (
                ErrorCode.VALIDATION_ERROR,
                _message_or_default(exc, "La solicitud no es válida."),
                {},
            )
    return ErrorCode.SERVER_ERROR, _SERVER_ERROR_MESSAGE, {}


def exception_handler(exc: BaseException, context: dict[str, Any]) -> Any:
    """Render every API error through the standard envelope.

    Unhandled exceptions are logged with the request id for correlation
    and, outside DEBUG mode, answered with a generic ``500`` envelope
    that never leaks internal details.
    """
    # Importación perezosa: rest_framework.views importa api_settings al
    # inicializarse y esta función se referencia desde REST_FRAMEWORK, así
    # que una importación de módulo crearía un ciclo con las clases de
    # autenticación resueltas por settings.
    from rest_framework.views import exception_handler as drf_exception_handler
    from rest_framework.views import set_rollback

    request = context.get("request")
    request_id = get_request_id(request) or new_request_id()

    response = drf_exception_handler(exc, context)
    if response is None:
        # Unhandled exception. Under DEBUG let Django show the traceback.
        if settings.DEBUG:
            return None
        logger.exception("Error interno no manejado [request_id=%s]", request_id)
        set_rollback()
        response = Response(status=500)

    code, message, details = _describe(exc)
    response.data = build_error_envelope(code, message, details, request_id)

    # Cabeceras explícitas del error de dominio (p. ej. Retry-After en 429).
    extra_headers = getattr(exc, "headers", None)
    if extra_headers:
        for header, value in extra_headers.items():
            response[header] = value
    return response


def _is_api_path(request: Any) -> bool:
    return str(getattr(request, "path", "")).startswith("/api/")


def not_found_handler(request: Any, exception: Exception | None = None) -> Any:
    """``handler404``: JSON con el contrato universal para rutas ``/api/``."""
    from django.http import JsonResponse
    from django.views.defaults import page_not_found

    if not _is_api_path(request):
        return page_not_found(request, exception)
    request_id = get_request_id(request) or new_request_id()
    envelope = build_error_envelope(ErrorCode.NOT_FOUND, "No encontrado.", {}, request_id)
    response = JsonResponse(envelope, status=404)
    response["X-Request-ID"] = request_id
    return response


def server_error_handler(request: Any) -> Any:
    """``handler500``: JSON genérico con el contrato universal para ``/api/``."""
    from django.http import JsonResponse
    from django.views.defaults import server_error

    if not _is_api_path(request):
        return server_error(request)
    request_id = get_request_id(request) or new_request_id()
    envelope = build_error_envelope(ErrorCode.SERVER_ERROR, _SERVER_ERROR_MESSAGE, {}, request_id)
    response = JsonResponse(envelope, status=500)
    response["X-Request-ID"] = request_id
    return response
