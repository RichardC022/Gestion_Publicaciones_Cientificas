"""Delete the expired idempotency keys (TSK-76).

Run daily by ``scripts/cron/gpc.cron``. Only keys whose 24-hour life has
ended are removed; a live key keeps protecting its retries. Silent when
there is nothing to delete.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.publications.services.idempotency import delete_expired_keys


class Command(BaseCommand):
    """Remove the ``Idempotency-Key`` rows past ``expires_at``."""

    help = "Elimina las claves de idempotencia vencidas; no toca las vigentes."

    def handle(self, *args, **options) -> None:
        deleted = delete_expired_keys()
        if deleted:
            self.stdout.write(
                f"{timezone.now().isoformat()} claves de idempotencia eliminadas: {deleted}"
            )
