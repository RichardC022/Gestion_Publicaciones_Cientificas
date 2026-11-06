"""Tests for the project URL configuration."""

from django.test import Client

from tests.contract import success_of


def test_api_root_is_mounted_under_api_v1(client: Client) -> None:
    """The API root is served under the versioned /api/v1/ prefix."""
    response = client.get("/api/v1/", secure=True)

    assert response.status_code == 200
    payload = success_of(response)["data"]
    assert payload["service"] == "gestion-publicaciones-cientificas"
    assert payload["api"] == "v1"


def test_unversioned_api_prefix_no_longer_serves_resources(client: Client) -> None:
    """Only ``/api/v1/`` carries the API; ``/api/`` alone is not a resource tree."""
    assert client.get("/api/", secure=True).status_code == 404
    assert client.get("/api/auth/me/", secure=True).status_code == 404  # sin versión: no existe


def test_health_is_served_versioned_and_unversioned(client: Client) -> None:
    """Docker and the operation scripts keep ``/api/health/``; v1 exposes it too."""
    from django.urls import resolve

    assert resolve("/api/health/").url_name == "health-unversioned"
    assert resolve("/api/v1/health/").url_name == "health"


def test_django_admin_is_separate_from_api() -> None:
    """Django Admin is not nested inside the API namespace."""
    from config import urls as project_urls

    api_patterns = [
        pattern
        for pattern in project_urls.urlpatterns
        if getattr(pattern, "pattern", None) is not None
        and str(pattern.pattern) == "api/v1/"
    ]

    assert len(api_patterns) == 1
    assert "config.api" in str(api_patterns[0])


def _reload_urls() -> None:
    import importlib

    from django.urls import clear_url_caches, set_urlconf

    from config import urls as project_urls

    importlib.reload(project_urls)
    clear_url_caches()
    set_urlconf(None)


def test_django_admin_is_mounted_only_when_enabled(settings, client: Client) -> None:
    """D-31: con ADMIN_ENABLED apagado `/admin/` no existe (404); encendido, redirige al login."""
    try:
        settings.ADMIN_ENABLED = False
        _reload_urls()
        for path in ("/admin/", "/admin/login/", "/admin/users/user/"):
            assert client.get(path, secure=True).status_code == 404, path

        settings.ADMIN_ENABLED = True
        _reload_urls()
        assert client.get("/admin/", secure=True).status_code == 302
    finally:
        settings.ADMIN_ENABLED = True  # el valor de desarrollo con el que corre la suite
        _reload_urls()
