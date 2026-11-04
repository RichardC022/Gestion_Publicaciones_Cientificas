"""Tests for the project URL configuration."""

import json

from django.test import Client


def test_api_root_is_mounted_under_api(client: Client) -> None:
    """The API root is served under the /api/ prefix."""
    response = client.get("/api/", secure=True)

    assert response.status_code == 200
    payload = json.loads(response.content)
    assert payload["service"] == "gestion-publicaciones-cientificas"


def test_django_admin_is_separate_from_api() -> None:
    """Django Admin is not nested inside the API namespace."""
    from config import urls as project_urls

    api_patterns = [
        pattern
        for pattern in project_urls.urlpatterns
        if getattr(pattern, "pattern", None) is not None
        and str(pattern.pattern) == "api/"
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
