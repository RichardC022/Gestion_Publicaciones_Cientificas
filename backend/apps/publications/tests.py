"""Tests for the publications application."""

from django.apps import apps


def test_publications_app_is_installed() -> None:
    """The publications application is part of the project."""
    config = apps.get_app_config("publications")
    assert config.name == "apps.publications"
