"""The reviewer's draft and final evaluation (TSK-62).

Both actions start from :meth:`Assignment.objects.for_reviewer` and lock
the assignment row, so a revocation, an expiration and a save or a
submission see each other's result instead of racing. The rules:

* Only an ``ACTIVE`` assignment before ``due_at`` accepts writes. The
  cut is the database clock: ``now() == due_at`` is already late and
  answers ``410``; the draft is kept and never becomes final.
* ``lock_version`` is the optimistic lock (``If-Match``/``ETag``): a stale
  value answers ``409`` and keeps the winning edit.
* A draft admits gaps. The final submission needs the five scores, the
  recommendation and the comments for the author; it completes the
  assignment in the same transaction, audits it, and announces it after
  the commit. A ``FINAL`` evaluation is immutable (trigger of migration
  ``0002``); the service also refuses to touch it.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from django.db import transaction
from django.db.models.functions import Now

from apps.audit.models import AuditLog
from apps.audit.services import AuditService
from apps.reviews.models import SCORE_FIELDS, Assignment, Evaluation
from apps.reviews.services.assignments import run_audited
from apps.reviews.signals import announce, evaluation_submitted
from apps.users.models import Role, User
from config.exceptions import DomainError, ErrorCode

#: What the reviewer writes in a draft; nothing else is ever taken from the client.
DRAFT_FIELDS = (*SCORE_FIELDS, "recommendation", "comments_for_author", "confidential_comments")

#: What the final submission requires (``confidential_comments`` stays optional).
REQUIRED_FIELDS = (*SCORE_FIELDS, "recommendation", "comments_for_author")

NOT_FOUND_MESSAGE = "No encontrado."
SUBMITTED_MESSAGE = "La evaluación ya fue enviada y no admite cambios."
REVOKED_MESSAGE = "La asignación fue revocada y no admite evaluación."
OVERDUE_MESSAGE = "El plazo de evaluación venció. El borrador se conserva sin enviarse."
CONFLICT_DECLARED_MESSAGE = "Se declaró un conflicto de interés: la evaluación está bloqueada."
STALE_MESSAGE = "El borrador cambió desde que lo leyó. Recárguelo antes de continuar."
MISSING_MESSAGE = "Este campo es obligatorio para enviar la evaluación."


def _locked_assignment(assignment_id: UUID, reviewer: User) -> Assignment:
    """The reviewer's own assignment, locked; anything else answers ``404``."""
    try:
        return (
            Assignment.objects.for_reviewer(reviewer)
            .select_for_update(of=("self",))
            .get(pk=assignment_id)
        )
    except Assignment.DoesNotExist as exc:
        raise DomainError(NOT_FOUND_MESSAGE, code=ErrorCode.NOT_FOUND) from exc


def _ensure_open(assignment: Assignment) -> None:
    """Only an ``ACTIVE`` assignment before ``due_at`` (database clock) accepts writes."""
    if assignment.status == Assignment.Status.COMPLETED:
        raise DomainError(
            SUBMITTED_MESSAGE,
            code=ErrorCode.STATE_CONFLICT,
            details={"status": assignment.status},
        )
    if assignment.status == Assignment.Status.REVOKED:
        raise DomainError(
            REVOKED_MESSAGE,
            code=ErrorCode.STATE_CONFLICT,
            details={"status": assignment.status},
        )
    overdue = assignment.status == Assignment.Status.EXPIRED or Assignment.objects.filter(
        pk=assignment.pk, due_at__lte=Now()
    ).exists()
    if overdue:
        raise DomainError(OVERDUE_MESSAGE, code=ErrorCode.STATE_CONFLICT, status_code=410)


def _current_evaluation(assignment: Assignment, expected_lock_version: int) -> Evaluation | None:
    """The locked evaluation of the assignment, if any, once its lock matches."""
    evaluation = Evaluation.objects.select_for_update().filter(assignment=assignment).first()
    if evaluation is not None and evaluation.status == Evaluation.Status.FINAL:
        raise DomainError(SUBMITTED_MESSAGE, code=ErrorCode.STATE_CONFLICT)
    if evaluation is not None and evaluation.conflict_declared:
        raise DomainError(CONFLICT_DECLARED_MESSAGE, code=ErrorCode.STATE_CONFLICT)
    current = evaluation.lock_version if evaluation is not None else 0
    if current != expected_lock_version:
        raise DomainError(
            STALE_MESSAGE,
            code=ErrorCode.VERSION_CONFLICT,
            details={"lock_version": current},
        )
    return evaluation


def _normalized(values: dict[str, Any]) -> dict[str, Any]:
    """Keep only the draft fields; blank text is the same as no text."""
    cleaned: dict[str, Any] = {}
    for field in DRAFT_FIELDS:
        if field not in values:
            continue
        value = values[field]
        if isinstance(value, str):
            value = value.strip() or None
        cleaned[field] = value
    return cleaned


def save_draft(
    *, assignment_id: UUID, reviewer: User, values: dict[str, Any], expected_lock_version: int
) -> Evaluation:
    """Create or update the private draft; only the fields given are changed."""
    with transaction.atomic():
        assignment = _locked_assignment(assignment_id, reviewer)
        _ensure_open(assignment)
        evaluation = _current_evaluation(assignment, expected_lock_version)
        changes = _normalized(values)
        if evaluation is None:
            # Nace en 1: el borrador vacío que muestra el GET es el 0, así que dos
            # pestañas que parten de él no se pisan en silencio.
            return Evaluation.objects.create(
                assignment=assignment,
                manuscript=assignment.manuscript,
                version=assignment.version,
                reviewer=reviewer,
                lock_version=1,
                **changes,
            )
        for field, value in changes.items():
            setattr(evaluation, field, value)
        evaluation.lock_version += 1
        evaluation.save(update_fields=(*changes, "lock_version", "updated_at"))
        return evaluation


def _missing_fields(evaluation: Evaluation | None) -> list[str]:
    if evaluation is None:
        return list(REQUIRED_FIELDS)
    return [field for field in REQUIRED_FIELDS if getattr(evaluation, field) in (None, "")]


def submit_evaluation(
    *, assignment_id: UUID, reviewer: User, expected_lock_version: int, context: dict
) -> Evaluation:
    """Turn the draft into the immutable final evaluation and complete the assignment.

    Everything commits together with its audit event, or nothing does: an
    unavailable audit trail answers ``503`` and the draft stays a draft.
    """

    def work() -> Evaluation:
        assignment = _locked_assignment(assignment_id, reviewer)
        _ensure_open(assignment)
        evaluation = _current_evaluation(assignment, expected_lock_version)
        missing = _missing_fields(evaluation)
        if missing:
            raise DomainError(
                "Complete la evaluación antes de enviarla.",
                code=ErrorCode.VALIDATION_ERROR,
                details={field: [MISSING_MESSAGE] for field in missing},
            )

        evaluation.status = Evaluation.Status.FINAL
        evaluation.submitted_at = Now()
        evaluation.lock_version += 1
        evaluation.save(update_fields=("status", "submitted_at", "lock_version", "updated_at"))

        assignment.status = Assignment.Status.COMPLETED
        assignment.completed_at = Now()
        assignment.lock_version += 1
        assignment.save(update_fields=("status", "completed_at", "lock_version", "updated_at"))

        AuditService.record(
            action="EVALUATION_SUBMITTED",
            entity_type="EVALUATION",
            entity_id=evaluation.pk,
            result=AuditLog.Result.SUCCESS,
            actor=reviewer,
            actor_role=Role.Code.REVIEWER,
            details={
                "manuscript_id": str(assignment.manuscript_id),
                "assignment_id": str(assignment.pk),
                "version_number": assignment.version.version_number,
            },
            **context,
        )
        transaction.on_commit(
            lambda: announce(
                evaluation_submitted,
                evaluation_id=evaluation.pk,
                assignment_id=assignment.pk,
                manuscript_id=assignment.manuscript_id,
                reviewer_id=reviewer.pk,
            )
        )
        evaluation.refresh_from_db()
        return evaluation

    return run_audited(work)
