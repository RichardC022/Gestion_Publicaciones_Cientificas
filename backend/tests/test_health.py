"""Tests for the public health endpoint (TSK-12)."""

import json
import logging
import os

import pytest
from django.test import override_settings

UNAVAILABLE_MESSAGE = "El servicio no está disponible temporalmente."


@pytest.mark.django_db
def test_health_returns_200_with_minimal_payload(client, tmp_path):
    """A healthy system answers 200 with no user or manuscript data."""
    with override_settings(MEDIA_ROOT=tmp_path):
        response = client.get("/api/health/", secure=True)

    assert response.status_code == 200
    assert json.loads(response.content) == {"status": "ok"}
    assert response["X-Request-ID"]


@pytest.mark.django_db
def test_health_returns_503_when_database_fails(client, tmp_path, monkeypatch):
    """A database failure yields a generic 503 envelope without internals."""
    from config import health

    def broken_database() -> None:
        raise RuntimeError("sentinel-db-host-unreachable")

    monkeypatch.setattr(health, "check_database", broken_database)
    with override_settings(MEDIA_ROOT=tmp_path):
        response = client.get("/api/health/", secure=True)

    assert response.status_code == 503
    payload = json.loads(response.content)
    assert set(payload.keys()) == {"error"}
    error = payload["error"]
    assert error["code"] == "SERVER_ERROR"
    assert error["message"] == UNAVAILABLE_MESSAGE
    assert error["details"] == {}
    assert error["request_id"]
    assert "sentinel-db-host-unreachable" not in response.content.decode()


@pytest.mark.django_db
def test_health_returns_503_when_volume_is_missing(client, tmp_path, caplog):
    """A missing media volume yields a generic 503 and logs the request id."""
    missing_volume = tmp_path / "media-missing"
    with override_settings(MEDIA_ROOT=missing_volume):
        with caplog.at_level(logging.ERROR, logger="config.health"):
            response = client.get(
                "/api/health/", secure=True, HTTP_X_REQUEST_ID="rid-health-missing"
            )

    assert response.status_code == 503
    error = json.loads(response.content)["error"]
    assert error["code"] == "SERVER_ERROR"
    assert error["message"] == UNAVAILABLE_MESSAGE
    assert error["request_id"] == "rid-health-missing"
    assert "media-missing" not in response.content.decode()
    assert any("rid-health-missing" in message for message in caplog.messages)


@pytest.mark.django_db
@pytest.mark.skipif(
    os.geteuid() == 0, reason="root can write into read-only directories"
)
def test_health_returns_503_when_volume_is_read_only(client, tmp_path):
    """A read-only media volume fails the temporary write/read cycle."""
    read_only = tmp_path / "read-only"
    read_only.mkdir()
    read_only.chmod(0o500)
    with override_settings(MEDIA_ROOT=read_only):
        response = client.get("/api/health/", secure=True)

    assert response.status_code == 503
    error = json.loads(response.content)["error"]
    assert error["message"] == UNAVAILABLE_MESSAGE
