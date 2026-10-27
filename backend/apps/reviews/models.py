"""Domain models of reviewer assignments, evaluations and incidents (TSK-46, TSK-59).

They follow the implementation plan (sections 1.13, 1.14, 1.14.1 and 1.20):

* ``Assignment`` links one reviewer to one manuscript version. The
  database allows a single ``ACTIVE`` assignment per manuscript and fixes
  the deadline to exactly 20 days after ``assigned_at``.
* ``Evaluation`` is the reviewer's draft and, once ``FINAL``, the
  immutable evaluation. A trigger (migration ``0002``) rejects any
  ``UPDATE`` or ``DELETE`` over a ``FINAL`` row; the submission logic
  that performs the ``DRAFT`` → ``FINAL`` transition arrives in Phase 4.
* ``IncidentReport`` is the reviewer's confidential report of a possible
  identity leak (CA-HU-16-06). It only stores the report: it never
  touches the PDF, the evaluation or the manuscript status.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.db.models import BooleanField, ExpressionWrapper, F, Q
from django.db.models.functions import Now
from django.utils import timezone

from apps.publications.models import CorrectionRound, Manuscript, ManuscriptVersion

#: Calendar days a reviewer has to evaluate (RN-05).
ASSIGNMENT_DAYS = 20

#: Inclusive bounds of every evaluation score.
MIN_SCORE = 1
MAX_SCORE = 5

SCORE_FIELDS = (
    "originality_score",
    "methodology_score",
    "clarity_score",
    "relevance_score",
    "ethics_score",
)


class AssignmentQuerySet(models.QuerySet):
    """Scopes over assignments."""

    def with_overdue(self) -> "AssignmentQuerySet":
        """Annotate ``is_overdue``: ``ACTIVE`` and past ``due_at``, by the database clock.

        The scheduled task only marks ``EXPIRED`` later; the exact cut is
        always ``due_at <= now()`` evaluated by PostgreSQL.
        """
        return self.annotate(
            is_overdue=ExpressionWrapper(
                Q(status=Assignment.Status.ACTIVE, due_at__lte=Now()),
                output_field=BooleanField(),
            )
        )


class Assignment(models.Model):
    """Assignment of one reviewer to one version of a manuscript."""

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Activa"
        COMPLETED = "COMPLETED", "Completada"
        REVOKED = "REVOKED", "Revocada"
        EXPIRED = "EXPIRED", "Vencida"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    manuscript = models.ForeignKey(
        Manuscript,
        on_delete=models.PROTECT,
        related_name="assignments",
    )
    version = models.ForeignKey(
        ManuscriptVersion,
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
    assigned_at = models.DateTimeField(default=timezone.now)
    # Exactamente `assigned_at + 20 días`: la restricción CHECK lo valida y
    # el servicio de asignación (TSK-48) lo calcula en PostgreSQL.
    due_at = models.DateTimeField()
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.ACTIVE,
    )
    completed_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="revoked_assignments",
    )
    revocation_reason = models.TextField(null=True, blank=True)
    # Bloqueo optimista para `If-Match`/`ETag`.
    lock_version = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = AssignmentQuerySet.as_manager()

    class Meta:
        db_table = "reviews_assignment"
        ordering = ("-assigned_at",)
        indexes = [
            models.Index(
                fields=("reviewer", "status", "due_at"),
                name="idx_assignment_reviewer_due",
            ),
            models.Index(
                fields=("manuscript", "status"),
                # Django limita los nombres de índice a 30 caracteres.
                name="idx_assignment_ms_status",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=("ACTIVE", "COMPLETED", "REVOKED", "EXPIRED")),
                name="ck_assignment_status",
            ),
            # El plazo es de 20 días exactos, validado en la base de datos.
            models.CheckConstraint(
                condition=Q(
                    due_at=ExpressionWrapper(
                        F("assigned_at") + timedelta(days=ASSIGNMENT_DAYS),
                        output_field=models.DateTimeField(),
                    )
                ),
                name="ck_assignment_due_at",
            ),
            # Como máximo un Revisor activo por manuscrito.
            models.UniqueConstraint(
                fields=("manuscript",),
                condition=Q(status="ACTIVE"),
                name="uq_assignment_active",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.manuscript_id} · {self.reviewer_id} · {self.status}"


class Evaluation(models.Model):
    """Reviewer's private draft that becomes the immutable final evaluation."""

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Borrador"
        FINAL = "FINAL", "Final"

    class Recommendation(models.TextChoices):
        ACCEPT = "ACCEPT", "Aceptar"
        REQUIRES_CORRECTIONS = "REQUIRES_CORRECTIONS", "Requiere correcciones"
        REJECT = "REJECT", "Rechazar"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    assignment = models.OneToOneField(
        Assignment,
        on_delete=models.PROTECT,
        related_name="evaluation",
    )
    manuscript = models.ForeignKey(
        Manuscript,
        on_delete=models.PROTECT,
        related_name="evaluations",
    )
    version = models.ForeignKey(
        ManuscriptVersion,
        on_delete=models.PROTECT,
        related_name="evaluations",
    )
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="evaluations",
    )
    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    originality_score = models.SmallIntegerField(null=True, blank=True)
    methodology_score = models.SmallIntegerField(null=True, blank=True)
    clarity_score = models.SmallIntegerField(null=True, blank=True)
    relevance_score = models.SmallIntegerField(null=True, blank=True)
    ethics_score = models.SmallIntegerField(null=True, blank=True)
    recommendation = models.CharField(
        max_length=24,
        choices=Recommendation.choices,
        null=True,
        blank=True,
    )
    # Visibles para el Autor; obligatorios al enviar.
    comments_for_author = models.TextField(null=True, blank=True)
    # Solo para el Editor, nunca para el Autor.
    confidential_comments = models.TextField(null=True, blank=True)
    conflict_declared = models.BooleanField(default=False)
    submitted_at = models.DateTimeField(null=True, blank=True)
    # Bloqueo optimista del borrador para `If-Match`/`ETag`.
    lock_version = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "reviews_evaluation"
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("version", "reviewer"),
                name="uq_evaluation_version_reviewer",
            ),
            models.CheckConstraint(
                condition=Q(status__in=("DRAFT", "FINAL")),
                name="ck_evaluation_status",
            ),
            models.CheckConstraint(
                condition=Q(recommendation__isnull=True)
                | Q(recommendation__in=("ACCEPT", "REQUIRES_CORRECTIONS", "REJECT")),
                name="ck_evaluation_recommendation",
            ),
            *(
                models.CheckConstraint(
                    condition=Q(**{f"{field}__isnull": True})
                    | Q(**{f"{field}__gte": MIN_SCORE, f"{field}__lte": MAX_SCORE}),
                    name=f"ck_evaluation_{field}",
                )
                for field in SCORE_FIELDS
            ),
            # Una evaluación final está completa; el borrador admite huecos.
            models.CheckConstraint(
                condition=Q(status="DRAFT")
                | Q(
                    recommendation__isnull=False,
                    comments_for_author__isnull=False,
                    submitted_at__isnull=False,
                    **{f"{field}__isnull": False for field in SCORE_FIELDS},
                ),
                name="ck_evaluation_final_complete",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.assignment_id} · {self.status}"


class IncidentReport(models.Model):
    """Reviewer's confidential report about an assignment (CA-HU-16-06).

    The report is private to the reviewer and the editor; the author never
    sees it. The database allows one ``OPEN`` report per assignment and
    requires ``resolution`` and ``resolved_at`` once it is ``RESOLVED``.
    The effects of each resolution belong to the editor's service, not to
    this model.
    """

    class ReportType(models.TextChoices):
        IDENTITY_LEAK = "IDENTITY_LEAK", "Posible fuga de identidad"
        OTHER = "OTHER", "Otro"

    class Status(models.TextChoices):
        OPEN = "OPEN", "Abierto"
        RESOLVED = "RESOLVED", "Resuelto"

    class Resolution(models.TextChoices):
        REQUEST_ANONYMIZED_VERSION = (
            "REQUEST_ANONYMIZED_VERSION",
            "Solicitar versión anonimizada",
        )
        REASSIGN = "REASSIGN", "Reasignar"
        DISMISS = "DISMISS", "Descartar"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    assignment = models.ForeignKey(
        Assignment,
        on_delete=models.PROTECT,
        related_name="incident_reports",
    )
    manuscript = models.ForeignKey(
        Manuscript,
        on_delete=models.PROTECT,
        related_name="incident_reports",
    )
    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="incident_reports",
    )
    report_type = models.CharField(max_length=24, choices=ReportType.choices)
    description = models.TextField()
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.OPEN,
    )
    resolution = models.CharField(
        max_length=32,
        choices=Resolution.choices,
        null=True,
        blank=True,
    )
    # Ronda que abre `REQUEST_ANONYMIZED_VERSION`; nula en otro caso.
    correction_round = models.ForeignKey(
        CorrectionRound,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="incident_reports",
    )
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resolved_incident_reports",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "reviews_incident_report"
        ordering = ("-created_at",)
        indexes = [
            models.Index(
                fields=("status", "created_at"),
                name="idx_incident_status_date",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(report_type__in=("IDENTITY_LEAK", "OTHER")),
                name="ck_incident_report_type",
            ),
            models.CheckConstraint(
                condition=Q(status__in=("OPEN", "RESOLVED")),
                name="ck_incident_status",
            ),
            models.CheckConstraint(
                condition=Q(resolution__isnull=True)
                | Q(resolution__in=("REQUEST_ANONYMIZED_VERSION", "REASSIGN", "DISMISS")),
                name="ck_incident_resolution",
            ),
            # Un reporte resuelto registra cómo y cuándo se resolvió.
            models.CheckConstraint(
                condition=Q(status="OPEN")
                | Q(resolution__isnull=False, resolved_at__isnull=False),
                name="ck_incident_resolved_complete",
            ),
            # Un solo reporte abierto por asignación.
            models.UniqueConstraint(
                fields=("assignment",),
                condition=Q(status="OPEN"),
                name="uq_incident_open",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.assignment_id} · {self.report_type} · {self.status}"
