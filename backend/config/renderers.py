"""Renderer del contrato JSON universal de la API.

Toda respuesta JSON de ``/api/v1/`` se entrega con la misma forma::

    {
        "success": true,
        "message": "Operación exitosa.",
        "data": {...},
        "errors": [],
        "meta": {"request_id": "...", "pagination": {...}}
    }

* ``data`` lleva el cuerpo del recurso (o la lista de recursos); es ``null`` en
  los errores.
* ``errors`` es una lista vacía en los éxitos. En los errores contiene entradas
  ``{"code", "message", "field", "details"}`` (ver ``config.exceptions``).
* ``meta`` siempre trae el ``request_id`` de la solicitud; las listas
  paginadas añaden ``pagination`` con ``count``, ``next`` y ``previous``.

Los errores ya llegan envueltos desde ``config.exceptions.exception_handler``;
el renderer solo envuelve los éxitos y deja pasar lo que ya cumple el contrato.
Las descargas de archivos (``HttpResponse`` con ``X-Accel-Redirect``) no pasan
por DRF y por eso no se tocan.
"""

from __future__ import annotations

from typing import Any

from rest_framework.renderers import JSONRenderer

from config.middleware import get_request_id

ENVELOPE_KEYS = frozenset({"success", "message", "data", "errors", "meta"})

_SUCCESS_MESSAGES = {
    200: "Operación exitosa.",
    201: "Recurso creado correctamente.",
    202: "Solicitud aceptada.",
}
_DEFAULT_SUCCESS_MESSAGE = "Operación exitosa."
_PAGE_KEYS = frozenset({"count", "next", "previous", "results"})
_DEFAULT_ERROR_MESSAGE = "La solicitud no pudo completarse."


class PaginatedPayload(dict):
    """Página ya armada por el paginador, marcada para que el renderer la separe.

    Conserva las claves ``count``, ``next``, ``previous`` y ``results`` para que
    el código que lee ``response.data`` dentro del proceso no cambie.
    """


def is_envelope(data: Any) -> bool:
    """Indica si ``data`` ya cumple el contrato universal."""
    return isinstance(data, dict) and ENVELOPE_KEYS <= data.keys()


def build_success_envelope(
    data: Any,
    *,
    message: str = _DEFAULT_SUCCESS_MESSAGE,
    request_id: str | None = None,
    pagination: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the universal envelope of a successful response."""
    meta: dict[str, Any] = {"request_id": request_id}
    if pagination is not None:
        meta["pagination"] = pagination
    return {
        "success": True,
        "message": message,
        "data": data,
        "errors": [],
        "meta": meta,
    }


class EnvelopeJSONRenderer(JSONRenderer):
    """JSON renderer that applies the universal response contract."""

    def render(
        self,
        data: Any,
        accepted_media_type: str | None = None,
        renderer_context: dict[str, Any] | None = None,
    ) -> bytes:
        context = renderer_context or {}
        response = context.get("response")
        status_code = getattr(response, "status_code", 200)

        # 204: por definición no lleva cuerpo, no hay nada que envolver.
        if status_code == 204:
            return b""

        if is_envelope(data):
            return super().render(data, accepted_media_type, renderer_context)

        request_id = get_request_id(context.get("request"))

        if status_code >= 400:
            # Respuesta de error que no pasó por el manejador de excepciones
            # (una vista que devolvió ``Response(..., status=4xx)`` a mano).
            envelope: dict[str, Any] = {
                "success": False,
                "message": _DEFAULT_ERROR_MESSAGE,
                "data": None,
                "errors": [
                    {
                        "code": "VALIDATION_ERROR" if status_code < 500 else "SERVER_ERROR",
                        "message": _DEFAULT_ERROR_MESSAGE,
                        "field": None,
                        "details": data if data is not None else {},
                    }
                ],
                "meta": {"request_id": request_id},
            }
        elif isinstance(data, PaginatedPayload):
            envelope = build_success_envelope(
                data["results"],
                message=_SUCCESS_MESSAGES.get(status_code, _DEFAULT_SUCCESS_MESSAGE),
                request_id=request_id,
                pagination={
                    "count": data["count"],
                    "next": data["next"],
                    "previous": data["previous"],
                },
            )
            # Datos extra que una vista añadió a la página (p. ej. el
            # ``diagnosis`` de revisores elegibles) viajan en ``meta``.
            for key, value in data.items():
                if key not in _PAGE_KEYS:
                    envelope["meta"][key] = value
        else:
            envelope = build_success_envelope(
                data,
                message=_SUCCESS_MESSAGES.get(status_code, _DEFAULT_SUCCESS_MESSAGE),
                request_id=request_id,
            )
        return super().render(envelope, accepted_media_type, renderer_context)
