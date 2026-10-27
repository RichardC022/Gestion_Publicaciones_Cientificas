"""Tests for the ``X-Request-ID`` middleware (TSK-11)."""

import json
import logging
import re

import pytest
from django.conf import settings
from django.test import Client, override_settings

from config import middleware
from config.middleware import RequestIDLogFilter

GENERATED_ID = re.compile(r"^[0-9a-f]{32}$")


@override_settings(ROOT_URLCONF="tests.api_urls")
def test_response_carries_generated_request_id(client):
    """Without a client id the middleware generates one and echoes it."""
    response = client.get("/echo/", secure=True)

    assert response.status_code == 200
    request_id = response["X-Request-ID"]
    assert GENERATED_ID.fullmatch(request_id)
    assert json.loads(response.content)["request_id"] == request_id


@override_settings(ROOT_URLCONF="tests.api_urls")
def test_valid_client_request_id_is_preserved(client):
    """A safe client identifier is reused end to end."""
    response = client.get("/echo/", secure=True, HTTP_X_REQUEST_ID="client-abc-123")

    assert response.status_code == 200
    assert response["X-Request-ID"] == "client-abc-123"
    assert json.loads(response.content)["request_id"] == "client-abc-123"


@pytest.mark.parametrize(
    "unsafe_value",
    [
        "Ana Pérez <ana.perez@unl.edu.ec>",
        "rid with spaces",
        "rid\nwith-newline",
        "a" * 65,
        "",
    ],
)
@override_settings(ROOT_URLCONF="tests.api_urls")
def test_unsafe_request_id_is_replaced(client, unsafe_value):
    """Unsafe identifiers never reach logs, responses or the audit trail."""
    response = client.get("/echo/", secure=True, HTTP_X_REQUEST_ID=unsafe_value)

    assert response.status_code == 200
    request_id = response["X-Request-ID"]
    assert request_id != unsafe_value.strip()
    assert GENERATED_ID.fullmatch(request_id)


@override_settings(ROOT_URLCONF="tests.api_urls")
def test_unhandled_error_is_logged_with_request_id(caplog):
    """The request id reaches application logs for correlation."""
    with override_settings(DEBUG=False):
        client = Client(raise_request_exception=False)
        with caplog.at_level(logging.ERROR, logger="config.exceptions"):
            response = client.get("/crash/", secure=True, HTTP_X_REQUEST_ID="rid-log-1")

    assert response.status_code == 500
    assert any("rid-log-1" in message for message in caplog.messages)


def test_log_filter_attaches_active_request_id_to_records():
    """The log filter injects the id of the request being served."""
    record = logging.LogRecord(
        "tests", logging.INFO, "tests", 1, "mensaje de prueba", None, None
    )
    token = middleware._current_request_id.set("filter-rid-1")
    try:
        assert RequestIDLogFilter().filter(record) is True
        assert record.request_id == "filter-rid-1"
    finally:
        middleware._current_request_id.reset(token)


def test_log_filter_defaults_to_dash_outside_requests():
    """Outside of a request cycle the filter uses a neutral marker."""
    record = logging.LogRecord(
        "tests", logging.INFO, "tests", 1, "mensaje de prueba", None, None
    )

    assert RequestIDLogFilter().filter(record) is True
    assert record.request_id == "-"


def test_request_id_middleware_runs_first():
    """The middleware wraps the whole cycle, before any other middleware."""
    assert settings.MIDDLEWARE[0] == "config.middleware.RequestIdMiddleware"


@override_settings(ROOT_URLCONF="tests.api_urls")
def test_request_id_is_readable_for_auditing(client):
    """Views and services (including audit) can read ``request.request_id``."""
    response = client.get("/echo/", secure=True, HTTP_X_REQUEST_ID="rid-audit")

    assert response.status_code == 200
    assert json.loads(response.content)["request_id"] == "rid-audit"
