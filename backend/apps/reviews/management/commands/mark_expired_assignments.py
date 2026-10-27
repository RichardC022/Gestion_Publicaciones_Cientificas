"""Mark the assignments past their deadline as ``EXPIRED`` (TSK-49).

Run every minute by ``scripts/cron/gpc.cron``. It is idempotent and
silent when there is nothing to do, so the log only shows real work.
It exits with an error if any assignment could not be audited, so the
failure is visible in the cron log; that assignment is retried on the
next run.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.reviews.services.expiration import mark_expired_assignments


class Command(BaseCommand):
    """Expire the active assignments whose ``due_at`` has passed."""

    help = "Marca como EXPIRED las asignaciones ACTIVE con due_at vencido (sin revocar ni reasignar)."

    def handle(self, *args, **options) -> None:
        result = mark_expired_assignments()
        if result.expired or result.failed:
            self.stdout.write(
                f"{timezone.now().isoformat()} asignaciones vencidas: {result.expired}; "
                f"con error: {result.failed}"
            )
        if result.failed:
            raise CommandError(
                f"{result.failed} asignación(es) no se pudieron marcar; se reintentarán."
            )
