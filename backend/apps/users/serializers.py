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


class DashboardSectionSerializer(serializers.Serializer):
    """One role section of the unified dashboard (plan section 2.2).

    ``status`` is resolved independently per section; ``message``
    carries the retryable notice when the section failed and ``data``
    holds the section payload when it succeeded.
    """

    status = serializers.ChoiceField(choices=("ok", "error"), read_only=True)
    data = serializers.JSONField(read_only=True, allow_null=True)
    message = serializers.CharField(read_only=True, allow_null=True)


class DashboardSerializer(serializers.Serializer):
    """Single response of ``GET /api/dashboard/`` (plan section 2.2).

    ``sections`` only contains the sections of the active roles; a
    person without roles receives it explicitly empty. The panel never
    asks to choose a role.
    """

    user = SessionUserSerializer(read_only=True)
    roles = serializers.ListField(child=serializers.CharField(), read_only=True)
    sections = serializers.DictField(child=DashboardSectionSerializer(), read_only=True)


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
