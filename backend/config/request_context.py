"""Request metadata shared by the views that write to the audit trail."""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_ipv46_address
from rest_framework.request import Request

from config.middleware import get_request_id

USER_AGENT_MAX_LENGTH = 300


def client_ip(request: Request) -> str | None:
    """Best-effort client IP for the attempt registry and the audit trail.

    Nginx (TSK-04) forwards ``X-Forwarded-For`` and ``X-Real-IP``; the
    first forwarded entry wins. Anything that is not a valid address is
    dropped instead of breaking the request.
    """
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR") or ""
    candidate = forwarded.split(",")[0].strip()
    if not candidate:
        candidate = (request.META.get("HTTP_X_REAL_IP") or "").strip()
    if not candidate:
        candidate = (request.META.get("REMOTE_ADDR") or "").strip()
    if not candidate:
        return None
    try:
        validate_ipv46_address(candidate)
    except DjangoValidationError:
        return None
    return candidate


def audit_request_context(request: Request) -> dict[str, Any]:
    """Request id, IP and user agent, as ``AuditService.record`` expects them."""
    return {
        "request_id": get_request_id(request),
        "ip_address": client_ip(request),
        "user_agent": (request.META.get("HTTP_USER_AGENT") or "")[:USER_AGENT_MAX_LENGTH]
        or None,
    }
