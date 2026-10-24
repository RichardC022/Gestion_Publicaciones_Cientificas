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
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from config.exceptions import ErrorCode, build_error_envelope
from config.middleware import get_request_id

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
