"""Domain models for manuscript submission, versioning and catalog.

This module models the editorial life cycle of a scientific manuscript,
including its immutable versions and the authorship metadata required to
classify submissions for the public catalog.
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.core.models import BaseModel


class ManuscriptStatus(models.TextChoices):
    """Enumerates the editorial life-cycle states of a manuscript."""

    DRAFT = "draft", "Borrador"
    RECEIVED = "received", "Recibido"
    UNDER_REVIEW = "under_review", "En Revisión"
    REQUIRES_CHANGES = "requires_changes", "Requiere Correcciones"
    ACCEPTED = "accepted", "Aceptado"
    REJECTED = "rejected", "Rechazado"
    PUBLISHED = "published", "Publicado"
    WITHDRAWN = "withdrawn", "Dado de baja"


class ResearchArea(BaseModel):
    """Thematic area of knowledge used to classify publications."""

    name = models.CharField(max_length=150, unique=True)
    code = models.CharField(max_length=20, unique=True)

    class Meta:
        """Metadata for the research area model."""

        db_table = "publications_research_area"
        verbose_name = "research area"
        verbose_name_plural = "research areas"
        ordering = ["name"]

    def __str__(self) -> str:
        """Return the area name."""
        return self.name


class Category(BaseModel):
    """Fine-grained category within a research area for catalog filters."""

    name = models.CharField(max_length=150)
    research_area = models.ForeignKey(
        ResearchArea,
        on_delete=models.PROTECT,
        related_name="categories",
    )

    class Meta:
        """Metadata for the category model."""

        db_table = "publications_category"
        verbose_name = "category"
        verbose_name_plural = "categories"
        constraints = [
            models.UniqueConstraint(
                fields=["name", "research_area"],
                name="publications_category_unique_per_area",
            )
        ]
        ordering = ["name"]

    def __str__(self) -> str:
        """Return the category name."""
        return self.name


class Manuscript(BaseModel):
    """A scientific work submitted to the editorial workflow.

    Attributes:
        title: Manuscript title (mandatory metadata).
        abstract: Structured summary of the work.
        keywords: Comma-separated keywords for catalog search.
        language: Primary language of the manuscript.
        status: Current position within the editorial life cycle.
        author: User who owns and manages the submission.
        research_area: Thematic area classifying the manuscript.
        category: Optional fine-grained category.
        submitted_at: Timestamp when the manuscript left the draft state.
    """

    title = models.CharField(max_length=300)
    abstract = models.TextField()
    keywords = models.CharField(max_length=300)
    language = models.CharField(max_length=10, default="es")
    status = models.CharField(
        max_length=20,
        choices=ManuscriptStatus.choices,
        default=ManuscriptStatus.DRAFT,
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="manuscripts",
    )
    research_area = models.ForeignKey(
        ResearchArea,
        on_delete=models.PROTECT,
        related_name="manuscripts",
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="manuscripts",
    )
    submitted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        """Metadata and indexes for the manuscript model."""

        db_table = "publications_manuscript"
        verbose_name = "manuscript"
        verbose_name_plural = "manuscripts"
        indexes = [
            models.Index(fields=["status"], name="pub_manuscript_status_idx"),
            models.Index(fields=["created_at"], name="pub_manuscript_created_idx"),
            models.Index(fields=["research_area"], name="pub_manuscript_area_idx"),
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        """Return the manuscript title."""
        return self.title

    @property
    def is_editable(self) -> bool:
        """Return whether metadata may still be edited (RF-21)."""
        return self.status in (
            ManuscriptStatus.DRAFT,
            ManuscriptStatus.REQUIRES_CHANGES,
        )

    def current_version(self) -> "ManuscriptVersion | None":
        """Return the most recent version, or ``None`` if not versioned yet."""
        return self.versions.order_by("-version_number").first()

    def can_accept_new_version(self) -> bool:
        """Return whether a corrected version may be uploaded (RF-06)."""
        return self.status == ManuscriptStatus.REQUIRES_CHANGES


class ManuscriptVersion(BaseModel):
    """Immutable snapshot of a manuscript delivered by the author.

    Versions are never overwritten; each corrected submission creates a new
    row with an incrementing ``version_number`` (RF-06, RNF-05).

    Attributes:
        manuscript: Owning manuscript.
        version_number: Sequential number of the version, unique per manuscript.
        file: Protected PDF deliverable.
        is_metadata_scrubbed: Whether author metadata was sanitized for blinding.
        notes: Optional change notes provided by the author.
    """

    manuscript = models.ForeignKey(
        Manuscript,
        on_delete=models.PROTECT,
        related_name="versions",
    )
    version_number = models.PositiveIntegerField()
    file = models.FileField(upload_to="manuscripts/%Y/%m/")
    is_metadata_scrubbed = models.BooleanField(default=False)
    notes = models.TextField(blank=True)

    class Meta:
        """Metadata and constraints for the manuscript version model."""

        db_table = "publications_manuscript_version"
        verbose_name = "manuscript version"
        verbose_name_plural = "manuscript versions"
        constraints = [
            models.UniqueConstraint(
                fields=["manuscript", "version_number"],
                name="publications_version_unique_number",
            )
        ]
        ordering = ["manuscript", "version_number"]

    def __str__(self) -> str:
        """Return an identifying label for the version."""
        return f"{self.manuscript_id} v{self.version_number}"

    def clean(self) -> None:
        """Validate that the version number is positive."""
        if self.version_number < 1:
            raise ValidationError("version_number must be greater than or equal to 1.")


class Author(BaseModel):
    """Authorship metadata linking a person to a manuscript.

    The identity stored here is deliberately kept in the publications domain so
    that review-facing representations can omit it (RNF-07).

    Attributes:
        manuscript: Owning manuscript.
        full_name: Name of the author as it must appear in the publication.
        affiliation: Institutional affiliation.
        email: Contact email.
        order: Author position within the authorship list.
        is_corresponding: Whether this author is the corresponding author.
    """

    manuscript = models.ForeignKey(
        Manuscript,
        on_delete=models.PROTECT,
        related_name="authors",
    )
    full_name = models.CharField(max_length=200)
    affiliation = models.CharField(max_length=250, blank=True)
    email = models.EmailField(blank=True)
    order = models.PositiveSmallIntegerField(default=1)
    is_corresponding = models.BooleanField(default=False)

    class Meta:
        """Metadata and constraints for the author model."""

        db_table = "publications_author"
        verbose_name = "author"
        verbose_name_plural = "authors"
        constraints = [
            models.UniqueConstraint(
                fields=["manuscript", "order"],
                name="publications_author_unique_order",
            )
        ]
        ordering = ["manuscript", "order"]

    def __str__(self) -> str:
        """Return the author full name."""
        return self.full_name
