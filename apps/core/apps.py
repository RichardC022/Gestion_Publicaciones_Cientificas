"""Application configuration for the shared core app."""

from django.apps import AppConfig


class CoreConfig(AppConfig):
    """Configuration for cross-cutting domain concerns."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"
    verbose_name = "Core"
