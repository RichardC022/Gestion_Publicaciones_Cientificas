"""Cuentas de prueba con un rol cada una, para recorrer la aplicación a mano (SOLO desarrollo)."""

from __future__ import annotations

import os

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from apps.users.services.provisioning import provision_user

#: Variable que confirma que ESTE entorno es de pruebas (el contenedor corre con ajustes de
#: producción incluso en desarrollo, así que `DEBUG` no basta como señal).
GUARD = "ALLOW_DEV_USERS"
DEFAULT_PASSWORD = "Gpc-dev-2026"
AREAS = ["Agronomía", "Ingeniería", "Medicina", "Educación", "Derecho"]

#: identificador, nombre, apellido y roles (el perfil de revisor se crea con el rol REVIEWER)
DEV_USERS: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    ("autor", "Ana", "Autora Prueba", ("AUTHOR",)),
    ("autor2", "Andrés", "Autor Dos", ("AUTHOR",)),
    ("editor", "Esteban", "Editor Prueba", ("EDITOR",)),
    ("revisor", "Rosa", "Revisora Prueba", ("REVIEWER",)),
    ("revisor2", "Ramiro", "Revisor Dos", ("REVIEWER",)),
    ("admin", "Adriana", "Administradora Prueba", ("ADMIN",)),
    ("autor.revisor", "Elena", "Autora y Revisora", ("AUTHOR", "REVIEWER")),
)


class Command(BaseCommand):
    """Crea (o actualiza la contraseña de) las cuentas de prueba. Nunca en producción."""

    help = (
        "Crea cuentas de prueba (autor, editor, revisor, admin y una multirrol) con una "
        f"contraseña conocida. Exige {GUARD}=1 o DEBUG; no lo use en el piloto real."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument("--password", default=DEFAULT_PASSWORD, help=f"Por defecto: {DEFAULT_PASSWORD}")

    def handle(self, *args, **options) -> None:
        if not (settings.DEBUG or os.environ.get(GUARD) == "1"):
            raise CommandError(
                "Este comando crea cuentas con contraseña conocida y solo es para desarrollo. "
                f"Si este entorno es de pruebas, ejecútelo con {GUARD}=1."
            )
        call_command("seed_roles", verbosity=0)
        password = options["password"]
        self.stdout.write(f"{'Identificador':<16}{'Roles':<20}Correo")
        for identifier, first_name, last_name, roles in DEV_USERS:
            result = provision_user(
                institutional_id=identifier,
                first_name=first_name,
                last_name=last_name,
                email=f"{identifier}@dev.unl.edu.ec",
                roles=roles,
                password=password,  # siempre: así repetir el comando restablece la contraseña
                expertise_areas=AREAS,
            )
            self.stdout.write(f"{result.user.institutional_id:<16}{', '.join(roles):<20}{result.user.email}")
        self.stdout.write(self.style.SUCCESS(f"\n{len(DEV_USERS)} cuentas listas. Contraseña de todas: {password}"))
