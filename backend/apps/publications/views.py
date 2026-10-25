"""Manuscript endpoints of the author and editor modules (plan section 2.3).

* ``GET /api/manuscripts/`` — the author's own manuscripts and, for an
  editor, the editor scope. Roles are additive: a person with both roles
  gets the union.
* ``POST /api/manuscripts/`` — author only; creates a ``DRAFT``.
* ``GET /api/manuscripts/{id}/`` — the author's own or the editor's.
* ``PATCH /api/manuscripts/{id}/`` — the owner, while ``DRAFT`` or
  ``REQUIRES_CORRECTIONS``; requires ``If-Match`` with the ``ETag``.

A manuscript outside the actor's scope answers ``404``, never ``403``.
``403`` is reserved for a role without access to the module.
"""

from __future__ import annotations

import re

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.generics import GenericAPIView
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from apps.publications.filters import apply_filters
from apps.publications.models import Manuscript
from apps.publications.permissions import IsManuscriptOwner
from apps.publications.serializers import (
    AuthorManuscriptSerializer,
    draft_file_summary,
    manuscript_serializer_class,
)
from apps.publications.services.drafts import attach_draft_file, ensure_draft
from apps.publications.services.manuscripts import (
    create_manuscript,
    ensure_editable,
    update_manuscript,
)
from apps.users.models import Role
from apps.users.permissions import IsAuthor, IsEditor, request_active_roles
from config.exceptions import DomainError, ErrorCode
from config.request_context import audit_request_context

_IF_MATCH_PATTERN = re.compile(r'^(?:W/)?"?(\d+)"?$')


def etag_for(manuscript: Manuscript) -> str:
    """Strong ``ETag`` of the optimistic lock (plan section 2.11)."""
    return f'"{manuscript.lock_version}"'


def parse_if_match(request: Request) -> int:
    """The ``lock_version`` the client saw; the header is mandatory."""
    match = _IF_MATCH_PATTERN.match((request.headers.get("If-Match") or "").strip())
    if match is None:
        raise DomainError(
            "Envíe la cabecera If-Match con el ETag vigente del manuscrito.",
            code=ErrorCode.VALIDATION_ERROR,
        )
    return int(match.group(1))


class ManuscriptBaseView(GenericAPIView):
    """Shared scope and representation of the manuscript endpoints."""

    def get_queryset(self):
        roles = request_active_roles(self.request)
        return (
            Manuscript.objects.visible_to(
                self.request.user,
                as_author=Role.Code.AUTHOR in roles,
                as_editor=Role.Code.EDITOR in roles,
            )
            .select_related("created_by")
            .prefetch_related("authors", "versions")
        )

    def get_manuscript(self, pk) -> Manuscript:
        """The manuscript in scope; anything else answers ``404``."""
        manuscript = get_object_or_404(self.get_queryset(), pk=pk)
        self.check_object_permissions(self.request, manuscript)
        return manuscript

    def represent(self, manuscript: Manuscript) -> dict:
        serializer_class = manuscript_serializer_class(manuscript, self.request.user)
        return serializer_class(manuscript, context={"request": self.request}).data

    def respond(self, manuscript: Manuscript, http_status: int = status.HTTP_200_OK) -> Response:
        response = Response(self.represent(manuscript), status=http_status)
        response["ETag"] = etag_for(manuscript)
        return response


class ManuscriptListCreateView(ManuscriptBaseView):
    """List the manuscripts in scope or register a new draft."""

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAuthenticated(), IsAuthor()]
        return [IsAuthenticated(), (IsAuthor | IsEditor)()]

    def get(self, request: Request) -> Response:
        queryset = apply_filters(self.get_queryset(), request.query_params)
        page = self.paginate_queryset(queryset)
        return self.get_paginated_response([self.represent(item) for item in page])

    def post(self, request: Request) -> Response:
        serializer = AuthorManuscriptSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        manuscript = create_manuscript(
            user=request.user,
            data=serializer.validated_data,
            context=audit_request_context(request),
        )
        return self.respond(manuscript, status.HTTP_201_CREATED)


class ManuscriptDetailView(ManuscriptBaseView):
    """Read a manuscript in scope or edit the owner's one."""

    def get_permissions(self):
        if self.request.method == "PATCH":
            return [IsAuthenticated(), IsAuthor(), IsManuscriptOwner()]
        return [IsAuthenticated(), (IsAuthor | IsEditor)()]

    def get(self, request: Request, pk) -> Response:
        return self.respond(self.get_manuscript(pk))

    def patch(self, request: Request, pk) -> Response:
        manuscript = self.get_manuscript(pk)
        # Estado y cabecera antes de validar el cuerpo: un manuscrito no
        # editable responde 409 sin importar el contenido enviado.
        ensure_editable(manuscript)
        expected_lock_version = parse_if_match(request)

        serializer = AuthorManuscriptSerializer(
            manuscript, data=request.data, partial=True, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        updated = update_manuscript(
            manuscript_id=manuscript.pk,
            user=request.user,
            expected_lock_version=expected_lock_version,
            data=serializer.validated_data,
            context=audit_request_context(request),
        )
        return self.respond(updated)


class ManuscriptDraftFileView(ManuscriptBaseView):
    """``POST /api/manuscripts/{id}/draft-file/``: attach or replace the draft PDF.

    Only the owner, only while the manuscript is a ``DRAFT``. It creates
    no version, round or snapshot. Anything but ``multipart/form-data``
    answers ``415``; the file travels in the ``file`` field.
    """

    parser_classes = [MultiPartParser]

    def get_permissions(self):
        return [IsAuthenticated(), IsAuthor(), IsManuscriptOwner()]

    def post(self, request: Request, pk) -> Response:
        manuscript = self.get_manuscript(pk)
        # El estado se revisa antes de leer el cuerpo (409 antes que 415/400).
        ensure_draft(manuscript)

        uploaded = request.data.get("file")
        if uploaded is None or not hasattr(uploaded, "chunks"):
            raise DomainError(
                "Adjunte el archivo PDF en el campo 'file' de la solicitud multipart.",
                code=ErrorCode.VALIDATION_ERROR,
            )

        result = attach_draft_file(
            manuscript_id=manuscript.pk,
            user=request.user,
            uploaded=uploaded,
            context=audit_request_context(request),
        )
        return Response(
            draft_file_summary(result.manuscript),
            status=status.HTTP_200_OK if result.replaced else status.HTTP_201_CREATED,
        )
