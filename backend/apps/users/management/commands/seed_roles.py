"""Seed the fixed role catalog (plan §1.4)."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.users.models import Role

ROLE_SEED: tuple[tuple[str, str, str], ...] = (
    (Role.Code.AUTHOR, "Autor", "Registra y envía manuscritos."),
    (Role.Code.REVIEWER, "Revisor", "Evalúa manuscritos asignados bajo doble ciego."),
    (Role.Code.EDITOR, "Editor", "Gestiona envíos, asignaciones y veredictos."),
    (Role.Code.ADMIN, "Administrador", "Consulta auditoría y habilita correcciones."),
)


class Command(BaseCommand):
    """Create the four institutional roles exactly once (idempotent)."""

    help = "Siembra los roles institucionales AUTHOR, REVIEWER, EDITOR y ADMIN."

    def handle(self, *args, **options) -> None:
        for code, name, description in ROLE_SEED:
            role, created = Role.objects.get_or_create(
                code=code,
                defaults={"name": name, "description": description},
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f"Rol creado: {code}"))
            else:
                self.stdout.write(f"Rol ya existente: {code}")
        self.stdout.write(
            self.style.SUCCESS(
                f"Roles institucionales: {Role.objects.count()} (catálogo completo)."
            )
        )
