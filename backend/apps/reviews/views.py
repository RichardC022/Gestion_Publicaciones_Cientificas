"""Editor endpoints (plan section 2.4, TSK-47).

Every view requires an authenticated account with the active ``EDITOR``
role (``403`` otherwise). The scope is :meth:`Manuscript.objects.for_editor`,
which leaves out drafts and any manuscript the editor registered or
co-authored: those answer ``404``, so a conflict of interest never
reveals that the manuscript exists, and the editor can neither assign
nor judge it.
"""

from __future__ import annotations

from django.db.models import OuterRef, Q, QuerySet, Subquery
from django.db.models.functions import Now
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from apps.publications.filters import apply_filters
from apps.publications.models import Manuscript, ManuscriptVersion
from apps.publications.views import etag_for
from apps.reviews.models import Assignment
from apps.reviews.serializers import (
    AssignmentSerializer,
    AssignReviewerSerializer,
    EligibleReviewerSerializer,
    ReviewerFilterSerializer,
    RevokeAssignmentSerializer,
    StartReviewSerializer,
    SubmissionDetailSerializer,
    SubmissionListSerializer,
)
from apps.reviews.services.assignments import assign_reviewer, revoke_assignment, start_review
from apps.reviews.services.eligibility import eligible_reviewers
from apps.users.permissions import IsEditor
from config.exceptions import DomainError, ErrorCode
from config.request_context import audit_request_context


class EditorBaseView(GenericAPIView):
    """Shared permissions and manuscript scope of the editor module."""

    permission_classes = [IsAuthenticated, IsEditor]

    def scoped_manuscripts(self) -> QuerySet:
        return Manuscript.objects.for_editor(self.request.user)

    def get_manuscript(self, pk) -> Manuscript:
        """The manuscript in the editor's scope; anything else answers ``404``."""
        return get_object_or_404(self.scoped_manuscripts(), pk=pk)

    def scoped_assignments(self) -> QuerySet:
        in_scope = self.scoped_manuscripts().values("pk")
        return (
            Assignment.objects.filter(manuscript__in=in_scope)
            .select_related("manuscript", "version", "reviewer", "assigned_by", "revoked_by")
            .with_overdue()
        )

    def represent_assignment(self, assignment: Assignment) -> dict:
        fresh = self.scoped_assignments().get(pk=assignment.pk)
        return AssignmentSerializer(fresh, context={"request": self.request}).data


class SubmissionListView(EditorBaseView):
    """``GET /api/editor/submissions/``: the inbox of ``SUBMITTED`` manuscripts."""

    def get(self, request: Request) -> Response:
        latest_submission = (
            ManuscriptVersion.objects.filter(manuscript=OuterRef("pk"))
            .order_by("-version_number")
            .values("submitted_at")[:1]
        )
        inbox = (
            self.scoped_manuscripts()
            .filter(status=Manuscript.Status.SUBMITTED, is_active=True)
            .annotate(submitted_at=Subquery(latest_submission))
        )
        page = self.paginate_queryset(apply_filters(inbox, request.query_params))
        return self.get_paginated_response(SubmissionListSerializer(page, many=True).data)


class SubmissionDetailView(EditorBaseView):
    """``GET /api/editor/submissions/{id}/``: metadata, authors, PDFs and history."""

    def get(self, request: Request, pk) -> Response:
        manuscript = self.get_manuscript(pk)
        data = SubmissionDetailSerializer(manuscript, context={"request": request}).data
        response = Response(data)
        response["ETag"] = etag_for(manuscript)
        return response


class StartReviewView(EditorBaseView):
    """``POST /api/editor/submissions/{id}/start-review/``.

    ``SUBMITTED`` becomes ``UNDER_REVIEW``; with ``reviewer_id`` the
    reviewer is assigned in the same transaction.
    """

    def post(self, request: Request, pk) -> Response:
        manuscript = self.get_manuscript(pk)
        body = StartReviewSerializer(data=request.data)
        body.is_valid(raise_exception=True)

        manuscript, assignment = start_review(
            manuscript_id=manuscript.pk,
            editor=request.user,
            reviewer_id=body.validated_data.get("reviewer_id"),
            context=audit_request_context(request),
        )
        response = Response(
            {
                "id": manuscript.pk,
                "code": manuscript.code,
                "status": manuscript.status,
                "assignment": self.represent_assignment(assignment) if assignment else None,
            }
        )
        response["ETag"] = etag_for(manuscript)
        return response


class EligibleReviewersView(EditorBaseView):
    """``GET /api/editor/reviewers/``: available reviewers free of conflicts."""

    def get(self, request: Request) -> Response:
        params = ReviewerFilterSerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        manuscript = None
        if "manuscript_id" in params.validated_data:
            manuscript = self.get_manuscript(params.validated_data["manuscript_id"])
        area = params.validated_data.get("area") or (manuscript.area if manuscript else None)

        reviewers = eligible_reviewers(manuscript=manuscript, area=area)
        page = self.paginate_queryset(reviewers)
        return self.get_paginated_response(EligibleReviewerSerializer(page, many=True).data)


class ManuscriptAssignmentsView(EditorBaseView):
    """``/api/editor/manuscripts/{id}/assignments/``: history and new assignment."""

    def get(self, request: Request, pk) -> Response:
        manuscript = self.get_manuscript(pk)
        history = self.scoped_assignments().filter(manuscript=manuscript).order_by(
            "-assigned_at", "-id"
        )
        page = self.paginate_queryset(history)
        return self.get_paginated_response(
            AssignmentSerializer(page, many=True, context={"request": request}).data
        )

    def post(self, request: Request, pk) -> Response:
        manuscript = self.get_manuscript(pk)
        body = AssignReviewerSerializer(data=request.data)
        body.is_valid(raise_exception=True)

        assignment = assign_reviewer(
            manuscript_id=manuscript.pk,
            editor=request.user,
            reviewer_id=body.validated_data["reviewer_id"],
            context=audit_request_context(request),
        )
        return Response(self.represent_assignment(assignment), status=status.HTTP_201_CREATED)


class AssignmentRevokeView(EditorBaseView):
    """``POST /api/editor/assignments/{id}/revoke/``."""

    def post(self, request: Request, pk) -> Response:
        assignment = get_object_or_404(self.scoped_assignments(), pk=pk)
        body = RevokeAssignmentSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        if not body.validated_data["reason"].strip():
            raise DomainError(
                "Indique el motivo de la revocación.",
                code=ErrorCode.VALIDATION_ERROR,
                details={"reason": ["Indique el motivo de la revocación."]},
            )

        revoked = revoke_assignment(
            assignment_id=assignment.pk,
            editor=request.user,
            cause=body.validated_data["cause"],
            reason=body.validated_data["reason"],
            context=audit_request_context(request),
        )
        return Response(self.represent_assignment(revoked))


class ExpiredAssignmentsView(EditorBaseView):
    """``GET /api/editor/assignments/expired/``: overdue assignments awaiting a decision.

    ``EXPIRED`` ones, plus ``ACTIVE`` ones already past ``due_at`` that the
    scheduled task has not marked yet: the cut is always the database clock.
    """

    def get(self, request: Request) -> Response:
        overdue = (
            self.scoped_assignments()
            .filter(manuscript__is_active=True)
            .filter(
                Q(status=Assignment.Status.EXPIRED)
                | Q(status=Assignment.Status.ACTIVE, due_at__lte=Now())
            )
            .order_by("due_at", "id")
        )
        page = self.paginate_queryset(overdue)
        return self.get_paginated_response(
            AssignmentSerializer(page, many=True, context={"request": request}).data
        )
