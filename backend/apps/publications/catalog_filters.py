"""Query-string filters of the public catalog (plan section 2.6, TSK-74).

``search`` covers title, authors, keywords, area, abstract and code;
``area``, ``language``, ``keyword``, ``date_from`` and ``date_to`` (the
publication date) narrow the list; ``ordering`` is ``published_at`` or
``title``, with a leading ``-`` for descending. A malformed value is a
``400``, never ignored.
"""

from __future__ import annotations

from rest_framework import serializers

from apps.publications.services.catalog import ORDERING_FIELDS

ORDERING_CHOICES = tuple(ORDERING_FIELDS) + tuple(f"-{field}" for field in ORDERING_FIELDS)


class CatalogFilterSerializer(serializers.Serializer):
    """Validated filter parameters of ``GET /api/catalog/``."""

    search = serializers.CharField(max_length=200, required=False, allow_blank=True)
    area = serializers.CharField(max_length=120, required=False)
    language = serializers.RegexField(r"^[a-z]{2}$", required=False)
    keyword = serializers.CharField(max_length=100, required=False)
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)
    ordering = serializers.ChoiceField(choices=ORDERING_CHOICES, required=False)

    def validate(self, attrs: dict) -> dict:
        date_from, date_to = attrs.get("date_from"), attrs.get("date_to")
        if date_from and date_to and date_from > date_to:
            raise serializers.ValidationError(
                {"date_from": ["date_from no puede ser posterior a date_to."]}
            )
        if not attrs.get("search"):
            attrs.pop("search", None)
        return attrs


def validated_filters(query_params) -> dict:
    """The validated filters; invalid parameters raise ``400``."""
    serializer = CatalogFilterSerializer(data=query_params)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data
