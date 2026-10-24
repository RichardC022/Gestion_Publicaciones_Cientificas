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
