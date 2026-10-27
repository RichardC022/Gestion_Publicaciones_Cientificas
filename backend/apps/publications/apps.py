"""Publications application configuration."""

from django.apps import AppConfig


class PublicationsConfig(AppConfig):
    """Manuscripts, versions, verdicts, and public catalog domain."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.publications"
    label = "publications"
    verbose_name = "Publications"
