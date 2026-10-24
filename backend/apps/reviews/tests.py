"""Tests for the reviews application."""

from django.apps import apps


def test_reviews_app_is_installed() -> None:
    """The reviews application is part of the project."""
    config = apps.get_app_config("reviews")
    assert config.name == "apps.reviews"
