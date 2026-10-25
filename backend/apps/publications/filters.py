"""Query-string filters of the manuscript list (plan section 2.1).

Common parameters: ``status``, ``area``, ``date_from``, ``date_to``,
``search`` and ``ordering``, plus ``archived`` for the logically
withdrawn manuscripts. A malformed value is a ``400``, never ignored.
"""

from __future__ import annotations

from django.contrib.postgres.search import SearchQuery
from django.db.models import Q, QuerySet
from rest_framework import serializers

from apps.publications.models import Manuscript

ORDERING_FIELDS = ("created_at", "updated_at", "title", "status", "code")
ORDERING_CHOICES = ORDERING_FIELDS + tuple(f"-{field}" for field in ORDERING_FIELDS)
DEFAULT_ORDERING = "-created_at"


class ManuscriptFilterSerializer(serializers.Serializer):
    """Validated filter parameters of ``GET /api/manuscripts/``."""

    status = serializers.ChoiceField(choices=Manuscript.Status.choices, required=False)
    area = serializers.CharField(max_length=120, required=False)
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)
    search = serializers.CharField(max_length=200, required=False, allow_blank=True)
    ordering = serializers.ChoiceField(choices=ORDERING_CHOICES, required=False)
    archived = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs: dict) -> dict:
        date_from, date_to = attrs.get("date_from"), attrs.get("date_to")
        if date_from and date_to and date_from > date_to:
            raise serializers.ValidationError(
                {"date_from": ["date_from no puede ser posterior a date_to."]}
            )
        return attrs


def apply_filters(queryset: QuerySet, query_params) -> QuerySet:
    """Filter and order ``queryset``; invalid parameters raise ``400``."""
    serializer = ManuscriptFilterSerializer(data=query_params)
    serializer.is_valid(raise_exception=True)
    params = serializer.validated_data

    queryset = queryset.filter(is_active=not params["archived"])
    if "status" in params:
        queryset = queryset.filter(status=params["status"])
    if "area" in params:
        queryset = queryset.filter(area__iexact=params["area"])
    if "date_from" in params:
        queryset = queryset.filter(created_at__date__gte=params["date_from"])
    if "date_to" in params:
        queryset = queryset.filter(created_at__date__lte=params["date_to"])
    if params.get("search"):
        term = params["search"]
        queryset = queryset.filter(
            Q(code__icontains=term)
            | Q(search_vector=SearchQuery(term, config="spanish", search_type="websearch"))
        )
    return queryset.order_by(params.get("ordering", DEFAULT_ORDERING), "id")
