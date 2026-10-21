"""Create demo users covering every institutional role.

Usage::

    python manage.py seed_demo

The command is idempotent: existing users are updated rather than duplicated.
It is intended for local demonstrations and staging, never for production
credentials (the default password is obviously non-secret).
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

from apps.users.models import User, UserRole

DEMO_PASSWORD = "Demo.12345"

DEMO_USERS: list[dict[str, Any]] = [
    {
        "username": "admin.unl",
        "email": "admin@unl.edu.ec",
        "document_id": "1100000001",
        "first_name": "Administrador",
        "last_name": "Institucional",
        "roles": {UserRole.ADMIN},
        "is_staff": True,
        "is_superuser": True,
    },
    {
        "username": "editor.unl",
        "email": "editor@unl.edu.ec",
        "document_id": "1100000002",
        "first_name": "Elena",
        "last_name": "Editora",
        "roles": {UserRole.EDITOR},
    },
    {
        "username": "revisor.unl",
        "email": "revisor@unl.edu.ec",
        "document_id": "1100000003",
        "first_name": "Raúl",
        "last_name": "Revisor",
        "roles": {UserRole.REVIEWER},
    },
    {
        "username": "autor.unl",
        "email": "autor@unl.edu.ec",
        "document_id": "1100000004",
        "first_name": "Ana",
        "last_name": "Autora",
        "roles": {UserRole.AUTHOR},
    },
    {
        "username": "docente.unl",
        "email": "docente@unl.edu.ec",
        "document_id": "1100000005",
        "first_name": "Diego",
        "last_name": "Docente",
        "roles": {UserRole.AUTHOR, UserRole.REVIEWER},
    },
]


class Command(BaseCommand):
    """Seed the database with one demo account per role."""

    help = "Create demo users for every institutional role (idempotent)."

    def handle(self, *args: Any, **options: Any) -> None:
        """Create or update the demo accounts."""
        for spec in DEMO_USERS:
            roles: set[str] = spec.pop("roles")
            active_role = (
                UserRole.ADMIN if UserRole.ADMIN in roles else next(iter(roles))
            )
            user, created = User.objects.get_or_create(
                username=spec["username"],
                defaults={
                    "email": spec["email"],
                    "document_id": spec["document_id"],
                    "first_name": spec["first_name"],
                    "last_name": spec["last_name"],
                    "is_staff": spec.get("is_staff", False),
                    "is_superuser": spec.get("is_superuser", False),
                },
            )
            user.email = spec["email"]
            user.document_id = spec["document_id"]
            user.first_name = spec["first_name"]
            user.last_name = spec["last_name"]
            user.is_staff = spec.get("is_staff", False)
            user.is_superuser = spec.get("is_superuser", False)
            user.is_author_enabled = UserRole.AUTHOR in roles
            user.is_reviewer_enabled = UserRole.REVIEWER in roles
            user.is_editor_enabled = UserRole.EDITOR in roles
            user.is_admin_enabled = UserRole.ADMIN in roles
            user.active_role = active_role
            user.set_password(DEMO_PASSWORD)
            user.save()
            verb = "created" if created else "updated"
            self.stdout.write(
                self.style.SUCCESS(f"{verb}: {user.username} ({active_role})")
            )

        self.stdout.write(
            self.style.WARNING(f"All demo users share the password: {DEMO_PASSWORD}")
        )
