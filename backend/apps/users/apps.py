"""Users application configuration."""

from django.apps import AppConfig


class UsersConfig(AppConfig):
    """Institutional users, roles, and authentication domain."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.users"
    label = "users"
    verbose_name = "Users"
