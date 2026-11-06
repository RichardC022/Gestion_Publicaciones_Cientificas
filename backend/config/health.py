"""Public health endpoint used by Docker Compose and monitoring.

``GET /api/health/`` verifies, without exposing sensitive details:

* basic application availability (the view itself responding),
* PostgreSQL answering ``SELECT 1``,
* the media volume accepting a temporary write/read cycle.

A healthy system returns ``200 {"status": "ok"}``. Any failure returns a
generic ``503`` envelope that keeps the request id; the failing component
is logged with the same request id and never disclosed to the client.
"""

from __future__ import annotations

import logging
import os
import tempfile

from django.conf import settings
from django.db import connections
from drf_spectacular.utils import inline_serializer
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from config.exceptions import ErrorCode, build_error_envelope
from config.middleware import get_request_id
from config.openapi import error_response

logger = logging.getLogger(__name__)

GENERIC_UNAVAILABLE_MESSAGE = "El servicio no está disponible temporalmente."


def check_database() -> None:
    """Fail if PostgreSQL cannot execute ``SELECT 1``."""
    with connections["default"].cursor() as cursor:
        cursor.execute("SELECT 1")
        row = cursor.fetchone()
    if row != (1,):
        raise RuntimeError("SELECT 1 returned an unexpected result")


def check_media_volume() -> None:
    """Fail if ``MEDIA_ROOT`` does not accept a temporary write/read cycle."""
    media_root = settings.MEDIA_ROOT
    if not os.path.isdir(media_root):
        raise RuntimeError("MEDIA_ROOT is not available")
    handle = tempfile.NamedTemporaryFile(
        mode="w+b",
        dir=media_root,
        prefix=".health-",
        suffix=".tmp",
        delete=True,
    )
    try:
        payload = b"health-check"
        handle.write(payload)
        handle.flush()
        handle.seek(0)
        if handle.read() != payload:
            raise RuntimeError("media volume verification mismatch")
    finally:
        handle.close()


@extend_schema_view(
    get=extend_schema(
        tags=["Sistema"],
        operation_id="health_retrieve",
        summary="Estado del servicio",
        description=(
            "Público. Comprueba que PostgreSQL responde y que el volumen de medios admite "
            "escritura. También se sirve sin versión en `/api/health/` (lo usan Docker y los "
            "scripts de operación). Ante una falla responde 503 genérico, sin revelar el componente."
        ),
        responses={
            200: inline_serializer(
                "Health", {"status": serializers.CharField(read_only=True, default="ok")}
            ),
            503: error_response("Base de datos o volumen de medios no disponibles."),
        },
        auth=[],
    ),
)
class HealthView(APIView):
    """Public health probe: ``200`` when everything works, ``503`` otherwise."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        request_id = get_request_id(request)
        try:
            check_database()
            check_media_volume()
        except Exception:
            logger.exception("Health check failed [request_id=%s]", request_id)
            error = build_error_envelope(
                ErrorCode.SERVER_ERROR,
                GENERIC_UNAVAILABLE_MESSAGE,
                {},
                request_id,
            )
            return Response(error, status=503)
        return Response({"status": "ok"})


@extend_schema_view(get=extend_schema(exclude=True))
class UnversionedHealthView(HealthView):
    """``GET /api/health/``: el mismo health sin versión, que usan Docker y los scripts.

    Se excluye del schema OpenAPI para no duplicar la operación de ``/api/v1/health/``.
    """
