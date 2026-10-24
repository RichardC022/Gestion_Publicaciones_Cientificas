"""Request ID middleware for end-to-end correlation.

Every request receives an opaque identifier that is:

* echoed back in the ``X-Request-ID`` response header,
* attached to the request object (``request.request_id``) for views,
  services and the audit trail (``AuditService`` consumes it in TSK-18),
* exposed to log formatters through :class:`RequestIDLogFilter`.

Client supplied identifiers are accepted only when they match a strict
character set and length, so a request id can never carry personal data
or log-injection payloads. Anything else is replaced by a generated id.
"""

from __future__ import annotations

import logging
import re
import uuid
from contextvars import ContextVar
from typing import Any, Callable

logger = logging.getLogger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"
REQUEST_ID_MAX_LENGTH = 64
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9@._~-]{1,64}$")

_current_request_id: ContextVar[str | None] = ContextVar(
    "gpc_current_request_id", default=None
)


def new_request_id() -> str:
    """Return a fresh opaque request identifier."""
    return uuid.uuid4().hex


def sanitize_request_id(value: Any) -> str | None:
    """Return ``value`` only when it is a safe opaque identifier."""
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if len(candidate) > REQUEST_ID_MAX_LENGTH:
        return None
    if _REQUEST_ID_PATTERN.fullmatch(candidate) is None:
        return None
    return candidate


def current_request_id() -> str | None:
    """Return the identifier of the request being served, if any."""
    return _current_request_id.get()


def get_request_id(request: Any) -> str | None:
    """Return the identifier attached to ``request`` by the middleware."""
    return getattr(request, "request_id", None)


class RequestIdMiddleware:
    """Assign a correlation identifier to every request/response cycle."""

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
    """Attach the active request identifier to every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = current_request_id() or "-"
        return True
