"""Alta de una cuenta institucional con sus roles (D-31: reemplaza al Django Admin)."""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.users.services.provisioning import ProvisioningError, provision_user


class Command(BaseCommand):
    """Crea una cuenta o le añade roles; imprime la contraseña generada una sola vez."""

    help = (
        "Crea una cuenta institucional con sus roles (AUTHOR, REVIEWER, EDITOR, ADMIN). "
        "Sin --password genera una aleatoria y la muestra una sola vez."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument("institutional_id", help="Identificador institucional (también es el usuario).")
        parser.add_argument("--first-name", required=True)
        parser.add_argument("--last-name", required=True)
        parser.add_argument("--email", required=True)
        parser.add_argument(
            "--role", action="append", dest="roles", required=True,
            help="Rol a otorgar; repítalo para varios (--role AUTHOR --role REVIEWER).",
        )
        parser.add_argument(
            "--areas", default="",
            help="Áreas de experticia del Revisor, separadas por comas (solo con el rol REVIEWER).",
        )
        parser.add_argument(
            "--password", default=None,
            help="Contraseña inicial. Evítela en producción: queda en el historial de la terminal.",
        )

    def handle(self, *args, **options) -> None:
        try:
            result = provision_user(
                institutional_id=options["institutional_id"],
                first_name=options["first_name"],
                last_name=options["last_name"],
                email=options["email"],
                roles=options["roles"],
                password=options["password"],
                expertise_areas=[a.strip() for a in options["areas"].split(",") if a.strip()],
            )
        except ProvisioningError as error:
            raise CommandError(str(error)) from error

        verb = "Cuenta creada" if result.created else "Cuenta existente"
        self.stdout.write(self.style.SUCCESS(f"{verb}: {result.user.institutional_id} ({result.user.email})"))
        self.stdout.write(f"Roles añadidos: {', '.join(result.roles_added) or 'ninguno (ya los tenía)'}")
        if options["password"] is None and result.password is not None:  # solo la generada
            self.stdout.write(f"Contraseña inicial (anótela ahora, no se vuelve a mostrar): {result.password}")
