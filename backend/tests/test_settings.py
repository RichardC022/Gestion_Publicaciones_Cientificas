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


def test_pdf_upload_limits_match_the_nginx_boundary() -> None:
    """Upload tuning coexists with the Nginx edge (plan §4.2 paso 3).

    Nginx accepts request bodies up to 60 MB (``client_max_body_size``)
    while Django streams anything above 2.5 MB straight to disk instead
    of holding it in memory. The real 50 MB per-PDF limit is enforced by
    the domain (PdfService, TSK-33/34) reading ``MAX_PDF_SIZE_BYTES``.
    """
    assert settings.FILE_UPLOAD_MAX_MEMORY_SIZE == 2_621_440
    assert settings.DATA_UPLOAD_MAX_MEMORY_SIZE == 62_914_560
    assert settings.MAX_PDF_SIZE_MB == 50
    assert settings.MAX_PDF_SIZE_BYTES == 50 * 1024 * 1024


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
        ("APP_DB_USER", "gpc_runtime"),
        ("APP_DB_PASSWORD", "ci-runtime-password"),
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


def _import_production(monkeypatch: pytest.MonkeyPatch, **extra: str):
    import importlib

    monkeypatch.delenv("DB_USE_ADMIN", raising=False)
    for name, value in {
        "DJANGO_SECRET_KEY": "dummy-key",
        "POSTGRES_DB": "gpc_ci",
        "POSTGRES_USER": "gpc_admin",
        "POSTGRES_PASSWORD": "ci-admin-password",
        "POSTGRES_HOST": "127.0.0.1",
        "POSTGRES_PORT": "5432",
        "APP_DB_USER": "gpc_runtime",
        "APP_DB_PASSWORD": "ci-runtime-password",
        "ALLOWED_HOSTS": "localhost",
        "CSRF_TRUSTED_ORIGINS": "http://localhost",
        "EMAIL_HOST": "smtp.example.com",
        "EMAIL_PORT": "587",
        "EMAIL_HOST_USER": "ci@example.com",
        "EMAIL_HOST_PASSWORD": "ci-password",
        "DEFAULT_FROM_EMAIL": "ci@example.com",
        **extra,
    }.items():
        monkeypatch.setenv(name, value)
    from config.settings import production

    return importlib.reload(production)


def test_production_connects_as_the_restricted_role(monkeypatch: pytest.MonkeyPatch) -> None:
    """Runtime uses APP_DB_USER, not the administrator (TSK-72)."""
    production = _import_production(monkeypatch)

    assert production.DATABASES["default"]["USER"] == "gpc_runtime"
    assert production.DATABASES["default"]["PASSWORD"] == "ci-runtime-password"


def test_production_uses_the_administrator_only_when_asked(monkeypatch: pytest.MonkeyPatch) -> None:
    """``DB_USE_ADMIN=1`` (migrate and privileges) switches to POSTGRES_USER."""
    production = _import_production(monkeypatch, DB_USE_ADMIN="1")

    assert production.DATABASES["default"]["USER"] == "gpc_admin"
    assert production.DATABASES["default"]["PASSWORD"] == "ci-admin-password"


def test_production_requires_the_restricted_role(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without APP_DB_USER the settings refuse to load (no silent superuser)."""
    from django.core.exceptions import ImproperlyConfigured

    _import_production(monkeypatch)
    monkeypatch.delenv("APP_DB_USER")
    with pytest.raises(ImproperlyConfigured, match="APP_DB_USER"):
        import importlib

        from config.settings import production

        importlib.reload(production)
