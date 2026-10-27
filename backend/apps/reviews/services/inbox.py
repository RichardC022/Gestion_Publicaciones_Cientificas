"""State of an assignment in the reviewer's inbox (plan section 5, HU-16).

The inbox tells five situations apart. They are derived from the stored
status, the deadline by the database clock and whether the reviewer
already started the evaluation; nothing is stored.
"""

from __future__ import annotations

from django.db import models

from apps.reviews.models import Assignment


class InboxState(models.TextChoices):
    PENDING = "PENDING", "Pendiente"
    ON_TIME = "ON_TIME", "En plazo"
    OVERDUE = "OVERDUE", "Vencida"
    EVALUATED = "EVALUATED", "Evaluada"
    REVOKED = "REVOKED", "Revocada"


def inbox_state(*, status: str, is_overdue: bool, has_evaluation: bool) -> InboxState:
    """Classify an assignment.

    ``PENDING`` is an ``ACTIVE`` assignment with nothing saved yet and
    ``ON_TIME`` one whose draft is already in progress, both before
    ``due_at``. ``OVERDUE`` covers the ``EXPIRED`` ones and the ``ACTIVE``
    ones past ``due_at`` that the scheduled task has not marked yet.
    """
    if status == Assignment.Status.REVOKED:
        return InboxState.REVOKED
    if status == Assignment.Status.COMPLETED:
        return InboxState.EVALUATED
    if status == Assignment.Status.EXPIRED or is_overdue:
        return InboxState.OVERDUE
    return InboxState.ON_TIME if has_evaluation else InboxState.PENDING
