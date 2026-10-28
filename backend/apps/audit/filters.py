"""Query-string filters of the administrator audit list (TSK-73).

Parameters: ``date_from``, ``date_to`` (``YYYY-MM-DD``, inclusive, in the
institutional time zone), ``actor`` (user id), ``action``, ``manuscript``
(manuscript id) and ``result``. A malformed value is a ``400``.
"""

from __future__ import annotations

from django.db.models import Q, QuerySet
from rest_framework import serializers

from apps.audit.models import AuditLog
from apps.audit.serializers import MANUSCRIPT_ENTITY


class AuditFilterSerializer(serializers.Serializer):
    """Validated filter parameters of ``GET /api/admin/audit/``."""

    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)
    actor = serializers.UUIDField(required=False)
    action = serializers.RegexField(r"^[A-Z0-9_]{1,64}$", required=False)
    manuscript = serializers.UUIDField(required=False)
    result = serializers.ChoiceField(choices=AuditLog.Result.choices, required=False)

    def validate(self, attrs: dict) -> dict:
        date_from, date_to = attrs.get("date_from"), attrs.get("date_to")
        if date_from and date_to and date_from > date_to:
            raise serializers.ValidationError(
                {"date_from": ["date_from no puede ser posterior a date_to."]}
            )
        return attrs


def validated_filters(query_params) -> dict:
    """The validated filters; invalid parameters raise ``400``."""
    serializer = AuditFilterSerializer(data=query_params)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


def apply_filters(queryset: QuerySet, params: dict) -> QuerySet:
    """Narrow the audit queryset with already validated ``params``."""
    if "date_from" in params:
        queryset = queryset.filter(occurred_at__date__gte=params["date_from"])
    if "date_to" in params:
        queryset = queryset.filter(occurred_at__date__lte=params["date_to"])
    if "actor" in params:
        queryset = queryset.filter(actor_id=params["actor"])
    if "action" in params:
        queryset = queryset.filter(action=params["action"])
    if "result" in params:
        queryset = queryset.filter(result=params["result"])
    if "manuscript" in params:
        manuscript = params["manuscript"]
        queryset = queryset.filter(
            Q(entity_type=MANUSCRIPT_ENTITY, entity_id=manuscript)
            | Q(details__manuscript_id=str(manuscript))
        )
    return queryset


def audited_filters(params: dict) -> dict[str, str]:
    """The filters as plain strings, for the ``details`` of the query event."""
    return {key: str(value) for key, value in params.items()}
