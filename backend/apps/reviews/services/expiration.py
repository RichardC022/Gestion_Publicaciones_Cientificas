"""Expiration of assignments past their deadline (TSK-49, RN-05).

``mark_expired_assignments`` only changes ``ACTIVE`` to ``EXPIRED`` for
the rows whose ``due_at <= now()`` by the database clock. It never
revokes, never creates an assignment and leaves evaluations and drafts
untouched: what follows is the editor's decision.

Each assignment expires in its own transaction together with its audit
event, and is announced after the commit. Only an ``ACTIVE`` row is
selected, so running the task again finds nothing to do and repeats no
event or notice. If the audit trail is unavailable for one assignment it
stays ``ACTIVE`` and the next run retries it, without blocking the rest.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

from django.db import transaction
from django.db.models.functions import Now

from apps.audit.models import AuditLog
from apps.audit.services import AuditService, AuditUnavailable
from apps.reviews.models import Assignment
from apps.reviews.signals import announce, assignment_expired

logger = logging.getLogger(__name__)

EXPIRATION_REASON = "Venció el plazo de 20 días de la asignación."


@dataclass(frozen=True)
class ExpirationResult:
    """How many assignments were expired and how many could not be."""

    expired: int
    failed: int


def _expire(assignment_id: UUID) -> bool:
    """Expire one assignment; ``False`` if it is no longer due.

    The row is locked and the condition re-evaluated, so an assignment
    revoked or completed in the meantime is left alone, and one that
    another process is already handling is skipped.
    """
    assignment = (
        Assignment.objects.select_for_update(skip_locked=True)
        .filter(pk=assignment_id, status=Assignment.Status.ACTIVE, due_at__lte=Now())
        .first()
    )
    if assignment is None:
        return False
    assignment.status = Assignment.Status.EXPIRED
    assignment.lock_version += 1
    assignment.save(update_fields=("status", "lock_version", "updated_at"))
    AuditService.record(
        action="ASSIGNMENT_EXPIRED",
        entity_type="ASSIGNMENT",
        entity_id=assignment.pk,
        result=AuditLog.Result.SUCCESS,
        reason=EXPIRATION_REASON,
        details={
            "manuscript_id": str(assignment.manuscript_id),
            "due_at": assignment.due_at.isoformat(),
            "source": "scheduler",
        },
    )
    transaction.on_commit(
        lambda: announce(
            assignment_expired,
            assignment_id=assignment.pk,
            manuscript_id=assignment.manuscript_id,
            reviewer_id=assignment.reviewer_id,
            assigned_by_id=assignment.assigned_by_id,
        )
    )
    return True


def mark_expired_assignments() -> ExpirationResult:
    """Mark as ``EXPIRED`` every ``ACTIVE`` assignment whose deadline passed."""
    due_ids = list(
        Assignment.objects.filter(status=Assignment.Status.ACTIVE, due_at__lte=Now())
        .order_by("due_at", "id")
        .values_list("pk", flat=True)
    )
    expired = failed = 0
    for assignment_id in due_ids:
        try:
            with transaction.atomic():
                expired += _expire(assignment_id)
        except AuditUnavailable:
            failed += 1
            logger.error("No se pudo auditar el vencimiento de la asignación %s", assignment_id)
    return ExpirationResult(expired=expired, failed=failed)
