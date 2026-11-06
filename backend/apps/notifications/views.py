"""Notification endpoints of the signed-in user (plan section 2.8, TSK-75).

Every query starts at :func:`~apps.notifications.services.panel_notices`,
the user's own panel notices, so another person's notice answers ``404``
and never reveals that it exists. Any authenticated account may read its
own notices, whatever its roles.
"""

from __future__ import annotations

from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from apps.notifications.serializers import NotificationSerializer
from apps.notifications.services import mark_all_read, mark_read, panel_notices
from config.exceptions import DomainError, ErrorCode
from config.openapi import PAGINATION

READ_FILTER_MESSAGE = "El parámetro read debe ser true o false."


class NotificationBaseView(GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = NotificationSerializer

    def get_queryset(self):
        return panel_notices(self.request.user)


@extend_schema_view(
    get=extend_schema(
        tags=["Notificaciones"],
        operation_id="notifications_list",
        summary="Listar mis avisos",
        description=(
            "Los avisos del usuario, del más reciente al más antiguo. `meta.unread_count` trae el "
            "total de no leídos, sin importar el filtro."
        ),
        parameters=[
            OpenApiParameter(
                "read",
                OpenApiTypes.BOOL,
                OpenApiParameter.QUERY,
                description="`true` solo leídos; `false` solo no leídos. Otro valor responde 400.",
            ),
            *PAGINATION,
        ],
        responses={200: NotificationSerializer(many=True)},
    ),
)
class NotificationListView(NotificationBaseView):
    """``GET /api/v1/notifications/``: own notices, newest first, with ``unread_count``."""

    def get(self, request: Request) -> Response:
        queryset = self.get_queryset()
        unread = queryset.filter(read_at__isnull=True).count()
        flag = request.query_params.get("read")
        if flag is not None:
            if flag not in ("true", "false"):
                raise DomainError(
                    READ_FILTER_MESSAGE,
                    code=ErrorCode.VALIDATION_ERROR,
                    details={"read": [READ_FILTER_MESSAGE]},
                )
            queryset = queryset.filter(read_at__isnull=(flag == "false"))
        page = self.paginate_queryset(queryset.order_by("-created_at", "id"))
        response = self.get_paginated_response(NotificationSerializer(page, many=True).data)
        response.data["unread_count"] = unread
        return response


@extend_schema_view(
    patch=extend_schema(
        tags=["Notificaciones"],
        operation_id="notifications_mark_read",
        summary="Marcar un aviso como leído",
        description="Idempotente. Un aviso ajeno responde 404.",
        request=None,
        parameters=[OpenApiParameter("id", OpenApiTypes.UUID, OpenApiParameter.PATH)],
        responses={200: NotificationSerializer},
    ),
)
class NotificationReadView(NotificationBaseView):
    """``PATCH /api/v1/notifications/{id}/read/``: mark one notice read (idempotent)."""

    def patch(self, request: Request, pk) -> Response:
        notice = get_object_or_404(self.get_queryset(), pk=pk)
        return Response(NotificationSerializer(mark_read(notice)).data)


@extend_schema_view(
    post=extend_schema(
        tags=["Notificaciones"],
        operation_id="notifications_mark_all_read",
        summary="Marcar todos mis avisos como leídos",
        request=None,
        responses={204: None},
    ),
)
class NotificationReadAllView(NotificationBaseView):
    """``POST /api/v1/notifications/read-all/``: mark every own notice read."""

    def post(self, request: Request) -> Response:
        mark_all_read(request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)
