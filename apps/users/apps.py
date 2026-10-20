"""Application configuration for the users app."""

from django.apps import AppConfig


class UsersConfig(AppConfig):
    """Configuration for authentication, roles and RBAC."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.users"
    verbose_name = "Users"
