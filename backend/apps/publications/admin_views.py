"""Administrator endpoint of the verdict correction (plan section 2.7, TSK-77).

``POST /api/admin/verdicts/{id}/authorize-correction/`` is the only write
of the administrator role (CA-HU-13-12). It needs the active ``ADMIN``
role, ``Idempotency-Key`` and a ``reason`` of 10 to 1000 characters. The
answer carries the manuscript's public code, the decision and the dates:
no authors, evaluations, comments or PDF.
"""

from __future__ import annotations

import json

from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import JSONRenderer
from rest_framework.request import Request
from rest_framework.response import Response

from apps.publications.models import Verdict, VerdictCorrection
from apps.publications.services.corrections import authorize_correction
from apps.publications.services.idempotency import IdempotencyScope, IdempotentReplay, request_hash
from apps.publications.views import parse_idempotency_key, replayed
from apps.users.permissions import IsAdmin
from config.request_context import audit_request_context

REASON_MIN, REASON_MAX = 10, 1000


class AuthorizeCorrectionSerializer(serializers.Serializer):
    """Body: the administrator's reason, 10 to 1000 characters once trimmed."""

    reason = serializers.CharField(
        min_length=REASON_MIN,
        max_length=REASON_MAX,
        trim_whitespace=True,
        error_messages={
            "required": "Indique el motivo de la habilitación.",
            "blank": "Indique el motivo de la habilitación.",
            "min_length": f"El motivo debe tener al menos {REASON_MIN} caracteres.",
            "max_length": f"El motivo no puede superar {REASON_MAX} caracteres.",
        },
    )


def render_correction(correction: VerdictCorrection) -> tuple[int, dict]:
    """``(status, body)`` of a created authorization; the body is what gets stored."""
    data = {
        "id": str(correction.pk),
        "verdict_id": str(correction.original_verdict_id),
        "manuscript_code": correction.manuscript.code,
        "decision": correction.original_verdict.decision,
        "decided_at": correction.original_verdict.created_at,
        "reason": correction.reason,
        "authorized_at": correction.authorized_at,
        "is_active": correction.is_active,
    }
    return status.HTTP_201_CREATED, json.loads(JSONRenderer().render(data))


class AuthorizeCorrectionView(GenericAPIView):
    permission_classes = [IsAuthenticated, IsAdmin]
    serializer_class = AuthorizeCorrectionSerializer

    def post(self, request: Request, pk) -> Response:
        verdict = get_object_or_404(Verdict, pk=pk)
        body = AuthorizeCorrectionSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        reason = body.validated_data["reason"]
        key = parse_idempotency_key(request)

        scope = IdempotencyScope(
            user=request.user,
            endpoint=f"{request.method} {request.path}",
            key=key,
            request_hash=lambda: request_hash(str(verdict.pk), reason),
            render=render_correction,
        )
        if (stored := scope.find()) is not None:
            return replayed(stored)
        try:
            correction = authorize_correction(
                verdict_id=verdict.pk,
                admin=request.user,
                reason=reason,
                context=audit_request_context(request),
                idempotency=scope,
            )
        except IdempotentReplay as replay:
            return replayed(replay.stored)
        status_code, response_body = render_correction(correction)
        return Response(response_body, status=status_code)
