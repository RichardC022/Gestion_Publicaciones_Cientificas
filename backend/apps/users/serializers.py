"""Serializers for the institutional auth endpoints (plan section 2.2)."""

from __future__ import annotations

from rest_framework import serializers

from apps.users.models import Role, User


class LoginSerializer(serializers.Serializer):
    """Credentials for ``POST /api/auth/login/``."""

    identifier = serializers.CharField(
        max_length=254,
        help_text="ID institucional, usuario o correo electrónico.",
    )
    password = serializers.CharField(
        write_only=True,
        trim_whitespace=False,
        style={"input_type": "password"},
    )


class SessionUserSerializer(serializers.ModelSerializer):
    """Identity of the authenticated institutional account."""

    full_name = serializers.CharField(source="get_full_name", read_only=True)

    class Meta:
        model = User
        fields = (
            "id",
            "institutional_id",
            "username",
            "email",
            "first_name",
            "last_name",
            "full_name",
        )


# Módulos de navegación habilitados por rol activo: la SPA renderiza
# exactamente estas rutas con rolesGuard (plan section 3.3). Los permisos
# se derivan de los roles activos leídos de la base de datos.
NAVIGATION_BY_ROLE: dict[str, tuple[dict[str, str], ...]] = {
    Role.Code.AUTHOR: (
        {"label": "Mis manuscritos", "route": "/app/author/manuscripts"},
    ),
    Role.Code.REVIEWER: (
        {"label": "Mis asignaciones", "route": "/app/reviewer/assignments"},
        {"label": "Historial de evaluaciones", "route": "/app/reviewer/history"},
    ),
    Role.Code.EDITOR: (
        {"label": "Bandeja de envíos", "route": "/app/editor/submissions"},
        {
            "label": "Plazos vencidos",
            "route": "/app/editor/assignments/expired",
        },
        {"label": "Incidentes confidenciales", "route": "/app/editor/incidents"},
    ),
    Role.Code.ADMIN: (
        {"label": "Auditoría", "route": "/app/admin/audit"},
    ),
}


def navigation_permissions(role_codes: list[str]) -> list[dict[str, str]]:
    """Navigation permissions derived from the active roles."""
    entries: list[dict[str, str]] = []
    for code in role_codes:
        for entry in NAVIGATION_BY_ROLE.get(code, ()):
            entries.append({"role": code, **entry})
    return entries
