"""E-mail delivery of pending notices with retry and backoff (TSK-76).

The panel notice never depends on this module: a ``PANEL`` row is usable
from the moment it exists. Only the ``EMAIL`` rows travel through here.

A row is eligible when it is ``PENDING``, or ``FAILED`` with attempts left
and its ``next_attempt_at`` already past. Each row is locked with
``SKIP LOCKED`` while it is sent, so two overlapping runs of the command
never mail the same notice twice. A ``SENT`` row is never selected again.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.notifications.models import Notification

logger = logging.getLogger(__name__)

#: Wait before retry number ``n`` (index ``n - 1``); after the last one the
#: notice stays ``FAILED`` for good and shows up in the command output.
BACKOFF_STEPS: tuple[timedelta, ...] = (
    timedelta(minutes=1),
    timedelta(minutes=5),
    timedelta(minutes=15),
    timedelta(hours=1),
    timedelta(hours=4),
)
MAX_ATTEMPTS = len(BACKOFF_STEPS) + 1

LAST_ERROR_LIMIT = 500


@dataclass(frozen=True)
class DeliveryResult:
    """What one run of :func:`send_pending_notifications` did."""

    sent: int = 0
    failed: int = 0
    exhausted: int = 0


def backoff_for(attempts: int) -> timedelta | None:
    """Wait after the ``attempts``-th failure; ``None`` when no retry is left."""
    if attempts >= MAX_ATTEMPTS:
        return None
    return BACKOFF_STEPS[attempts - 1]


def _eligible(now):
    return Notification.objects.filter(channel=Notification.Channel.EMAIL).filter(
        Q(status=Notification.Status.PENDING)
        | Q(
            status=Notification.Status.FAILED,
            attempts__lt=MAX_ATTEMPTS,
            next_attempt_at__lte=now,
        )
    )


def _compose(notification: Notification) -> tuple[str, str]:
    """Subject and body from the sanitized payload; nothing else is mailed."""
    payload = notification.payload if isinstance(notification.payload, dict) else {}
    subject = str(payload.get("title") or notification.event_type)
    body = str(payload.get("message") or "")
    return subject, body


def send_pending_notifications(now=None) -> DeliveryResult:
    """Mail every eligible notice once; record the outcome of each one."""
    now = now or timezone.now()
    candidate_ids = list(
        _eligible(now).order_by("created_at", "id").values_list("pk", flat=True)
    )
    sent = failed = exhausted = 0
    for pk in candidate_ids:
        with transaction.atomic():
            notification = (
                _eligible(now)
                .select_for_update(skip_locked=True, of=("self",))
                .select_related("recipient")
                .filter(pk=pk)
                .first()
            )
            if notification is None:
                continue
            try:
                email = notification.recipient.email
                if not email:
                    raise ValueError("El destinatario no tiene correo registrado.")
                subject, body = _compose(notification)
                send_mail(subject, body, None, [email], fail_silently=False)
            except Exception as exc:  # noqa: BLE001 - any transport error is a retry
                notification.attempts += 1
                notification.status = Notification.Status.FAILED
                notification.last_error = f"{type(exc).__name__}: {exc}"[:LAST_ERROR_LIMIT]
                wait = backoff_for(notification.attempts)
                notification.next_attempt_at = None if wait is None else now + wait
                failed += 1
                exhausted += wait is None
                logger.warning(
                    "Aviso %s no enviado (intento %s): %s",
                    notification.pk,
                    notification.attempts,
                    type(exc).__name__,
                )
            else:
                notification.attempts += 1
                notification.status = Notification.Status.SENT
                notification.sent_at = timezone.now()
                notification.last_error = None
                notification.next_attempt_at = None
                sent += 1
            notification.save(
                update_fields=[
                    "attempts",
                    "status",
                    "last_error",
                    "next_attempt_at",
                    "sent_at",
                ]
            )
    return DeliveryResult(sent=sent, failed=failed, exhausted=exhausted)
