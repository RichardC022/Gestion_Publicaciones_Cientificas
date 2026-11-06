"""Sobre estándar de error y manejo de excepciones de DRF.

Toda respuesta de error de la API usa el mismo contrato universal que las respuestas
exitosas (ver ``config.renderers``)::

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

``ErrorCode`` guarda el catálogo de códigos del plan (sección 2.10) y ``DomainError`` es la
clase base de los errores de dominio: lanzarla con un código del catálogo la presenta con el
sobre y conserva el identificador de la solicitud que la provocó. ``exception_handler`` está
registrado en ``REST_FRAMEWORK["EXCEPTION_HANDLER"]``.

Los parámetros de consulta inválidos (por ejemplo, filtros o paginación mal formados) deben
salir como ``ValidationError`` para que el sobre los presente con HTTP ``400``.
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

# Mensajes genéricos en español, para los errores que no traen uno propio.
_VALIDATION_MESSAGE = "Los datos enviados no son válidos."
_SERVER_ERROR_MESSAGE = "Error interno del servidor."


class ErrorCode:
    """Códigos de error del catálogo de dominio (plan de implementación, sección 2.10).

    Son el identificador estable que ven los clientes en ``errors[].code``: el texto del
    mensaje puede cambiar, el código no.
    """

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
    # Respaldo para errores sin clasificar; nunca lleva detalles internos.
    SERVER_ERROR = "SERVER_ERROR"


# Estado HTTP que corresponde a cada código del catálogo. Un código que no esté aquí
# responde 400 (ver ``DomainError``).
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
    """Error de dominio con un código explícito del catálogo.

    Ejemplo::

        raise DomainError(
            "La acción no es válida en el estado actual.",
            code=ErrorCode.STATE_CONFLICT,
            details={"status": manuscript.status},
        )

    El estado HTTP sale del código (``_STATUS_BY_CODE``) salvo que se pase ``status_code``.
    ``details`` viaja tal cual en ``errors[].details``. ``headers`` añade cabeceras a la
    respuesta; por ejemplo, el ``Retry-After`` de un bloqueo ``429``.
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


# Excepciones de DRF y su equivalente en el catálogo: (tipo, código, mensaje por defecto).
# Se recorre en orden y gana la primera coincidencia.
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
    """Devuelve el primer texto legible que haya en el detalle de un error de DRF.

    El detalle puede ser un texto, una lista o un diccionario anidado; si no hay ninguno,
    devuelve una cadena vacía.
    """
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
    """Arma la lista ``errors`` del contrato universal.

    Cada entrada es ``{"code", "message", "field", "details"}``:

    * un error de validación por campo genera una entrada por cada campo de primer nivel,
      con ``details`` igual al detalle original de ese campo (posiblemente anidado), de modo
      que el cliente pueda reconstruir ``{campo: detalle}`` sin pérdida;
    * cualquier otro error genera una sola entrada con el ``details`` original.
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
    """Devuelve el sobre universal de una respuesta de error.

    ``success`` es ``False``, ``data`` es ``None`` y ``meta`` lleva el ``request_id``.
    """
    return {
        "success": False,
        "message": message,
        "data": None,
        "errors": _build_errors(code, message, details),
        "meta": {"request_id": request_id},
    }


def _message_or_default(exc: exceptions.APIException, default: str) -> str:
    """Conserva el mensaje propio de la excepción o, si es el genérico de DRF, usa el de por defecto en español."""
    detail = getattr(exc, "detail", None)
    default_detail = getattr(type(exc), "default_detail", None)
    if isinstance(detail, str) and detail and detail != default_detail:
        return str(detail)
    return default


def _describe(exc: BaseException) -> tuple[str, str, Any]:
    """Traduce una excepción a ``(código, mensaje, detalles)`` del sobre de error.

    El orden de las comprobaciones importa; gana la primera que coincida:

    1. ``DomainError``: usa su código, mensaje y detalles tal cual.
    2. ``Http404`` y ``PermissionDenied`` de Django.
    3. ``ValidationError`` de DRF (texto suelto o detalle por campo).
    4. La tabla ``_TYPED_ERRORS`` de excepciones de DRF.
    5. Cualquier otra con ``status_code``: 409, 413 y 429 tienen código propio; el resto de
       los 4xx es ``VALIDATION_ERROR``.
    6. Todo lo demás es ``SERVER_ERROR``, sin detalles internos.
    """
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
    """Presenta todo error de la API con el sobre estándar.

    Las excepciones no controladas se registran en el log con el identificador de la solicitud
    (para poder correlacionarlas) y, fuera de ``DEBUG``, se responden con un ``500`` genérico
    que nunca filtra detalles internos. Con ``DEBUG`` activo se devuelve ``None`` y Django
    muestra la traza.
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
        # Excepción no controlada. Con DEBUG, Django debe mostrar la traza.
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
    """Indica si la ruta pertenece a la API (empieza por ``/api/``)."""
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
