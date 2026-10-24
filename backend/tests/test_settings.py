"""Tests for project-level settings and app registration."""

from django.conf import settings

DOMAIN_APPS = (
    "apps.users",
    "apps.publications",
    "apps.reviews",
    "apps.audit",
    "apps.notifications",
)


def test_five_domain_apps_are_installed() -> None:
    """All domain applications are registered in INSTALLED_APPS."""
    for app_name in DOMAIN_APPS:
        assert app_name in settings.INSTALLED_APPS


def test_database_engine_is_postgresql() -> None:
    """The project never falls back to another database engine."""
    assert settings.DATABASES["default"]["ENGINE"] == "django.db.backends.postgresql"
