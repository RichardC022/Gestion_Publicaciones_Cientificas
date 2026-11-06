"""Documentación OpenAPI del contrato universal de la API.

drf-spectacular describe lo que cada vista *devuelve*; el contrato
``{success, message, data, errors, meta}`` (``config.renderers``) lo añade el
renderer en tiempo de ejecución. Este módulo hace que el schema diga lo mismo
que la API:

* ``BearerJWTScheme`` documenta la autenticación ``Authorization: Bearer``.
* ``wrap_in_envelope`` es un *postprocessing hook*: envuelve cada respuesta 2xx
  JSON en el sobre de éxito (``data`` conserva el schema original), completa las
  respuestas de error con el sobre de error y añade a cada operación las
  respuestas de error que se deducen de ella (401/403 si requiere sesión, 400 si
  recibe datos, 404 si apunta a un recurso).
* ``PAGINATED`` marca el schema de una página para que el hook declare
  ``meta.pagination``.

Las vistas solo declaran lo propio de cada endpoint con ``@extend_schema``; las
respuestas de error de dominio se declaran con :func:`error_response`.
"""

from __future__ import annotations

from typing import Any

from drf_spectacular.extensions import OpenApiAuthenticationExtension
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse

#: Marca (extensión del schema) que pone el paginador en el schema de una página.
PAGINATED = "x-paginated"

_REF = "#/components/schemas/"

#: Texto por defecto de cada respuesta de error que el hook completa.
_ERROR_DESCRIPTIONS = {
    "400": "Datos inválidos (VALIDATION_ERROR, PDF_INVALID).",
    "401": "Sesión ausente, inválida o expirada (AUTH_INVALID).",
    "403": "El rol o el alcance del usuario no permite la acción (FORBIDDEN).",
    "404": "El recurso no existe o no es visible para este usuario (NOT_FOUND).",
    "409": "La acción no es válida en el estado actual (STATE_CONFLICT y afines).",
    "413": "El archivo supera el límite de 50 MB (PDF_TOO_LARGE).",
    "415": "Tipo de contenido no soportado (PDF_UNSUPPORTED).",
    "429": "Demasiados intentos o solicitudes (RATE_LIMITED, AUTH_LOCKED).",
    "500": "Error interno (SERVER_ERROR); nunca revela detalles internos.",
    "503": "Servicio no disponible temporalmente (STORAGE_UNAVAILABLE, AUDIT_UNAVAILABLE).",
}


#: Cabeceras que comparten varios endpoints de escritura.
IF_MATCH = OpenApiParameter(
    "If-Match",
    location=OpenApiParameter.HEADER,
    required=True,
    description=(
        'ETag vigente del recurso (por ejemplo `"3"`), tomado de la cabecera `ETag` de la '
        "última lectura. Evita sobrescribir cambios ajenos (bloqueo optimista)."
    ),
)
IDEMPOTENCY_KEY = OpenApiParameter(
    "Idempotency-Key",
    location=OpenApiParameter.HEADER,
    required=True,
    description=(
        "Clave elegida por el cliente (1 a 100 caracteres: letras, números, `.` `_` `:` `-`). "
        "Reintentar con la misma clave repite la respuesta guardada, marcada con "
        "`Idempotent-Replayed: true`, y no duplica efectos."
    ),
)


#: Paginación de las listas (``config.pagination.StandardPagination``).
PAGINATION = [
    OpenApiParameter(
        "page",
        int,
        OpenApiParameter.QUERY,
        description="Número de página (desde 1). También acepta `last`.",
    ),
    OpenApiParameter(
        "page_size",
        int,
        OpenApiParameter.QUERY,
        description="Elementos por página: de 1 a 100 (20 por defecto).",
    ),
]


def error_response(description: str) -> OpenApiResponse:
    """Respuesta de error de una vista; el hook añade el sobre de error como cuerpo."""
    return OpenApiResponse(description=description)


class BearerJWTScheme(OpenApiAuthenticationExtension):
    """Documenta ``InstitutionalJWTAuthentication`` como esquema Bearer JWT."""

    target_class = "apps.users.authentication.InstitutionalJWTAuthentication"
    name = "bearerAuth"

    def get_security_definition(self, auto_schema: Any) -> dict[str, Any]:
        return {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": (
                "Token de acceso (15 min) que entrega `POST /auth/login/`. "
                "Envíelo como `Authorization: Bearer <token>`. El de renovación viaja "
                "aparte, en una cookie HttpOnly."
            ),
        }


def _components() -> dict[str, Any]:
    """Esquemas del contrato que el schema referencia."""
    return {
        "ResponseMeta": {
            "type": "object",
            "description": "Metadatos de la respuesta.",
            "properties": {
                "request_id": {
                    "type": "string",
                    "nullable": True,
                    "description": "Identificador de la solicitud (cabecera `X-Request-ID`).",
                },
            },
            "additionalProperties": True,
        },
        "PaginationMeta": {
            "type": "object",
            "description": "Datos de paginación de una lista.",
            "properties": {
                "count": {"type": "integer", "description": "Total de elementos."},
                "next": {"type": "string", "format": "uri", "nullable": True},
                "previous": {"type": "string", "format": "uri", "nullable": True},
            },
            "required": ["count", "next", "previous"],
        },
        "ErrorEntry": {
            "type": "object",
            "description": "Una entrada de `errors`.",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Código del catálogo de errores.",
                    "example": "STATE_CONFLICT",
                },
                "message": {"type": "string"},
                "field": {
                    "type": "string",
                    "nullable": True,
                    "description": "Campo con el error; solo en validación.",
                },
                "details": {"description": "Detalle original (objeto, lista o texto)."},
            },
            "required": ["code", "message", "field", "details"],
        },
        "SuccessEnvelope": {
            "type": "object",
            "description": "Sobre de toda respuesta exitosa. `data` es la carga de cada endpoint.",
            "properties": {
                "success": {"type": "boolean", "enum": [True]},
                "message": {"type": "string", "example": "Operación exitosa."},
                "data": {"description": "Carga del endpoint."},
                "errors": {"type": "array", "maxItems": 0, "items": {}},
                "meta": {"$ref": _REF + "ResponseMeta"},
            },
            "required": ["success", "message", "data", "errors", "meta"],
        },
        "PaginatedSuccessEnvelope": {
            "type": "object",
            "description": "Sobre de una lista paginada: `data` es la lista de la página.",
            "properties": {
                "success": {"type": "boolean", "enum": [True]},
                "message": {"type": "string", "example": "Operación exitosa."},
                "data": {"type": "array", "items": {}},
                "errors": {"type": "array", "maxItems": 0, "items": {}},
                "meta": {
                    "allOf": [{"$ref": _REF + "ResponseMeta"}],
                    "type": "object",
                    "properties": {"pagination": {"$ref": _REF + "PaginationMeta"}},
                    "required": ["pagination"],
                },
            },
            "required": ["success", "message", "data", "errors", "meta"],
        },
        "ErrorEnvelope": {
            "type": "object",
            "description": "Sobre de toda respuesta de error.",
            "properties": {
                "success": {"type": "boolean", "enum": [False]},
                "message": {"type": "string", "example": "Acceso denegado."},
                "data": {"type": "object", "nullable": True, "enum": [None]},
                "errors": {"type": "array", "items": {"$ref": _REF + "ErrorEntry"}},
                "meta": {"$ref": _REF + "ResponseMeta"},
            },
            "required": ["success", "message", "data", "errors", "meta"],
        },
    }


def _error_content() -> dict[str, Any]:
    return {"application/json": {"schema": {"$ref": _REF + "ErrorEnvelope"}}}


def _is_paginated(schema: dict[str, Any], components: dict[str, Any]) -> bool:
    """Indica si ``schema`` es una página: lleva la marca, o referencia un componente que la lleva."""
    if schema.get(PAGINATED):
        return True
    ref = schema.get("$ref", "")
    if ref.startswith(_REF):
        return bool(components.get(ref.removeprefix(_REF), {}).get(PAGINATED))
    return False


def _wrap_success(schema: dict[str, Any], components: dict[str, Any]) -> dict[str, Any]:
    """Envuelve el schema de una carga 2xx en el sobre de éxito."""
    envelope = "PaginatedSuccessEnvelope" if _is_paginated(schema, components) else "SuccessEnvelope"
    schema.pop(PAGINATED, None)
    return {
        "allOf": [
            {"$ref": _REF + envelope},
            {"type": "object", "properties": {"data": schema}},
        ]
    }


def wrap_in_envelope(result: dict[str, Any], generator: Any, request: Any, public: bool) -> dict:
    """Postprocessing hook: aplica el contrato universal al schema generado."""
    components = result.setdefault("components", {}).setdefault("schemas", {})
    components.update(_components())

    for path_item in result.get("paths", {}).values():
        for method, operation in path_item.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            responses = operation.setdefault("responses", {})

            for status, response in list(responses.items()):
                content = response.get("content")
                if str(status).startswith("2"):
                    json_content = (content or {}).get("application/json")
                    if json_content is not None:
                        json_content["schema"] = _wrap_success(
                            json_content.get("schema", {}), components
                        )
                elif not content:
                    response["content"] = _error_content()

            _add_deduced_errors(operation, responses)

    # La marca solo sirve a este hook: no debe quedar en el schema publicado.
    for component in components.values():
        if isinstance(component, dict):
            component.pop(PAGINATED, None)
    return result


def _add_deduced_errors(operation: dict[str, Any], responses: dict[str, Any]) -> None:
    """Añade 401/403/400/404 cuando se deducen de la operación y la vista no los declaró."""
    deduced: list[str] = []
    if operation.get("security"):
        deduced += ["401", "403"]
    parameters = operation.get("parameters", [])
    if operation.get("requestBody") or any(p.get("in") == "query" for p in parameters):
        deduced.append("400")
    if any(p.get("in") == "path" for p in parameters):
        deduced.append("404")
    for status in deduced:
        if status not in responses:
            responses[status] = {
                "description": _ERROR_DESCRIPTIONS[status],
                "content": _error_content(),
            }
    for status, response in responses.items():
        if not response.get("description") and status in _ERROR_DESCRIPTIONS:
            response["description"] = _ERROR_DESCRIPTIONS[status]
