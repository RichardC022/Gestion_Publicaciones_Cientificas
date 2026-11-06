"""Metadatos de la solicitud que comparten las vistas que escriben en la auditoría."""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_ipv46_address
from rest_framework.request import Request

from config.middleware import get_request_id

# Longitud máxima del agente de usuario que se guarda en la auditoría.
USER_AGENT_MAX_LENGTH = 300


def client_ip(request: Request) -> str | None:
    """IP del cliente (en el mejor esfuerzo) para el registro de intentos y la auditoría.

    Se prueba, en orden, ``X-Forwarded-For`` (manda su primera entrada), ``X-Real-IP`` y
    ``REMOTE_ADDR``. Lo que no sea una dirección IPv4 o IPv6 válida se descarta
    (devuelve ``None``) en lugar de romper la solicitud.

    Limitación conocida: Nginx usa ``$proxy_add_x_forwarded_for``, que **añade** la IP real
    al final de lo que el cliente ya haya enviado; por eso la primera entrada puede ser
    falsificada por quien llame a la API. La IP es un dato informativo de la auditoría: el
    bloqueo por intentos fallidos se hace por identificador, no por IP.
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
    """Identificador de solicitud, IP y agente de usuario, como los espera ``AuditService.record``.

    El agente de usuario se recorta a :data:`USER_AGENT_MAX_LENGTH` caracteres y queda en
    ``None`` si viene vacío.
    """
    return {
        "request_id": get_request_id(request),
        "ip_address": client_ip(request),
        "user_agent": (request.META.get("HTTP_USER_AGENT") or "")[:USER_AGENT_MAX_LENGTH]
        or None,
    }
