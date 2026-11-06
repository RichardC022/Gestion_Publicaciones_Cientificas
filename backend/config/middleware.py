"""Middleware del identificador de solicitud, para correlacionar de extremo a extremo.

Cada solicitud recibe un identificador opaco que:

* se devuelve en la cabecera de respuesta ``X-Request-ID``,
* se adjunta al objeto de la solicitud (``request.request_id``) para que lo usen
  las vistas, los servicios y la auditoría (``AuditService``),
* se expone a los formateadores de log mediante :class:`RequestIDLogFilter`.

Un identificador enviado por el cliente solo se acepta si cumple un conjunto de
caracteres y una longitud estrictos; así un ``request_id`` nunca puede transportar
datos personales ni intentos de inyección en el log. Cualquier otro valor se
reemplaza por uno generado.
"""

from __future__ import annotations

import logging
import re
import uuid
from contextvars import ContextVar
from typing import Any, Callable

logger = logging.getLogger(__name__)

# Cabecera por la que viaja el identificador, en la solicitud y en la respuesta.
REQUEST_ID_HEADER = "X-Request-ID"
# Longitud máxima aceptada para un identificador enviado por el cliente.
REQUEST_ID_MAX_LENGTH = 64
# Letras, dígitos y @ . _ ~ - (sin espacios, saltos de línea ni otros símbolos).
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9@._~-]{1,64}$")

# Identificador de la solicitud en curso. Una variable de contexto (y no un atributo global)
# mantiene el valor correcto aunque se atiendan solicitudes concurrentes.
_current_request_id: ContextVar[str | None] = ContextVar(
    "gpc_current_request_id", default=None
)


def new_request_id() -> str:
    """Devuelve un identificador de solicitud nuevo y opaco (un UUID4 en hexadecimal)."""
    return uuid.uuid4().hex


def sanitize_request_id(value: Any) -> str | None:
    """Devuelve ``value`` solo si es un identificador opaco seguro; si no, ``None``.

    Seguro significa un texto de 1 a 64 caracteres entre letras, dígitos y
    ``@ . _ ~ -``, una vez quitados los espacios de los extremos.
    """
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if len(candidate) > REQUEST_ID_MAX_LENGTH:
        return None
    if _REQUEST_ID_PATTERN.fullmatch(candidate) is None:
        return None
    return candidate


def current_request_id() -> str | None:
    """Devuelve el identificador de la solicitud que se atiende, o ``None`` fuera de una."""
    return _current_request_id.get()


def get_request_id(request: Any) -> str | None:
    """Devuelve el identificador que el middleware adjuntó a ``request`` (``None`` si no pasó por él)."""
    return getattr(request, "request_id", None)


class RequestIdMiddleware:
    """Asigna un identificador de correlación a cada ciclo solicitud/respuesta.

    Usa el de la cabecera ``X-Request-ID`` si es seguro; si no, genera uno. Lo deja en
    ``request.request_id`` y en una variable de contexto (para el log) mientras dura la
    solicitud, y lo devuelve en la cabecera de la respuesta.
    """

    def __init__(self, get_response: Callable) -> None:
        self.get_response = get_response

    def __call__(self, request: Any) -> Any:
        incoming = request.headers.get(REQUEST_ID_HEADER)
        request_id = sanitize_request_id(incoming) or new_request_id()
        request.request_id = request_id
        token = _current_request_id.set(request_id)
        try:
            response = self.get_response(request)
        finally:
            _current_request_id.reset(token)
        response[REQUEST_ID_HEADER] = request_id
        return response


class RequestIDLogFilter(logging.Filter):
    """Añade a cada registro de log el identificador de la solicitud activa.

    Fuera de una solicitud (por ejemplo, en un comando de gestión) usa ``-``.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = current_request_id() or "-"
        return True
