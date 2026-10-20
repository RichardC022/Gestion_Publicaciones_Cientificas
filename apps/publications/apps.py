"""Application configuration for the publications app."""

from django.apps import AppConfig


class PublicationsConfig(AppConfig):
    """Configuration for manuscript submission, versioning and catalog."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.publications"
    verbose_name = "Publications"
