"""Role-specific serializers of the manuscript module (plan section 2.9).

The double-blind and confidentiality rules rely on separate allowlist
serializers, never on one serializer with conditional ``exclude``:

* :class:`AuthorManuscriptSerializer` — the author's own manuscript: its
  authors, state, round, version and the editable metadata. It never
  carries the reviewer's identity, confidential comments or scores.
* :class:`AuthorEvaluationFeedbackSerializer` — the only view of an
  evaluation the author gets: the comments written for them, the
  verdict and the editor's observations.
* :class:`EditorManuscriptSerializer` — the editor's read-only view,
  with the authors' contact data and the versions.
"""

from __future__ import annotations

import re

from rest_framework import serializers

from apps.publications.models import Manuscript, ManuscriptAuthor, ManuscriptVersion
from apps.users.serializers import SessionUserSerializer

#: ISO 639-1 language code (plan section 1.8).
LANGUAGE_PATTERN = re.compile(r"^[a-z]{2}$")

#: Metadata the formal submission requires (CA-HU-04-02). A draft may
#: leave them empty; a manuscript under correction may not blank them.
REQUIRED_METADATA = ("title", "abstract", "keywords", "area", "language")


class ManuscriptAuthorSerializer(serializers.ModelSerializer):
    """Author with affiliation and contact; the order is the list position."""

    class Meta:
        model = ManuscriptAuthor
        fields = ("full_name", "email", "affiliation", "is_corresponding", "author_order")
        read_only_fields = ("author_order",)


class ManuscriptVersionSummarySerializer(serializers.ModelSerializer):
    """Version row of the editor's view: file name, size and integrity seal."""

    class Meta:
        model = ManuscriptVersion
        fields = (
            "id",
            "version_number",
            "round_number",
            "original_filename",
            "original_size_bytes",
            "original_sha256",
            "submitted_at",
        )
        read_only_fields = fields


class AuthorEvaluationFeedbackSerializer(serializers.Serializer):
    """What the author may read of an evaluation (CA double-blind).

    Allowlist of three fields: the reviewer's identity, the confidential
    comments and the scores are never part of it.
    """

    comments_for_author = serializers.CharField(read_only=True)
    decision = serializers.CharField(read_only=True)
    observations = serializers.CharField(read_only=True, allow_null=True)


def draft_file_summary(manuscript: Manuscript) -> dict | None:
    """Name, size and date of the attached draft PDF; never its path."""
    if not manuscript.draft_file_path:
        return None
    return {
        "filename": manuscript.draft_filename,
        "size_bytes": manuscript.draft_size_bytes,
        "uploaded_at": serializers.DateTimeField().to_representation(
            manuscript.draft_uploaded_at
        ),
    }


class AuthorManuscriptSerializer(serializers.ModelSerializer):
    """The author's own manuscript; also validates the writable metadata."""

    authors = ManuscriptAuthorSerializer(many=True, allow_empty=False)
    keywords = serializers.ListField(
        child=serializers.CharField(max_length=100),
        required=False,
        allow_empty=True,
    )
    draft_file = serializers.SerializerMethodField()

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
            "status",
            "current_round",
            "current_version",
            "is_active",
            "withdrawn_at",
            "withdrawal_reason",
            "authors",
            "draft_file",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "code",
            "status",
            "current_round",
            "current_version",
            "is_active",
            "withdrawn_at",
            "withdrawal_reason",
            "created_at",
            "updated_at",
        )
        extra_kwargs = {
            # Un borrador se guarda parcialmente (CA-HU-04-01).
            "title": {"required": False, "allow_blank": True},
            "abstract": {"required": False, "allow_blank": True},
            "area": {"required": False, "allow_blank": True},
            "language": {"required": False, "allow_blank": True},
        }

    def get_draft_file(self, obj: Manuscript) -> dict | None:
        return draft_file_summary(obj)

    def validate_language(self, value: str) -> str:
        value = value.strip().lower()
        if value and not LANGUAGE_PATTERN.match(value):
            raise serializers.ValidationError(
                "Use un código de idioma ISO 639-1 de dos letras."
            )
        return value

    def validate_authors(self, value: list[dict]) -> list[dict]:
        """At least one author, exactly one corresponding, the registrant listed."""
        emails = [author["email"].lower() for author in value]
        if len(set(emails)) != len(emails):
            raise serializers.ValidationError("Un mismo correo no puede repetirse entre los autores.")

        corresponding = sum(1 for author in value if author.get("is_corresponding"))
        if corresponding != 1:
            raise serializers.ValidationError("Debe indicar exactamente un autor responsable.")

        user = self.context["request"].user
        if user.email.lower() not in emails:
            raise serializers.ValidationError(
                "El autor que registra el manuscrito debe figurar en la lista de autores."
            )
        return value

    def validate(self, attrs: dict) -> dict:
        """A manuscript under correction keeps its required metadata complete."""
        instance = self.instance
        if instance is not None and instance.status == Manuscript.Status.REQUIRES_CORRECTIONS:
            errors = {
                field: ["Este campo no puede quedar vacío."]
                for field in REQUIRED_METADATA
                if field in attrs and not attrs[field]
            }
            if errors:
                raise serializers.ValidationError(errors)
        return attrs


class EditorManuscriptSerializer(serializers.ModelSerializer):
    """Read-only editor view: metadata, authors with contact and versions."""

    authors = ManuscriptAuthorSerializer(many=True, read_only=True)
    versions = ManuscriptVersionSummarySerializer(many=True, read_only=True)
    created_by = SessionUserSerializer(read_only=True)

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
            "status",
            "current_round",
            "current_version",
            "is_active",
            "withdrawn_at",
            "withdrawal_reason",
            "created_by",
            "authors",
            "versions",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


def manuscript_serializer_class(manuscript: Manuscript, user) -> type[serializers.ModelSerializer]:
    """The owner reads the author view; anyone else reaches it as editor."""
    if manuscript.created_by_id == user.id:
        return AuthorManuscriptSerializer
    return EditorManuscriptSerializer
