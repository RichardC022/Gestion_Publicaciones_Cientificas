"""Public catalog endpoints (plan sections 2.6 and 4.7, TSK-74).

Anonymous and read-only. The views authenticate nobody (a stale or wrong
token must not turn a public page into a ``401``) and start ONLY from
:func:`~apps.publications.services.catalog.public_entries`, so nothing
that is not an accepted, active and published article can be reached:

* an unknown code, or an article that is not accepted, answers ``404``;
* an accepted article that was taken down answers ``404`` on its page and
  ``410`` on its document;
* every document delivery is audited, and a failed audit means ``503``.

List and page answers may be cached for at most a minute (the plan allows
five); the document is never cached, so the audit sees every download.
"""

from __future__ import annotations

from django.http import HttpResponse
from rest_framework.generics import GenericAPIView
from rest_framework.request import Request
from rest_framework.response import Response

from apps.publications.catalog_filters import validated_filters
from apps.publications.catalog_serializers import PublicCatalogSerializer
from apps.publications.services.catalog import (
    public_entries,
    retired_article_exists,
    search_entries,
)
from apps.publications.services.downloads import authorize_public_download, xaccel_response
from apps.users.permissions import IsPublicCatalog
from config.exceptions import DomainError, ErrorCode
from config.request_context import audit_request_context

CACHE_CONTROL = "public, max-age=60"
UNAVAILABLE_MESSAGE = "Documento no disponible."


class PublicCatalogBaseView(GenericAPIView):
    """No authentication, safe methods only, accepted-and-active scope."""

    authentication_classes: list = []
    permission_classes = [IsPublicCatalog]
    serializer_class = PublicCatalogSerializer
    lookup_url_kwarg = "code"

    def get_queryset(self):
        return public_entries()


class CatalogListView(PublicCatalogBaseView):
    """``GET /api/catalog/``: search and filter the published articles."""

    def get(self, request: Request) -> Response:
        params = validated_filters(request.query_params)
        page = self.paginate_queryset(search_entries(self.get_queryset(), params))
        response = self.get_paginated_response(PublicCatalogSerializer(page, many=True).data)
        response["Cache-Control"] = CACHE_CONTROL
        return response


class CatalogDetailView(PublicCatalogBaseView):
    """``GET /api/catalog/{code}/``: the public page of one article."""

    def get(self, request: Request, code: str) -> Response:
        entry = self.get_object_by_code(code)
        response = Response(PublicCatalogSerializer(entry).data)
        response["Cache-Control"] = CACHE_CONTROL
        return response

    def get_object_by_code(self, code: str):
        entry = self.get_queryset().filter(manuscript__code=code).first()
        if entry is None:
            raise DomainError("Artículo no encontrado.", code=ErrorCode.NOT_FOUND)
        return entry


class CatalogDocumentView(PublicCatalogBaseView):
    """``GET /api/catalog/{code}/document/``: the public PDF through Nginx."""

    def get(self, request: Request, code: str) -> HttpResponse:
        entry = self.get_queryset().filter(manuscript__code=code).first()
        if entry is None:
            if retired_article_exists(code):
                raise DomainError(
                    UNAVAILABLE_MESSAGE, code=ErrorCode.STATE_CONFLICT, status_code=410
                )
            raise DomainError("Artículo no encontrado.", code=ErrorCode.NOT_FOUND)
        internal_uri = authorize_public_download(
            entry=entry, context=audit_request_context(request)
        )
        return xaccel_response(internal_uri, f"{entry.manuscript.code}.pdf", disposition="inline")
