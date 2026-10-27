"""Tests for the users application."""

from django.apps import apps


def test_users_app_is_installed() -> None:
    """The users application is part of the project."""
    config = apps.get_app_config("users")
    assert config.name == "apps.users"
