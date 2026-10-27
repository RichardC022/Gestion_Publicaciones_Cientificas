"""Editor (plan section 2.4, TSK-47) and reviewer (section 2.5, TSK-61) endpoints.

Every view requires an authenticated account with the active ``EDITOR``
role (``403`` otherwise). The scope is :meth:`Manuscript.objects.for_editor`,
which leaves out drafts and any manuscript the editor registered or
co-authored: those answer ``404``, so a conflict of interest never
reveals that the manuscript exists, and the editor can neither assign
nor judge it.

The reviewer's views start at :meth:`Assignment.objects.for_reviewer`,
never at the global manuscript repository: a foreign assignment, a
withdrawn manuscript or one the reviewer authored answers ``404``.
"""

from __future__ import annotations

import json

from django.db.models import OuterRef, Q, QuerySet, Subquery
from django.db.models.functions import Now
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import JSONRenderer
from rest_framework.request import Request
from rest_framework.response import Response

from apps.publications.filters import apply_filters
from apps.publications.models import Manuscript, ManuscriptVersion
from apps.publications.services.downloads import authorize_sanitized_download, xaccel_response
from apps.publications.services.idempotency import (
    IdempotencyScope,
    IdempotentReplay,
    request_hash,
)
from apps.publications.services.verdicts import VerdictResult, register_verdict
from apps.publications.views import (
    etag_for,
    parse_idempotency_key,
    parse_if_match,
    replayed,
)
from apps.reviews.models import Assignment, Evaluation
from apps.reviews.serializers import (
    AssignmentSerializer,
    AssignReviewerSerializer,
    EditorEvaluationSerializer,
    EvaluationDraftSerializer,
    EligibleReviewerSerializer,
    RegisterVerdictSerializer,
    ReviewerAssignmentDetailSerializer,
    ReviewerAssignmentSerializer,
    ReviewerEvaluationSerializer,
    ReviewerFilterSerializer,
    RevokeAssignmentSerializer,
    StartReviewSerializer,
    SubmissionDetailSerializer,
    SubmissionListSerializer,
    VerdictSerializer,
)
from apps.reviews.services.assignments import assign_reviewer, revoke_assignment, start_review
from apps.reviews.services.evaluations import save_draft, submit_evaluation
from apps.reviews.services.eligibility import eligibility_breakdown, eligible_reviewers
from apps.reviews.permissions import IsActiveAssignedReviewer, IsAssignedReviewer
from apps.users.permissions import IsEditor, IsReviewer
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
            .prefetch_related("authors")
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
    """``GET /api/editor/reviewers/``: available reviewers free of conflicts.

    When no reviewer is eligible the answer adds ``diagnosis``: how many
    reviewer accounts exist and how many each rule excludes, so the empty
    list is never left without an explanation.
    """

    def get(self, request: Request) -> Response:
        params = ReviewerFilterSerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        manuscript = None
        if "manuscript_id" in params.validated_data:
            manuscript = self.get_manuscript(params.validated_data["manuscript_id"])
        area = params.validated_data.get("area") or (manuscript.area if manuscript else None)

        reviewers = eligible_reviewers(manuscript=manuscript, area=area)
        page = self.paginate_queryset(reviewers)
        response = self.get_paginated_response(EligibleReviewerSerializer(page, many=True).data)
        if response.data["count"] == 0:
            # Una lista vacía se explica: cuántos Revisores hay y qué regla los excluye.
            response.data["diagnosis"] = eligibility_breakdown(manuscript=manuscript, area=area)
        return response


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


def render_verdict(result: VerdictResult) -> tuple[int, dict]:
    """``(status, body)`` of a registered verdict; the body is what gets stored.

    It carries the new verdict, the manuscript's new state, what the
    decision published or opened, and the whole verdict history.
    """
    manuscript = result.manuscript
    data = {
        "verdict": VerdictSerializer(result.verdict).data,
        "manuscript": {
            "id": manuscript.pk,
            "code": manuscript.code,
            "status": manuscript.status,
            "current_round": manuscript.current_round,
            "current_version": manuscript.current_version,
        },
        "catalog_entry": (
            {
                "id": result.catalog_entry.pk,
                "published_at": result.catalog_entry.published_at,
            }
            if result.catalog_entry
            else None
        ),
        "opened_round": result.opened_round.round_number if result.opened_round else None,
        "history": VerdictSerializer(
            manuscript.verdicts.select_related("editor", "version"), many=True
        ).data,
    }
    return status.HTTP_201_CREATED, json.loads(JSONRenderer().render(data))


class ManuscriptVerdictsView(EditorBaseView):
    """``/api/editor/manuscripts/{id}/verdicts/``: the verdict history and a new verdict.

    There is no ``PUT``, ``PATCH`` or ``DELETE``: a registered verdict is
    never edited (``405``). ``POST`` needs ``Idempotency-Key`` and
    ``If-Match`` with the ``ETag`` of the manuscript; the same key repeats
    the stored answer. An editor with a conflict of interest reaches the
    service, which blocks the attempt with ``403`` and audits it
    (CA-HU-13-08); on ``GET`` the same editor gets ``404``.
    """

    def get(self, request: Request, pk) -> Response:
        manuscript = self.get_manuscript(pk)
        page = self.paginate_queryset(manuscript.verdicts.select_related("editor", "version"))
        return self.get_paginated_response(VerdictSerializer(page, many=True).data)

    def post(self, request: Request, pk) -> Response:
        # Todo manuscrito enviado: el servicio decide el conflicto de interés
        # y deja constancia del intento, que el alcance con `404` ocultaría.
        manuscript = get_object_or_404(
            Manuscript.objects.exclude(status=Manuscript.Status.DRAFT), pk=pk
        )
        body = RegisterVerdictSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        key = parse_idempotency_key(request)

        scope = IdempotencyScope(
            user=request.user,
            endpoint=f"{request.method} {request.path}",
            key=key,
            request_hash=lambda: request_hash(
                str(manuscript.pk),
                data["decision"],
                (data.get("justification") or "").strip(),
                (data.get("observations") or "").strip(),
            ),
            render=render_verdict,
        )
        # Un reintento de un veredicto ya registrado devuelve su respuesta.
        if (stored := scope.find()) is not None:
            return replayed(stored)

        try:
            result = register_verdict(
                manuscript_id=manuscript.pk,
                editor=request.user,
                decision=data["decision"],
                justification=data.get("justification"),
                observations=data.get("observations"),
                expected_lock_version=parse_if_match(request),
                context=audit_request_context(request),
                idempotency=scope,
            )
        except IdempotentReplay as replay:
            return replayed(replay.stored)
        status_code, response_body = render_verdict(result)
        response = Response(response_body, status=status_code)
        response["ETag"] = etag_for(result.manuscript)
        return response


class ManuscriptEvaluationsView(EditorBaseView):
    """``GET /api/editor/manuscripts/{id}/evaluations/``: the final evaluations.

    Complete, with the reviewer's identity and the confidential comments:
    the only place that exposes them, and only to the editor. Drafts are
    private to the reviewer and never listed.
    """

    def get(self, request: Request, pk) -> Response:
        manuscript = self.get_manuscript(pk)
        evaluations = (
            Evaluation.objects.filter(manuscript=manuscript, status=Evaluation.Status.FINAL)
            .select_related("reviewer", "version")
            .order_by("submitted_at", "id")
        )
        page = self.paginate_queryset(evaluations)
        return self.get_paginated_response(EditorEvaluationSerializer(page, many=True).data)


class ReviewerBaseView(GenericAPIView):
    """Shared permissions and assignment scope of the reviewer module."""

    permission_classes = [IsAuthenticated, IsReviewer, IsAssignedReviewer]

    def scoped_assignments(self) -> QuerySet:
        return (
            Assignment.objects.for_reviewer(self.request.user)
            .with_overdue()
            .with_evaluation_started()
        )

    def get_assignment(self, pk) -> Assignment:
        """The reviewer's own assignment; anything else answers ``404``."""
        return get_object_or_404(self.scoped_assignments(), pk=pk)


class ReviewerAssignmentListView(ReviewerBaseView):
    """``GET /api/reviewer/assignments/``: the reviewer's own inbox."""

    def get(self, request: Request) -> Response:
        page = self.paginate_queryset(self.scoped_assignments())
        return self.get_paginated_response(ReviewerAssignmentSerializer(page, many=True).data)


class ReviewerAssignmentDetailView(ReviewerBaseView):
    """``GET /api/reviewer/assignments/{id}/``: blind detail of an ``ACTIVE`` or ``COMPLETED`` one."""

    def get(self, request: Request, pk) -> Response:
        assignment = self.get_assignment(pk)
        self.check_object_permissions(request, assignment)
        return Response(
            ReviewerAssignmentDetailSerializer(assignment, context={"request": request}).data
        )


class ReviewerAssignmentDocumentView(ReviewerBaseView):
    """``GET /api/reviewer/assignments/{id}/document/``: the sanitized PDF.

    Only an ``ACTIVE`` assignment downloads; any other status of the
    reviewer's own assignment answers ``410``. The internal path always
    ends in ``sanitized.pdf`` and the name is generic, so the original
    and the author's file name never reach the reviewer. The download is
    audited first; if the audit fails the answer is ``503`` without redirect.
    """

    permission_classes = [IsAuthenticated, IsReviewer, IsActiveAssignedReviewer]

    def get(self, request: Request, pk) -> HttpResponse:
        assignment = self.get_assignment(pk)
        if assignment.status != Assignment.Status.ACTIVE:
            raise DomainError(
                "Esta asignación ya no permite descargar el documento.",
                code=ErrorCode.STATE_CONFLICT,
                status_code=410,
            )
        self.check_object_permissions(request, assignment)

        manuscript, version = assignment.manuscript, assignment.version
        internal_uri = authorize_sanitized_download(
            manuscript=manuscript,
            version=version,
            user=request.user,
            context=audit_request_context(request),
        )
        return xaccel_response(
            internal_uri, f"manuscript-{manuscript.code}-v{version.version_number}.pdf"
        )


def evaluation_response(evaluation: Evaluation) -> Response:
    """The reviewer's evaluation with its optimistic lock as the ``ETag``."""
    response = Response(ReviewerEvaluationSerializer(evaluation).data)
    response["ETag"] = etag_for(evaluation)
    return response


class ReviewerEvaluationView(ReviewerBaseView):
    """``GET``/``PUT /api/reviewer/assignments/{id}/evaluation/``: the private draft or the final.

    ``GET`` answers an empty draft before the first save. ``PUT`` needs
    ``If-Match`` with the ``ETag`` read (``"0"`` for the empty draft) and
    changes only the fields sent; the service decides whether the
    assignment still accepts writes. Neither shows the draft to anyone
    but the reviewer who owns the assignment.
    """

    def get_permissions(self):
        if self.request.method == "GET":
            return super().get_permissions()
        return [IsAuthenticated(), IsReviewer()]

    def get(self, request: Request, pk) -> Response:
        assignment = self.get_assignment(pk)
        self.check_object_permissions(request, assignment)
        evaluation = Evaluation.objects.filter(assignment=assignment).first()
        if evaluation is None:
            evaluation = Evaluation(id=None, assignment=assignment)
        return evaluation_response(evaluation)

    def put(self, request: Request, pk) -> Response:
        self.get_assignment(pk)
        body = EvaluationDraftSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        evaluation = save_draft(
            assignment_id=pk,
            reviewer=request.user,
            values=body.validated_data,
            expected_lock_version=parse_if_match(request, "de la evaluación"),
        )
        return evaluation_response(evaluation)


class ReviewerEvaluationSubmitView(ReviewerBaseView):
    """``POST /api/reviewer/assignments/{id}/evaluation/submit/``: the immutable final."""

    permission_classes = [IsAuthenticated, IsReviewer]

    def post(self, request: Request, pk) -> Response:
        self.get_assignment(pk)
        evaluation = submit_evaluation(
            assignment_id=pk,
            reviewer=request.user,
            expected_lock_version=parse_if_match(request, "de la evaluación"),
            context=audit_request_context(request),
        )
        return evaluation_response(evaluation)
