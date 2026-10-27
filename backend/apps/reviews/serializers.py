"""Serializers of the editor module (plan section 2.4).

The editor is the only role that sees the reviewer's identity, so these
allowlists are never shared with the author or reviewer modules.
"""

from __future__ import annotations

from django.urls import reverse
from rest_framework import serializers

from apps.publications.models import Manuscript, Verdict
from apps.publications.serializers import (
    EditorManuscriptSerializer,
    HistoryEntrySerializer,
    ManuscriptVersionSummarySerializer,
)
from apps.publications.services.history import build_history
from apps.reviews.models import Assignment, Evaluation
from apps.reviews.services.assignments import RevocationCause
from apps.users.models import User


class PersonSerializer(serializers.ModelSerializer):
    """Name and contact of an account."""

    full_name = serializers.CharField(source="get_full_name", read_only=True)

    class Meta:
        model = User
        fields = ("id", "full_name", "email")
        read_only_fields = fields


class SubmissionListSerializer(serializers.ModelSerializer):
    """Row of the editor's inbox; ``submitted_at`` is annotated by the view."""

    submitted_at = serializers.DateTimeField(read_only=True)

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
            "submitted_at",
            "created_at",
        )
        read_only_fields = fields


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
