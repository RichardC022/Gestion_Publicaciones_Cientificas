"""Logical withdrawal of a manuscript (plan section 4.8, RF-22).

``withdraw_manuscript`` marks ``is_active=False`` together with
``withdrawn_at``, ``withdrawn_by`` and the reason, in ONE transaction
that also records the status event and the audit. Nothing is deleted:
versions, rounds, history and audit stay untouched (RN-11, RN-13), and
``status`` does not change — the withdrawal is a mark over any state.

The row lock taken here is the same one the upload, submission and new
version pipelines take, so a withdrawal that races with them never
leaves a partial version: whoever gets the lock first wins and the
other one answers ``409``.

Revoking the active assignment and deactivating the catalog entry
belong to other apps. They plug in through the in-transaction signal
:data:`~apps.publications.signals.manuscript_withdrawing`; the committed
withdrawal is announced with ``manuscript_withdrawn``. Until those
listeners exist, the immediate effect on the catalog and on the
reviewer comes from ``is_active=False``, which both listings filter.
"""

from __future__ import annotations

import logging
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from apps.audit.services import AuditUnavailable
from apps.publications.models import Manuscript, StatusEvent
from apps.publications.services.versions import record_audit
from apps.publications.signals import manuscript_withdrawing, manuscript_withdrawn
from apps.users.models import User
from apps.users.services.auth import AUDIT_UNAVAILABLE_MESSAGE
from config.exceptions import DomainError, ErrorCode

logger = logging.getLogger(__name__)

#: Statuses in which the reason is mandatory (CA-HU-08-02).
REASON_REQUIRED_STATUSES = (
    Manuscript.Status.UNDER_REVIEW,
    Manuscript.Status.ACCEPTED,
)

ALREADY_WITHDRAWN_MESSAGE = "El manuscrito ya se encuentra dado de baja."
REASON_REQUIRED_MESSAGE = (
    "Indique el motivo de la baja: el manuscrito está en revisión o ya fue aceptado."
)


def ensure_active(manuscript: Manuscript) -> None:
    """A second withdrawal is reported, never repeated (CA-HU-08-06)."""
    if not manuscript.is_active:
        raise DomainError(
            ALREADY_WITHDRAWN_MESSAGE,
            code=ErrorCode.STATE_CONFLICT,
            details={"status": manuscript.status, "is_active": False},
        )


def _announce(manuscript_id: UUID, user_id: UUID, previous_status: str) -> None:
    for receiver, error in manuscript_withdrawn.send_robust(
        sender=Manuscript,
        manuscript_id=manuscript_id,
        withdrawn_by_id=user_id,
        previous_status=previous_status,
    ):
        if isinstance(error, Exception):
            logger.error("Un receptor de la baja falló (%s): %s", receiver, error)


def withdraw_manuscript(
    *, manuscript_id: UUID, user: User, reason: str | None, context: dict
) -> Manuscript:
    """Withdraw the manuscript; ``reason`` is mandatory in review or accepted."""
    reason = (reason or "").strip() or None
    try:
        with transaction.atomic():
            manuscript = Manuscript.objects.select_for_update().get(pk=manuscript_id)
            ensure_active(manuscript)

            previous_status = manuscript.status
            if previous_status in REASON_REQUIRED_STATUSES and reason is None:
                raise DomainError(
                    REASON_REQUIRED_MESSAGE,
                    code=ErrorCode.VALIDATION_ERROR,
                    details={"reason": [REASON_REQUIRED_MESSAGE]},
                )

            now = timezone.now()
            manuscript.is_active = False
            manuscript.withdrawn_at = now
            manuscript.withdrawn_by = user
            manuscript.withdrawal_reason = reason
            manuscript.lock_version += 1
            manuscript.save(
                update_fields=(
                    "is_active",
                    "withdrawn_at",
                    "withdrawn_by",
                    "withdrawal_reason",
                    "lock_version",
                    "updated_at",
                )
            )
            # La baja no cambia el estado editorial: el evento lo repite.
            StatusEvent.objects.create(
                manuscript=manuscript,
                from_status=previous_status,
                to_status=previous_status,
                actor=user,
                reason=reason,
                metadata={"withdrawn": True},
            )
            manuscript_withdrawing.send(
                sender=Manuscript,
                manuscript_id=manuscript.pk,
                withdrawn_by_id=user.pk,
                previous_status=previous_status,
                withdrawn_at=now,
            )
            record_audit(
                "MANUSCRIPT_WITHDRAWN",
                manuscript.pk,
                user,
                context,
                reason=reason,
                details={"code": manuscript.code, "previous_status": previous_status},
            )
            transaction.on_commit(
                lambda: _announce(manuscript.pk, user.pk, previous_status)
            )
    except AuditUnavailable as exc:
        raise DomainError(AUDIT_UNAVAILABLE_MESSAGE, code=ErrorCode.AUDIT_UNAVAILABLE) from exc
    return manuscript
