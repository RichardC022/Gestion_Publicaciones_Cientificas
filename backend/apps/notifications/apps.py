"""Notifications application configuration."""

from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    """Panel and email notification domain."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.notifications"
    label = "notifications"
    verbose_name = "Notifications"

    def ready(self) -> None:
        from apps.notifications import receivers  # noqa: F401
