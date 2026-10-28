"""Send the pending e-mail notices and retry the failed ones (TSK-76).

Run every minute by ``scripts/cron/gpc.cron``. A notice already sent is
never mailed again, and a failure is stored as ``FAILED`` with a backoff,
so the next runs retry it without blocking the panel. It is silent when
there is nothing to do and exits with an error if any notice failed in
this run, so the failure is visible in the cron log.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.notifications.delivery import send_pending_notifications


class Command(BaseCommand):
    """Deliver ``PENDING``/``FAILED`` e-mail notices with backoff."""

    help = "Envía los avisos de correo PENDING/FAILED con reintento y backoff."

    def handle(self, *args, **options) -> None:
        result = send_pending_notifications()
        if result.sent or result.failed:
            self.stdout.write(
                f"{timezone.now().isoformat()} avisos enviados: {result.sent}; "
                f"con error: {result.failed}; sin reintentos restantes: {result.exhausted}"
            )
        if result.failed:
            raise CommandError(
                f"{result.failed} aviso(s) no se pudieron enviar; se reintentarán "
                "según el backoff."
            )
