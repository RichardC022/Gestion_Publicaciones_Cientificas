"""Domain models for blind peer review and editorial decisions.

The representations exposed to reviewers must never carry author identity, as
mandated by the double-blind principle (RNF-07). Author information is kept in
the publications domain and is intentionally not referenced here.
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.core.models import BaseModel
from apps.publications.models import Manuscript


class AssignmentStatus(models.TextChoices):
    """Enumerates the states of a review assignment."""

    PENDING = "pending", "Pendiente"
    IN_PROGRESS = "in_progress", "En Proceso"
    COMPLETED = "completed", "Completada"
    DECLINED = "declined", "Rechazada"


class Recommendation(models.TextChoices):
    """Enumerates a reviewer's technical recommendation."""

    ACCEPT = "accept", "Aceptar"
    MINOR_CHANGES = "minor_changes", "Cambios Menores"
    MAJOR_CHANGES = "major_changes", "Cambios Mayores"
    REJECT = "reject", "Rechazar"


class VerdictDecision(models.TextChoices):
    """Enumerates the editor's final decisions (RF-19)."""

    ACCEPTED = "accepted", "Aceptado"
    REJECTED = "rejected", "Rechazado"
    REQUIRES_CHANGES = "requires_changes", "Requiere Correcciones"


class ReviewAssignment(BaseModel):
    """Designation of a reviewer to evaluate a manuscript (RF-03).

    Attributes:
        manuscript: Manuscript under evaluation.
        reviewer: User acting as peer reviewer.
        assigned_by: Editor who created the assignment.
        status: Progress state of the assignment.
        due_date: Optional deadline for the evaluation.
    """

    manuscript = models.ForeignKey(
        Manuscript,
        on_delete=models.PROTECT,
        related_name="assignments",
    )
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="review_assignments",
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_assignments",
    )
    status = models.CharField(
        max_length=20,
        choices=AssignmentStatus.choices,
        default=AssignmentStatus.PENDING,
    )
    due_date = models.DateField(null=True, blank=True)

    class Meta:
        """Metadata and constraints for the review assignment model."""

        db_table = "reviews_assignment"
        verbose_name = "review assignment"
        verbose_name_plural = "review assignments"
        constraints = [
            models.UniqueConstraint(
                fields=["manuscript", "reviewer"],
                name="reviews_assignment_unique_reviewer",
            )
        ]
        indexes = [
            models.Index(fields=["status"], name="reviews_assignment_status_idx"),
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        """Return a label identifying the assignment."""
        return f"Assignment {self.pk} for manuscript {self.manuscript_id}"


class Evaluation(BaseModel):
    """Technical assessment recorded by a reviewer (RF-04, RF-18).

    Attributes:
        assignment: Review assignment this evaluation belongs to.
        observations: Reviewer's comments and justification.
        recommendation: Structured recommendation to the editor.
        submitted_at: Timestamp when the evaluation was submitted.
    """

    assignment = models.OneToOneField(
        ReviewAssignment,
        on_delete=models.PROTECT,
        related_name="evaluation",
    )
    observations = models.TextField()
    recommendation = models.CharField(
        max_length=20,
        choices=Recommendation.choices,
    )
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        """Metadata for the evaluation model."""

        db_table = "reviews_evaluation"
        verbose_name = "evaluation"
        verbose_name_plural = "evaluations"

    def __str__(self) -> str:
        """Return a label identifying the evaluation."""
        return f"Evaluation {self.pk} of assignment {self.assignment_id}"


class ReviewVerdict(BaseModel):
    """Final editorial resolution for a manuscript (RF-07, RF-19).

    Attributes:
        manuscript: Manuscript the verdict resolves.
        decided_by: Editor who issued the verdict.
        decision: Final decision taken.
        observations: Justification sent to the author.
    """

    manuscript = models.ForeignKey(
        Manuscript,
        on_delete=models.PROTECT,
        related_name="verdicts",
    )
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="issued_verdicts",
    )
    decision = models.CharField(
        max_length=20,
        choices=VerdictDecision.choices,
    )
    observations = models.TextField(blank=True)

    class Meta:
        """Metadata and constraints for the verdict model."""

        db_table = "reviews_verdict"
        verbose_name = "review verdict"
        verbose_name_plural = "review verdicts"
        indexes = [
            models.Index(fields=["decision"], name="reviews_verdict_decision_idx"),
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        """Return a label identifying the verdict."""
        return f"Verdict {self.decision} for manuscript {self.manuscript_id}"

    def clean(self) -> None:
        """Validate that a verdict is only issued after an evaluation exists."""
        if (
            self.manuscript_id
            and not self.manuscript.assignments.filter(
                evaluation__isnull=False
            ).exists()
        ):
            raise ValidationError(
                "A verdict cannot be issued before at least one evaluation exists."
            )
