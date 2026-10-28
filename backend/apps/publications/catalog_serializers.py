"""Public catalog serializers (plan section 2.9, TSK-74).

``PublicCatalogSerializer`` is an allowlist for anonymous visitors: the
article's code, title, authors with their affiliations (never their
e-mail), abstract, keywords, area, language, publication date and the
accepted version. It cannot reach evaluations, reviewers, history,
verdict justifications, audit, the private file name or any internal id.
"""

from __future__ import annotations

from rest_framework import serializers

from apps.publications.models import CatalogEntry, ManuscriptAuthor


class PublicAuthorSerializer(serializers.ModelSerializer):
    """Name and affiliation only: no contact data."""

    class Meta:
        model = ManuscriptAuthor
        fields = ("full_name", "affiliation")
        read_only_fields = fields


class PublicCatalogSerializer(serializers.ModelSerializer):
    """One published article, as any visitor sees it."""

    code = serializers.CharField(source="manuscript.code", read_only=True)
    title = serializers.CharField(source="manuscript.title", read_only=True)
    abstract = serializers.CharField(source="manuscript.abstract", read_only=True)
    keywords = serializers.ListField(source="manuscript.keywords", read_only=True)
    area = serializers.CharField(source="manuscript.area", read_only=True)
    language = serializers.CharField(source="manuscript.language", read_only=True)
    version_number = serializers.IntegerField(source="version.version_number", read_only=True)
    authors = serializers.SerializerMethodField()
    document_url = serializers.SerializerMethodField()

    class Meta:
        model = CatalogEntry
        fields = (
            "code",
            "title",
            "authors",
            "abstract",
            "keywords",
            "area",
            "language",
            "published_at",
            "version_number",
            "document_url",
        )
        read_only_fields = fields

    def get_authors(self, entry: CatalogEntry) -> list[dict]:
        authors = sorted(entry.manuscript.authors.all(), key=lambda a: a.author_order)
        return PublicAuthorSerializer(authors, many=True).data

    def get_document_url(self, entry: CatalogEntry) -> str:
        return f"/api/catalog/{entry.manuscript.code}/document/"
