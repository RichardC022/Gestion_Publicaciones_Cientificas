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
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    OpenApiParameter,
    extend_schema,
    extend_schema_view,
    inline_serializer,
)
from rest_framework import serializers, status
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import JSONRenderer
from rest_framework.request import Request
from rest_framework.response import Response

from apps.publications.filters import ManuscriptFilterSerializer, apply_filters
from apps.publications.models import Manuscript, ManuscriptVersion, Verdict
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
from apps.reviews.models import Assignment, Evaluation, IncidentReport
from apps.reviews.serializers import (
    AssignmentSerializer,
    AssignReviewerSerializer,
    DeclareConflictSerializer,
    EditorEvaluationSerializer,
    EditorIncidentSerializer,
    EvaluationDraftSerializer,
    EligibleReviewerSerializer,
    RegisterVerdictSerializer,
    ReportIncidentSerializer,
    ResolveIncidentSerializer,
    ReviewerAssignmentDetailSerializer,
    ReviewerAssignmentSerializer,
    ReviewerEvaluationHistoryDetailSerializer,
    ReviewerEvaluationHistorySerializer,
    ReviewerEvaluationSerializer,
    ReviewerIncidentSerializer,
    ReviewerFilterSerializer,
    RevokeAssignmentSerializer,
    StartReviewSerializer,
    SubmissionDetailSerializer,
    SubmissionListSerializer,
    VerdictSerializer,
)
from apps.reviews.services.assignments import assign_reviewer, revoke_assignment, start_review
from apps.reviews.services.incidents import report_incident, resolve_incident
from apps.reviews.services.evaluations import declare_conflict, save_draft, submit_evaluation
from apps.reviews.services.eligibility import eligibility_breakdown, eligible_reviewers
from apps.reviews.permissions import IsActiveAssignedReviewer, IsAssignedReviewer
from apps.users.permissions import IsEditor, IsReviewer
from config.exceptions import DomainError, ErrorCode
from config.openapi import IDEMPOTENCY_KEY, IF_MATCH, PAGINATION, error_response
from config.request_context import audit_request_context


# --- Documentación OpenAPI: piezas que comparten varias vistas -------------------------
ID = OpenApiParameter("id", OpenApiTypes.UUID, OpenApiParameter.PATH)
STATE_409 = error_response("La acción no es válida en el estado actual (STATE_CONFLICT).")
NOT_EDITOR_SCOPE = "Solo el Editor. Un manuscrito fuera de su alcance (o con conflicto de interés) responde 404."
ETAG = {
    "ETag": OpenApiParameter(
        "ETag",
        location=OpenApiParameter.HEADER,
        response=True,
        description='Versión actual del recurso (por ejemplo `"3"`); úsela en `If-Match`.',
    )
}
StartReviewResult = inline_serializer(
    "StartReviewResult",
    {
        "id": serializers.UUIDField(),
        "code": serializers.CharField(),
        "status": serializers.CharField(),
        "assignment": AssignmentSerializer(allow_null=True),
    },
)
VerdictRegistration = inline_serializer(
    "VerdictRegistration",
    {
        "verdict": VerdictSerializer(),
        "manuscript": inline_serializer(
            "VerdictManuscript",
            {
                "id": serializers.UUIDField(),
                "code": serializers.CharField(),
                "status": serializers.CharField(),
                "current_round": serializers.IntegerField(),
                "current_version": serializers.IntegerField(),
            },
        ),
        "catalog_entry": inline_serializer(
            "VerdictCatalogEntry",
            {"id": serializers.UUIDField(), "published_at": serializers.DateTimeField()},
            allow_null=True,
        ),
        "opened_round": serializers.IntegerField(allow_null=True),
        "history": VerdictSerializer(many=True),
    },
)


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

    def scoped_incidents(self) -> QuerySet:
        """Confidential reports over the manuscripts in the editor's scope."""
        return IncidentReport.objects.for_editor(self.request.user).select_related(
            "manuscript", "reporter", "resolved_by", "correction_round"
        )

    def represent_assignment(self, assignment: Assignment) -> dict:
        fresh = self.scoped_assignments().get(pk=assignment.pk)
        return AssignmentSerializer(fresh, context={"request": self.request}).data


@extend_schema_view(
    get=extend_schema(
        tags=["Editor"],
        operation_id="editor_submissions_list",
        summary="Bandeja de envíos",
        description="Solo el Editor. Manuscritos `SUBMITTED` de su alcance, con los mismos filtros que la lista del Autor.",
        parameters=[ManuscriptFilterSerializer, *PAGINATION],
        responses={200: SubmissionListSerializer(many=True)},
    ),
)
class SubmissionListView(EditorBaseView):
    """``GET /api/v1/editor/submissions/``: the inbox of ``SUBMITTED`` manuscripts."""

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


@extend_schema_view(
    get=extend_schema(
        tags=["Editor"],
        operation_id="editor_submissions_retrieve",
        summary="Detalle de un envío",
        description=NOT_EDITOR_SCOPE + " Incluye metadatos, autores, PDFs e historial.",
        parameters=[ID],
        responses={200: SubmissionDetailSerializer},
    ),
)
class SubmissionDetailView(EditorBaseView):
    """``GET /api/v1/editor/submissions/{id}/``: metadata, authors, PDFs and history."""

    def get(self, request: Request, pk) -> Response:
        manuscript = self.get_manuscript(pk)
        data = SubmissionDetailSerializer(manuscript, context={"request": request}).data
        response = Response(data)
        response["ETag"] = etag_for(manuscript)
        return response


@extend_schema_view(
    post=extend_schema(
        tags=["Editor"],
        operation_id="editor_submissions_start_review",
        summary="Iniciar la revisión",
        description=(
            "`SUBMITTED` pasa a `UNDER_REVIEW`. Con `reviewer_id`, el revisor se asigna en la "
            "misma transacción. " + NOT_EDITOR_SCOPE
        ),
        parameters=[ID],
        request=StartReviewSerializer,
        responses={200: StartReviewResult, 409: STATE_409},
    ),
)
class StartReviewView(EditorBaseView):
    """``POST /api/v1/editor/submissions/{id}/start-review/``.

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


@extend_schema_view(
    get=extend_schema(
        tags=["Editor"],
        operation_id="editor_reviewers_list",
        summary="Revisores elegibles",
        description=(
            "Revisores disponibles y sin conflicto de interés. Si no hay ninguno, `meta.diagnosis` "
            "explica cuántas cuentas hay y cuántas excluye cada regla."
        ),
        parameters=[ReviewerFilterSerializer, *PAGINATION],
        responses={200: EligibleReviewerSerializer(many=True)},
    ),
)
class EligibleReviewersView(EditorBaseView):
    """``GET /api/v1/editor/reviewers/``: available reviewers free of conflicts.

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


@extend_schema_view(
    get=extend_schema(
        tags=["Editor"],
        operation_id="editor_manuscript_assignments_list",
        summary="Historial de asignaciones",
        description=NOT_EDITOR_SCOPE,
        parameters=[ID, *PAGINATION],
        responses={200: AssignmentSerializer(many=True)},
    ),
    post=extend_schema(
        tags=["Editor"],
        operation_id="editor_manuscript_assignments_create",
        summary="Asignar un revisor",
        description="Exactamente un revisor activo por manuscrito. " + NOT_EDITOR_SCOPE,
        parameters=[ID],
        request=AssignReviewerSerializer,
        responses={
            201: AssignmentSerializer,
            409: error_response("Ya hay un revisor activo o la asignación es inválida (ASSIGNMENT_CONFLICT)."),
        },
    ),
)
class ManuscriptAssignmentsView(EditorBaseView):
    """``/api/v1/editor/manuscripts/{id}/assignments/``: history and new assignment."""

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


@extend_schema_view(
    post=extend_schema(
        tags=["Editor"],
        operation_id="editor_assignments_revoke",
        summary="Revocar una asignación",
        parameters=[ID],
        request=RevokeAssignmentSerializer,
        responses={200: AssignmentSerializer, 409: STATE_409},
    ),
)
class AssignmentRevokeView(EditorBaseView):
    """``POST /api/v1/editor/assignments/{id}/revoke/``."""

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


@extend_schema_view(
    get=extend_schema(
        tags=["Editor"],
        operation_id="editor_assignments_expired",
        summary="Asignaciones vencidas",
        description=(
            "Asignaciones `EXPIRED` y las `ACTIVE` ya pasadas de `due_at` que la tarea programada "
            "aún no marcó. El corte usa siempre el reloj de la base de datos."
        ),
        parameters=PAGINATION,
        responses={200: AssignmentSerializer(many=True)},
    ),
)
class ExpiredAssignmentsView(EditorBaseView):
    """``GET /api/v1/editor/assignments/expired/``: overdue assignments awaiting a decision.

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


@extend_schema_view(
    get=extend_schema(
        tags=["Editor"],
        operation_id="editor_manuscript_verdicts_list",
        summary="Historial de veredictos",
        description=NOT_EDITOR_SCOPE,
        parameters=[ID, *PAGINATION],
        responses={200: VerdictSerializer(many=True)},
    ),
    post=extend_schema(
        tags=["Editor"],
        operation_id="editor_manuscript_verdicts_create",
        summary="Registrar un veredicto",
        description=(
            "Un veredicto registrado nunca se edita (no hay PUT, PATCH ni DELETE: 405). Exige "
            "`Idempotency-Key` y `If-Match` con el ETag del manuscrito. Un Editor con conflicto "
            "de interés recibe 403 y el intento queda auditado."
        ),
        parameters=[ID, IDEMPOTENCY_KEY, IF_MATCH],
        request=RegisterVerdictSerializer,
        responses={
            201: VerdictRegistration,
            403: error_response("Conflicto de interés del Editor (FORBIDDEN); queda auditado."),
            409: error_response("Ya existe un veredicto para esa versión (VERDICT_CONFLICT) o el estado no lo permite."),
        },
    ),
)
class ManuscriptVerdictsView(EditorBaseView):
    """``/api/v1/editor/manuscripts/{id}/verdicts/``: the verdict history and a new verdict.

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


@extend_schema_view(
    get=extend_schema(
        tags=["Editor"],
        operation_id="editor_manuscript_evaluations_list",
        summary="Evaluaciones finales de un manuscrito",
        description=NOT_EDITOR_SCOPE + " Solo evaluaciones finales; los borradores del revisor no se listan.",
        parameters=[ID, *PAGINATION],
        responses={200: EditorEvaluationSerializer(many=True)},
    ),
)
class ManuscriptEvaluationsView(EditorBaseView):
    """``GET /api/v1/editor/manuscripts/{id}/evaluations/``: the final evaluations.

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


@extend_schema_view(
    get=extend_schema(
        tags=["Editor"],
        operation_id="editor_incidents_list",
        summary="Incidentes confidenciales",
        description=(
            "Reportes confidenciales de los revisores, los abiertos primero. Se excluyen los de "
            "manuscritos que el Editor registró o coescribió."
        ),
        parameters=[
            OpenApiParameter(
                "status",
                OpenApiTypes.STR,
                OpenApiParameter.QUERY,
                enum=["OPEN", "RESOLVED"],
                description="Filtra por estado. Otro valor responde 400.",
            ),
            *PAGINATION,
        ],
        responses={200: EditorIncidentSerializer(many=True)},
    ),
)
class IncidentListView(EditorBaseView):
    """``GET /api/v1/editor/incidents/``: the confidential reports, open ones first.

    ``?status=OPEN|RESOLVED`` narrows the list. Reports over a manuscript
    the editor registered or co-authored are left out.
    """

    def get(self, request: Request) -> Response:
        incidents = self.scoped_incidents()
        status_filter = request.query_params.get("status")
        if status_filter is not None:
            if status_filter not in IncidentReport.Status.values:
                raise DomainError(
                    "El estado debe ser OPEN o RESOLVED.",
                    code=ErrorCode.VALIDATION_ERROR,
                    details={"status": ["El estado debe ser OPEN o RESOLVED."]},
                )
            incidents = incidents.filter(status=status_filter)
        # "OPEN" va antes que "RESOLVED" en orden alfabético.
        page = self.paginate_queryset(incidents.order_by("status", "-created_at", "-id"))
        return self.get_paginated_response(EditorIncidentSerializer(page, many=True).data)


@extend_schema_view(
    post=extend_schema(
        tags=["Editor"],
        operation_id="editor_incidents_resolve",
        summary="Resolver un incidente",
        description="Se resuelve una sola vez: la segunda responde 409.",
        parameters=[ID],
        request=ResolveIncidentSerializer,
        responses={200: EditorIncidentSerializer, 409: STATE_409},
    ),
)
class IncidentResolveView(EditorBaseView):
    """``POST /api/v1/editor/incidents/{id}/resolve/``: resolve once (``409`` the second time)."""

    def post(self, request: Request, pk) -> Response:
        get_object_or_404(self.scoped_incidents(), pk=pk)
        body = ResolveIncidentSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        resolve_incident(
            incident_id=pk,
            editor=request.user,
            resolution=body.validated_data["resolution"],
            context=audit_request_context(request),
        )
        resolved = self.scoped_incidents().get(pk=pk)
        return Response(EditorIncidentSerializer(resolved).data)


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


@extend_schema_view(
    get=extend_schema(
        tags=["Revisor"],
        operation_id="reviewer_assignments_list",
        summary="Mis asignaciones",
        description="Bandeja del revisor. Nunca incluye manuscritos retirados ni los que el revisor coescribió.",
        parameters=PAGINATION,
        responses={200: ReviewerAssignmentSerializer(many=True)},
    ),
)
class ReviewerAssignmentListView(ReviewerBaseView):
    """``GET /api/v1/reviewer/assignments/``: the reviewer's own inbox."""

    def get(self, request: Request) -> Response:
        page = self.paginate_queryset(self.scoped_assignments())
        return self.get_paginated_response(ReviewerAssignmentSerializer(page, many=True).data)


@extend_schema_view(
    get=extend_schema(
        tags=["Revisor"],
        operation_id="reviewer_assignments_retrieve",
        summary="Detalle ciego de una asignación",
        description=(
            "Doble ciego: la respuesta nunca contiene nombre, correo ni filiación del Autor. Una "
            "asignación ajena responde 404."
        ),
        parameters=[ID],
        responses={200: ReviewerAssignmentDetailSerializer},
    ),
)
class ReviewerAssignmentDetailView(ReviewerBaseView):
    """``GET /api/v1/reviewer/assignments/{id}/``: blind detail of an ``ACTIVE`` or ``COMPLETED`` one."""

    def get(self, request: Request, pk) -> Response:
        assignment = self.get_assignment(pk)
        self.check_object_permissions(request, assignment)
        return Response(
            ReviewerAssignmentDetailSerializer(assignment, context={"request": request}).data
        )


@extend_schema_view(
    get=extend_schema(
        tags=["Revisor"],
        operation_id="reviewer_assignments_document",
        summary="Descargar el PDF sanitizado",
        description=(
            "Solo con la asignación `ACTIVE`; en otro estado responde 410. Entrega la copia "
            "sanitizada con nombre genérico, así que el original ni el nombre del archivo del Autor "
            "llegan al revisor. La descarga se audita antes; si falla, 503 sin redirigir."
        ),
        parameters=[ID],
        responses={
            (200, "application/pdf"): OpenApiTypes.BINARY,
            410: error_response("La asignación ya no permite descargar el documento."),
            503: error_response("La auditoría no está disponible (AUDIT_UNAVAILABLE)."),
        },
    ),
)
class ReviewerAssignmentDocumentView(ReviewerBaseView):
    """``GET /api/v1/reviewer/assignments/{id}/document/``: the sanitized PDF.

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


@extend_schema_view(
    get=extend_schema(
        tags=["Revisor"],
        operation_id="reviewer_assignment_evaluation_retrieve",
        summary="Ver mi evaluación (borrador o final)",
        description="Antes del primer guardado devuelve un borrador vacío con ETag `\"0\"`.",
        parameters=[ID],
        responses={200: ReviewerEvaluationSerializer},
    ),
    put=extend_schema(
        tags=["Revisor"],
        operation_id="reviewer_assignment_evaluation_save_draft",
        summary="Guardar el borrador",
        description=(
            "Cambia solo los campos enviados. Exige `If-Match` con el ETag leído (`\"0\"` para el "
            "borrador vacío). El servicio decide si la asignación todavía admite escritura."
        ),
        parameters=[ID, IF_MATCH],
        request=EvaluationDraftSerializer,
        responses={200: ReviewerEvaluationSerializer, 409: STATE_409},
    ),
)
class ReviewerEvaluationView(ReviewerBaseView):
    """``GET``/``PUT /api/v1/reviewer/assignments/{id}/evaluation/``: the private draft or the final.

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


@extend_schema_view(
    post=extend_schema(
        tags=["Revisor"],
        operation_id="reviewer_assignment_evaluation_submit",
        summary="Enviar la evaluación final",
        description="La evaluación final es inmutable. Exige `If-Match` con el ETag del borrador.",
        parameters=[ID, IF_MATCH],
        request=None,
        responses={200: ReviewerEvaluationSerializer, 409: STATE_409},
    ),
)
class ReviewerEvaluationSubmitView(ReviewerBaseView):
    """``POST /api/v1/reviewer/assignments/{id}/evaluation/submit/``: the immutable final."""

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


@extend_schema_view(
    post=extend_schema(
        tags=["Revisor"],
        operation_id="reviewer_assignment_conflict",
        summary="Declarar un conflicto de interés",
        description=(
            "Bloquea la evaluación (no más guardados ni envío) y avisa al Editor. La asignación "
            "sigue `ACTIVE` hasta que el Editor decida."
        ),
        parameters=[ID],
        request=DeclareConflictSerializer,
        responses={200: ReviewerEvaluationSerializer, 409: STATE_409},
    ),
)
class ReviewerConflictView(ReviewerBaseView):
    """``POST /api/v1/reviewer/assignments/{id}/conflict/``: declare a conflict of interest.

    Blocks the evaluation (no more saves or submission) and tells the
    editor; the assignment stays ``ACTIVE`` until the editor decides.
    """

    permission_classes = [IsAuthenticated, IsReviewer]

    def post(self, request: Request, pk) -> Response:
        self.get_assignment(pk)
        body = DeclareConflictSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        evaluation = declare_conflict(
            assignment_id=pk,
            reviewer=request.user,
            reason=(body.validated_data.get("reason") or "").strip() or None,
            context=audit_request_context(request),
        )
        return evaluation_response(evaluation)


class ReviewerHistoryBaseView(GenericAPIView):
    """The reviewer's own final evaluations, through the same scope as the inbox.

    Starting from :meth:`Assignment.objects.for_reviewer` keeps a
    withdrawn manuscript and one the reviewer co-authored out of the
    history. Drafts are never listed. The permission of the module role is
    enough here: :class:`IsAssignedReviewer` reads an object with a
    ``reviewer_id`` as an assignment, which an evaluation is not.
    """

    permission_classes = [IsAuthenticated, IsReviewer]

    def scoped_evaluations(self) -> QuerySet:
        own = Assignment.objects.for_reviewer(self.request.user).values("pk")
        latest_verdict = Verdict.objects.filter(evaluation=OuterRef("pk")).order_by(
            "-created_at", "-id"
        )
        return (
            Evaluation.objects.filter(assignment__in=own, status=Evaluation.Status.FINAL)
            .select_related("manuscript", "version")
            .annotate(
                editorial_decision=Subquery(latest_verdict.values("decision")[:1]),
                editorial_decided_at=Subquery(latest_verdict.values("created_at")[:1]),
            )
            .order_by("-submitted_at", "-id")
        )


@extend_schema_view(
    get=extend_schema(
        tags=["Revisor"],
        operation_id="reviewer_evaluations_list",
        summary="Historial de mis evaluaciones",
        description="Solo evaluaciones finales propias; los borradores nunca se listan.",
        parameters=PAGINATION,
        responses={200: ReviewerEvaluationHistorySerializer(many=True)},
    ),
)
class ReviewerEvaluationListView(ReviewerHistoryBaseView):
    """``GET /api/v1/reviewer/evaluations/``: history of the reviewer's final evaluations."""

    def get(self, request: Request) -> Response:
        page = self.paginate_queryset(self.scoped_evaluations())
        return self.get_paginated_response(
            ReviewerEvaluationHistorySerializer(page, many=True).data
        )


@extend_schema_view(
    get=extend_schema(
        tags=["Revisor"],
        operation_id="reviewer_evaluations_retrieve",
        summary="Ver una evaluación final",
        description="Solo lectura. Una evaluación ajena responde 404.",
        parameters=[ID],
        responses={200: ReviewerEvaluationHistoryDetailSerializer},
    ),
)
class ReviewerEvaluationDetailView(ReviewerHistoryBaseView):
    """``GET /api/v1/reviewer/evaluations/{id}/``: one final evaluation, read-only."""

    def get(self, request: Request, pk) -> Response:
        evaluation = get_object_or_404(self.scoped_evaluations(), pk=pk)
        return Response(ReviewerEvaluationHistoryDetailSerializer(evaluation).data)


@extend_schema_view(
    post=extend_schema(
        tags=["Revisor"],
        operation_id="reviewer_assignment_identity_leak",
        summary="Reportar una filtración de identidad",
        description=(
            "Reporte confidencial: no cambia la evaluación, el PDF ni el manuscrito, y el Autor "
            "nunca se entera. Solo el dueño de una asignación `ACTIVE`; un segundo reporte abierto "
            "responde 409."
        ),
        parameters=[ID],
        request=ReportIncidentSerializer,
        responses={201: ReviewerIncidentSerializer, 409: STATE_409},
    ),
)
class ReviewerIdentityLeakView(ReviewerBaseView):
    """``POST /api/v1/reviewer/assignments/{id}/identity-leak/``: a confidential report.

    Private: it changes neither the evaluation, the PDF nor the manuscript,
    and the author never learns it exists. Only the owner of an ``ACTIVE``
    assignment files it; a second open report answers ``409``.
    """

    permission_classes = [IsAuthenticated, IsReviewer]

    def post(self, request: Request, pk) -> Response:
        self.get_assignment(pk)
        body = ReportIncidentSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        incident = report_incident(
            assignment_id=pk,
            reviewer=request.user,
            report_type=body.validated_data["report_type"],
            description=body.validated_data["description"],
            context=audit_request_context(request),
        )
        return Response(ReviewerIncidentSerializer(incident).data, status=status.HTTP_201_CREATED)
