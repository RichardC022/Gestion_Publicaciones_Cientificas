"""Tests for project-level settings and app registration."""

import pytest
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


def test_jwt_lifetimes_match_the_institutional_policy() -> None:
    """Access 15 min, refresh 7 days and 30 minutes of inactivity (plan §6.1)."""
    assert settings.JWT_ACCESS_MINUTES == 15
    assert settings.JWT_REFRESH_DAYS == 7
    assert settings.SESSION_IDLE_MINUTES == 30


def test_refresh_cookie_is_always_httponly_with_strict_samesite() -> None:
    """The refresh cookie invariants hold in every environment (plan §2.1)."""
    assert settings.REFRESH_COOKIE_HTTPONLY is True
    assert settings.REFRESH_COOKIE_SAMESITE == "Strict"


def test_production_forces_secure_cookies(monkeypatch: pytest.MonkeyPatch) -> None:
    """Production serves cookies with the Secure attribute (COOKIE_SECURE=1).

    Importing ``config.settings.production`` validates the required
    environment variables (TSK-10). CI has no production secrets, so the
    test injects dummy values — including ``DJANGO_SECRET_KEY=dummy-key`` —
    just to import the module and verify the cookie contract.
    """
    for name, value in (
        ("DJANGO_SECRET_KEY", "dummy-key"),
        ("POSTGRES_DB", "gpc_ci"),
        ("POSTGRES_USER", "gpc_ci"),
        ("POSTGRES_PASSWORD", "gpc_ci_password"),
        ("POSTGRES_HOST", "127.0.0.1"),
        ("POSTGRES_PORT", "5432"),
        ("ALLOWED_HOSTS", "localhost"),
        ("CSRF_TRUSTED_ORIGINS", "http://localhost"),
        ("EMAIL_HOST", "smtp.example.com"),
        ("EMAIL_PORT", "587"),
        ("EMAIL_USE_TLS", "1"),
        ("EMAIL_HOST_USER", "ci@example.com"),
        ("EMAIL_HOST_PASSWORD", "ci-password"),
        ("DEFAULT_FROM_EMAIL", "ci@example.com"),
        ("COOKIE_SECURE", "1"),
    ):
        monkeypatch.setenv(name, value)

    from config.settings import production

    assert production.COOKIE_SECURE is True
