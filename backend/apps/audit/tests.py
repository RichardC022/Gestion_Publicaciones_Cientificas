"""Tests for the audit application."""

from django.apps import apps


def test_audit_app_is_installed() -> None:
    """The audit application is part of the project."""
    config = apps.get_app_config("audit")
    assert config.name == "apps.audit"
