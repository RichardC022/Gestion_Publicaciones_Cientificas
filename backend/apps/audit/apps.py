"""Audit application configuration."""

from django.apps import AppConfig


class AuditConfig(AppConfig):
    """Immutable audit trail and integrity chain domain."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.audit"
    label = "audit"
    verbose_name = "Audit"
