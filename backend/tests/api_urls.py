"""Test-only API routes for the TSK-11 acceptance tests.

These views exist exclusively to exercise the error envelope, the
request-id middleware and the pagination contract. They never mount in
the real URLconf.
"""

from django.http import Http404
from django.urls import path
from rest_framework import exceptions
from rest_framework.response import Response
from rest_framework.views import APIView

from config.exceptions import DomainError, ErrorCode
from config.pagination import StandardPagination

TOTAL_ITEMS = 250


class EchoRequestIDView(APIView):
    """Return the request id attached by the middleware."""

    def get(self, request, *args, **kwargs):
        return Response({"request_id": request.request_id})


class DomainErrorView(APIView):
    """Raise a domain error with catalog code and details."""

    def get(self, request, *args, **kwargs):
        raise DomainError(
            "La acción no es válida en el estado actual.",
            code=ErrorCode.STATE_CONFLICT,
            details={"current_status": "DRAFT"},
        )


class NotFoundView(APIView):
    """Raise a plain Django ``Http404``."""

    def get(self, request, *args, **kwargs):
        raise Http404


class ValidationView(APIView):
    """Raise a DRF validation error with field details."""

    def get(self, request, *args, **kwargs):
        raise exceptions.ValidationError({"title": ["Este campo es obligatorio."]})


class CrasherView(APIView):
    """Raise an unhandled exception with a sentinel payload."""

    def get(self, request, *args, **kwargs):
        raise RuntimeError("sentinel-internal-detail")


class ItemsView(APIView):
    """Paginated list endpoint used to validate the pagination contract."""

    def get(self, request, *args, **kwargs):
        items = [{"id": index} for index in range(TOTAL_ITEMS)]
        paginator = StandardPagination()
        page = paginator.paginate_queryset(items, request, view=self)
        return paginator.get_paginated_response(page)


urlpatterns = [
    path("echo/", EchoRequestIDView.as_view()),
    path("conflict/", DomainErrorView.as_view()),
    path("missing/", NotFoundView.as_view()),
    path("invalid/", ValidationView.as_view()),
    path("crash/", CrasherView.as_view()),
    path("items/", ItemsView.as_view()),
]
