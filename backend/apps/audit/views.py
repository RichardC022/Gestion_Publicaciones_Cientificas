"""Administrator audit endpoints (plan section 2.7, TSK-73).

``GET /api/admin/audit/`` and ``GET /api/admin/audit/{id}/`` need the
active ``ADMIN`` role (``403`` otherwise). Reading the audit trail is
itself audited, inside the same transaction as the read: if the query
event cannot be written the answer is ``503`` and nothing is returned
(fail closed, like every audited action).

The role never reaches manuscripts, evaluations or PDFs: the only
manuscript data here is the public code.
"""

from __future__ import annotations

from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from apps.audit.filters import apply_filters, audited_filters, validated_filters
from apps.audit.models import AuditLog
from apps.audit.serializers import AdminAuditDetailSerializer, AdminAuditSerializer, manuscript_id_of
from apps.audit.services import AuditService, AuditUnavailable
from apps.publications.models import Manuscript
from apps.users.models import Role
from apps.users.permissions import IsAdmin
from config.exceptions import DomainError, ErrorCode
from config.request_context import audit_request_context

AUDIT_ENTITY = "AUDIT_LOG"
AUDIT_UNAVAILABLE_MESSAGE = (
    "No se pudo registrar la consulta de auditoría; inténtelo de nuevo."
)


class AdminAuditBaseView(GenericAPIView):
    """Shared permissions, serializer context and self-auditing."""

    permission_classes = [IsAuthenticated, IsAdmin]
    serializer_class = AdminAuditSerializer

    def audit_read(self, action: str, *, entity_id=None, details: dict | None = None) -> None:
        """Record this query in the audit trail; ``503`` if it cannot be written."""
        try:
            AuditService.record(
                action=action,
                entity_type=AUDIT_ENTITY,
                entity_id=entity_id,
                result=AuditLog.Result.SUCCESS,
                actor=self.request.user,
                actor_role=Role.Code.ADMIN,
                details=details or {},
                **audit_request_context(self.request),
            )
        except AuditUnavailable as exc:
            raise DomainError(
                AUDIT_UNAVAILABLE_MESSAGE, code=ErrorCode.AUDIT_UNAVAILABLE
            ) from exc

    @staticmethod
    def manuscript_codes(entries) -> dict[str, str]:
        """``id -> code`` of the manuscripts the events mention (the code only)."""
        ids = {manuscript_id_of(entry) for entry in entries} - {None}
        return {
            str(pk): code
            for pk, code in Manuscript.objects.filter(pk__in=ids).values_list("pk", "code")
        }


class AuditListView(AdminAuditBaseView):
    """``GET /api/admin/audit/``: global, paginated, newest first."""

    def get(self, request: Request) -> Response:
        params = validated_filters(request.query_params)
        queryset = apply_filters(AuditLog.objects.all(), params).order_by("-occurred_at", "-id")
        with transaction.atomic():
            page = self.paginate_queryset(queryset)
            self.audit_read(
                "AUDIT_QUERIED",
                details={
                    "filters": audited_filters(params),
                    "page": int(request.query_params.get("page") or 1),
                    "returned": len(page),
                },
            )
        data = AdminAuditSerializer(
            page, many=True, context={"manuscript_codes": self.manuscript_codes(page)}
        ).data
        return self.get_paginated_response(data)


class AuditDetailView(AdminAuditBaseView):
    """``GET /api/admin/audit/{id}/``: one event, by its public ``event_id``."""

    def get(self, request: Request, pk) -> Response:
        entry = get_object_or_404(AuditLog, event_id=pk)
        with transaction.atomic():
            self.audit_read("AUDIT_DETAIL_VIEWED", entity_id=entry.event_id)
        data = AdminAuditDetailSerializer(
            entry, context={"manuscript_codes": self.manuscript_codes([entry])}
        ).data
        return Response(data)
