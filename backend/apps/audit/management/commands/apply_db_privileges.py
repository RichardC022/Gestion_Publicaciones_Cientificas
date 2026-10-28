"""Apply the restricted privileges of the runtime database role (TSK-72).

Run by the backend container right after ``migrate``, with the
administrative credentials, so a fresh database, an upgraded one and a
restored one all end with the same grants. It is idempotent. The role
comes from ``APP_DB_USER``/``APP_DB_PASSWORD``; see
``apps/audit/privileges.py`` for what it can and cannot do.
"""

from __future__ import annotations

import os

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.audit.privileges import apply_runtime_privileges


class Command(BaseCommand):
    """Create/refresh the runtime role: DML on data, only INSERT/SELECT on audit."""

    help = "Aplica los privilegios mínimos del rol de aplicación (auditoría solo INSERT/SELECT)."

    def handle(self, *args, **options) -> None:
        role = os.environ.get("APP_DB_USER", "")
        password = os.environ.get("APP_DB_PASSWORD", "")
        if not role or not password:
            raise CommandError("APP_DB_USER y APP_DB_PASSWORD son obligatorias.")
        admin = settings.DATABASES["default"]["USER"]
        if role == admin:
            raise CommandError(
                "APP_DB_USER debe ser distinto del usuario administrador (POSTGRES_USER): "
                "un superusuario ignora los privilegios."
            )
        apply_runtime_privileges(role, password)
        self.stdout.write(f"Privilegios del rol de aplicación «{role}» aplicados.")
