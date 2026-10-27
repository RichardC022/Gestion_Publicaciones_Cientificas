"""Serializers of the editor and reviewer modules (plan sections 2.4 and 2.9).

The editor is the only role that sees the reviewer's identity, so the
editor allowlists are never shared with the author or reviewer modules.
The reviewer ones are separate, explicit allowlists: the double-blind
rule never depends on an ``exclude`` or on a conditional field.
"""

from __future__ import annotations

from django.urls import reverse
from rest_framework import serializers

from apps.publications.models import Manuscript, ManuscriptVersion, Verdict
from apps.publications.serializers import (
    EditorManuscriptSerializer,
    HistoryEntrySerializer,
    ManuscriptVersionSummarySerializer,
)
from apps.publications.services.history import build_history
from apps.reviews.models import (
    MAX_SCORE,
    MIN_SCORE,
    SCORE_FIELDS,
    Assignment,
    Evaluation,
    IncidentReport,
)
from apps.reviews.services.assignments import RevocationCause
from apps.reviews.services.inbox import inbox_state
from apps.users.models import User


class PersonSerializer(serializers.ModelSerializer):
    """Name and contact of an account."""

    full_name = serializers.CharField(source="get_full_name", read_only=True)

    class Meta:
        model = User
        fields = ("id", "full_name", "email")
        read_only_fields = fields


class SubmissionListSerializer(serializers.ModelSerializer):
    """Row of the editor's inbox; ``submitted_at`` is annotated by the view.

    ``corresponding_author`` is only a name: the full roster, contacts and
    affiliations are in the detail. The view prefetches ``authors``.
    """

    submitted_at = serializers.DateTimeField(read_only=True)
    corresponding_author = serializers.SerializerMethodField()

    class Meta:
        model = Manuscript
        fields = (
            "id",
            "code",
            "title",
            "area",
            "language",
            "status",
            "current_round",
            "current_version",
            "corresponding_author",
            "submitted_at",
            "created_at",
        )
        read_only_fields = fields

    def get_corresponding_author(self, obj: Manuscript) -> str | None:
        """The corresponding author's name, or the first author's if none is marked."""
        authors = list(obj.authors.all())
        chosen = next((a for a in authors if a.is_corresponding), authors[0] if authors else None)
        return chosen.full_name if chosen else None


class EditorVersionSerializer(ManuscriptVersionSummarySerializer):
    """Version with the API path of its PDF, never the volume path."""

    file_url = serializers.SerializerMethodField()

    class Meta(ManuscriptVersionSummarySerializer.Meta):
        fields = (*ManuscriptVersionSummarySerializer.Meta.fields, "file_url")
        read_only_fields = fields

    def get_file_url(self, obj) -> str:
        return reverse(
            "manuscript-version-file",
            kwargs={"pk": obj.manuscript_id, "version_id": obj.pk},
        )


class AssignmentSerializer(serializers.ModelSerializer):
    """Assignment with the reviewer's identity, for the editor only."""

    reviewer = PersonSerializer(read_only=True)
    assigned_by = PersonSerializer(read_only=True)
    revoked_by = PersonSerializer(read_only=True)
    manuscript_code = serializers.CharField(source="manuscript.code", read_only=True)
    manuscript_title = serializers.CharField(source="manuscript.title", read_only=True)
    version_number = serializers.IntegerField(source="version.version_number", read_only=True)
    # Anotado con `due_at <= now()` de PostgreSQL (`with_overdue`).
    is_overdue = serializers.BooleanField(read_only=True)

    class Meta:
        model = Assignment
        fields = (
            "id",
            "manuscript",
            "manuscript_code",
            "manuscript_title",
            "version_number",
            "reviewer",
            "assigned_by",
            "assigned_at",
            "due_at",
            "status",
            "is_overdue",
            "completed_at",
            "revoked_at",
            "revoked_by",
            "revocation_reason",
        )
        read_only_fields = fields


class SubmissionDetailSerializer(EditorManuscriptSerializer):
    """Full submission: metadata, authors, PDFs, history and open assignment."""

    versions = EditorVersionSerializer(many=True, read_only=True)
    history = serializers.SerializerMethodField()
    open_assignment = serializers.SerializerMethodField()

    class Meta(EditorManuscriptSerializer.Meta):
        fields = (*EditorManuscriptSerializer.Meta.fields, "history", "open_assignment")
        read_only_fields = fields

    def get_history(self, obj: Manuscript) -> list[dict]:
        return HistoryEntrySerializer(build_history(obj), many=True).data

    def get_open_assignment(self, obj: Manuscript) -> dict | None:
        """The active or expired assignment waiting for the editor, if any."""
        assignment = (
            obj.assignments.filter(
                status__in=(Assignment.Status.ACTIVE, Assignment.Status.EXPIRED)
            )
            .select_related("reviewer", "assigned_by", "revoked_by", "manuscript", "version")
            .with_overdue()
            .first()
        )
        if assignment is None:
            return None
        return AssignmentSerializer(assignment, context=self.context).data


class EligibleReviewerSerializer(serializers.ModelSerializer):
    """Candidate reviewer with expertise and current load."""

    full_name = serializers.CharField(source="get_full_name", read_only=True)
    expertise_areas = serializers.ListField(
        source="reviewer_profile.expertise_areas", read_only=True
    )
    max_active_assignments = serializers.IntegerField(
        source="reviewer_profile.max_active_assignments", read_only=True
    )
    active_assignments = serializers.IntegerField(read_only=True)

    class Meta:
        model = User
        fields = (
            "id",
            "institutional_id",
            "full_name",
            "email",
            "expertise_areas",
            "max_active_assignments",
            "active_assignments",
        )
        read_only_fields = fields


class ReviewerFilterSerializer(serializers.Serializer):
    """Query string of ``GET /api/editor/reviewers/``."""

    manuscript_id = serializers.UUIDField(required=False)
    area = serializers.CharField(max_length=120, required=False)


class StartReviewSerializer(serializers.Serializer):
    """Body of ``start-review``: the reviewer is optional."""

    reviewer_id = serializers.UUIDField(required=False)


class AssignReviewerSerializer(serializers.Serializer):
    """Body of ``POST .../assignments/``."""

    reviewer_id = serializers.UUIDField()


class RevokeAssignmentSerializer(serializers.Serializer):
    """Body of ``POST .../revoke/``: the cause and a written reason."""

    cause = serializers.ChoiceField(choices=RevocationCause.choices)
    reason = serializers.CharField(max_length=2000, trim_whitespace=True)


class EditorEvaluationSerializer(serializers.ModelSerializer):
    """A final evaluation as the editor reads it: reviewer identity and confidential notes.

    It is an allowlist for the editor module only. The author gets
    :class:`~apps.publications.serializers.AuthorEvaluationFeedbackSerializer`
    and the reviewer's identity never reaches any other role.
    """

    reviewer = PersonSerializer(read_only=True)
    version_number = serializers.IntegerField(source="version.version_number", read_only=True)

    class Meta:
        model = Evaluation
        fields = (
            "id",
            "assignment",
            "version_number",
            "reviewer",
            "status",
            "originality_score",
            "methodology_score",
            "clarity_score",
            "relevance_score",
            "ethics_score",
            "recommendation",
            "comments_for_author",
            "confidential_comments",
            "conflict_declared",
            "submitted_at",
        )
        read_only_fields = fields


class VerdictSerializer(serializers.ModelSerializer):
    """A registered verdict; read-only, because verdicts are never edited."""

    editor = PersonSerializer(read_only=True)
    version_number = serializers.IntegerField(source="version.version_number", read_only=True)

    class Meta:
        model = Verdict
        fields = (
            "id",
            "decision",
            "justification",
            "observations",
            "version_number",
            "evaluation",
            "editor",
            "previous_verdict",
            "created_at",
        )
        read_only_fields = fields


class RegisterVerdictSerializer(serializers.Serializer):
    """Body of ``POST /api/editor/manuscripts/{id}/verdicts/``.

    Only the decision and its texts: the evaluated version, the evaluation
    and the editor come from the manuscript and the session. Whether a
    text is mandatory depends on the decision and the evaluation, which
    the service checks under the manuscript lock.
    """

    decision = serializers.ChoiceField(choices=Verdict.Decision.choices)
    justification = serializers.CharField(
        required=False, allow_blank=True, allow_null=True, max_length=5000
    )
    observations = serializers.CharField(
        required=False, allow_blank=True, allow_null=True, max_length=5000
    )


class ReviewerManuscriptSerializer(serializers.ModelSerializer):
    """The manuscript as its reviewer sees it: content, never authorship.

    Allowlist for the reviewer module (plan section 2.9, layer 2). It has
    no authors, affiliations, contact data, ``created_by`` or status
    history, and no file name of the author.
    """

    class Meta:
        model = Manuscript
        fields = (
            "id",
            "code",
            "title",
            "abstract",
            "keywords",
            "area",
            "language",
            "current_round",
            "current_version",
        )
        read_only_fields = fields


class ReviewerVersionSerializer(serializers.ModelSerializer):
    """The assigned version as its reviewer sees it: numbers and date only.

    It has no original file name, metadata snapshot, ``submitted_by``,
    paths or hashes. The download name is built from the manuscript code.
    """

    class Meta:
        model = ManuscriptVersion
        fields = ("version_number", "round_number", "submitted_at")
        read_only_fields = fields


class ReviewerAssignmentSerializer(serializers.ModelSerializer):
    """Row of the reviewer's inbox: the assignment and its blind manuscript summary.

    ``is_overdue`` and ``has_evaluation`` are annotated by the view
    (``with_overdue`` and ``with_evaluation_started``). It carries no
    authorship and no identity of the editor who assigned it.
    """

    manuscript_code = serializers.CharField(source="manuscript.code", read_only=True)
    manuscript_title = serializers.CharField(source="manuscript.title", read_only=True)
    area = serializers.CharField(source="manuscript.area", read_only=True)
    version_number = serializers.IntegerField(source="version.version_number", read_only=True)
    round_number = serializers.IntegerField(source="version.round_number", read_only=True)
    is_overdue = serializers.BooleanField(read_only=True)
    state = serializers.SerializerMethodField()

    class Meta:
        model = Assignment
        fields = (
            "id",
            "manuscript_code",
            "manuscript_title",
            "area",
            "version_number",
            "round_number",
            "assigned_at",
            "due_at",
            "status",
            "state",
            "is_overdue",
            "completed_at",
        )
        read_only_fields = fields

    def get_state(self, obj: Assignment) -> str:
        return inbox_state(
            status=obj.status, is_overdue=obj.is_overdue, has_evaluation=obj.has_evaluation
        ).value


class ReviewerAssignmentDetailSerializer(ReviewerAssignmentSerializer):
    """One assignment with the blind manuscript, the assigned version and the PDF path.

    ``document_url`` is the API path, never the volume path, and only
    while the assignment is ``ACTIVE``: any other status gets ``410``.
    """

    manuscript = ReviewerManuscriptSerializer(read_only=True)
    version = ReviewerVersionSerializer(read_only=True)
    document_url = serializers.SerializerMethodField()

    class Meta(ReviewerAssignmentSerializer.Meta):
        fields = (*ReviewerAssignmentSerializer.Meta.fields, "manuscript", "version", "document_url")
        read_only_fields = fields

    def get_document_url(self, obj: Assignment) -> str | None:
        if obj.status != Assignment.Status.ACTIVE:
            return None
        return reverse("reviewer-assignment-document", kwargs={"pk": obj.pk})


class ReviewerEvaluationSerializer(serializers.ModelSerializer):
    """The reviewer's own draft or final evaluation, confidential notes included.

    The optimistic lock travels in the ``ETag`` header, not in the body.
    An evaluation that was not saved yet is shown as an empty draft.
    """

    class Meta:
        model = Evaluation
        fields = (
            "id",
            "status",
            "originality_score",
            "methodology_score",
            "clarity_score",
            "relevance_score",
            "ethics_score",
            "recommendation",
            "comments_for_author",
            "confidential_comments",
            "conflict_declared",
            "submitted_at",
        )
        read_only_fields = fields


class EvaluationDraftSerializer(serializers.Serializer):
    """Body of ``PUT .../evaluation/``: every field optional, a gap is a valid draft.

    Only the keys sent are changed, and nothing else is accepted: the
    status, the conflict flag and the lock can never be set from here.
    """

    originality_score = serializers.IntegerField(
        min_value=MIN_SCORE, max_value=MAX_SCORE, required=False, allow_null=True
    )
    methodology_score = serializers.IntegerField(
        min_value=MIN_SCORE, max_value=MAX_SCORE, required=False, allow_null=True
    )
    clarity_score = serializers.IntegerField(
        min_value=MIN_SCORE, max_value=MAX_SCORE, required=False, allow_null=True
    )
    relevance_score = serializers.IntegerField(
        min_value=MIN_SCORE, max_value=MAX_SCORE, required=False, allow_null=True
    )
    ethics_score = serializers.IntegerField(
        min_value=MIN_SCORE, max_value=MAX_SCORE, required=False, allow_null=True
    )
    recommendation = serializers.ChoiceField(
        choices=Evaluation.Recommendation.choices, required=False, allow_null=True
    )
    comments_for_author = serializers.CharField(
        required=False, allow_blank=True, allow_null=True, max_length=10000
    )
    confidential_comments = serializers.CharField(
        required=False, allow_blank=True, allow_null=True, max_length=10000
    )


class DeclareConflictSerializer(serializers.Serializer):
    """Body of ``POST .../conflict/``: an optional reason, kept in the audit trail only."""

    reason = serializers.CharField(
        required=False, allow_blank=True, allow_null=True, max_length=2000
    )


class ReviewerEvaluationHistorySerializer(serializers.ModelSerializer):
    """Row of the reviewer's history: a final evaluation of their own, read-only.

    Anonymized by construction: the manuscript is identified by code,
    title and area, and the editorial result is only the decision and its
    date — never the justification or the observations the editor wrote
    for the author. ``editorial_decision`` and ``editorial_decided_at``
    are annotated by the view from the latest verdict, if any.
    """

    manuscript_code = serializers.CharField(source="manuscript.code", read_only=True)
    manuscript_title = serializers.CharField(source="manuscript.title", read_only=True)
    area = serializers.CharField(source="manuscript.area", read_only=True)
    version_number = serializers.IntegerField(source="version.version_number", read_only=True)
    round_number = serializers.IntegerField(source="version.round_number", read_only=True)
    editorial_result = serializers.SerializerMethodField()

    class Meta:
        model = Evaluation
        fields = (
            "id",
            "assignment",
            "manuscript_code",
            "manuscript_title",
            "area",
            "version_number",
            "round_number",
            "recommendation",
            "submitted_at",
            "editorial_result",
        )
        read_only_fields = fields

    def get_editorial_result(self, obj: Evaluation) -> dict | None:
        if obj.editorial_decision is None:
            return None
        return {"decision": obj.editorial_decision, "decided_at": obj.editorial_decided_at}


class ReviewerEvaluationHistoryDetailSerializer(ReviewerEvaluationHistorySerializer):
    """A final evaluation in full, for reading: scores and the comments for the author.

    The confidential comments are left out on purpose (CA-HU-17): they are
    for the editor and no history read-back carries them.
    """

    class Meta(ReviewerEvaluationHistorySerializer.Meta):
        fields = (
            *ReviewerEvaluationHistorySerializer.Meta.fields,
            *SCORE_FIELDS,
            "comments_for_author",
        )
        read_only_fields = fields


class ReportIncidentSerializer(serializers.Serializer):
    """Body of ``POST .../identity-leak/``: the type and a non-blank description."""

    report_type = serializers.ChoiceField(choices=IncidentReport.ReportType.choices)
    description = serializers.CharField(max_length=5000, trim_whitespace=True)


class ReviewerIncidentSerializer(serializers.ModelSerializer):
    """What the reporter gets back: the receipt, not the text nor anything editorial."""

    class Meta:
        model = IncidentReport
        fields = ("id", "assignment", "report_type", "status", "created_at")
        read_only_fields = fields


class EditorIncidentSerializer(serializers.ModelSerializer):
    """A confidential report as the editor reads it, with the reporter's identity.

    The editor module is the only place that exposes the description and
    the reviewer; the author never reaches either.
    """

    reporter = PersonSerializer(read_only=True)
    resolved_by = PersonSerializer(read_only=True)
    manuscript_code = serializers.CharField(source="manuscript.code", read_only=True)
    manuscript_title = serializers.CharField(source="manuscript.title", read_only=True)
    correction_round_number = serializers.IntegerField(
        source="correction_round.round_number", read_only=True, default=None
    )

    class Meta:
        model = IncidentReport
        fields = (
            "id",
            "status",
            "report_type",
            "description",
            "manuscript",
            "manuscript_code",
            "manuscript_title",
            "assignment",
            "reporter",
            "created_at",
            "resolution",
            "resolved_by",
            "resolved_at",
            "correction_round_number",
        )
        read_only_fields = fields


class ResolveIncidentSerializer(serializers.Serializer):
    """Body of ``POST .../resolve/``: the one resolution chosen."""

    resolution = serializers.ChoiceField(choices=IncidentReport.Resolution.choices)
