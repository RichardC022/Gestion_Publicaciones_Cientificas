"""Tests for the notifications application."""

from django.apps import apps


def test_notifications_app_is_installed() -> None:
    """The notifications application is part of the project."""
    config = apps.get_app_config("notifications")
    assert config.name == "apps.notifications"
