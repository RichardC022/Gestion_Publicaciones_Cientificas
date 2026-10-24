"""Tests for the standard pagination contract (TSK-11)."""

import json

from django.test import override_settings

from tests.api_urls import TOTAL_ITEMS

PAGINATION_KEYS = {"count", "next", "previous", "results"}


def _payload_of(response):
    payload = json.loads(response.content)
    assert set(payload.keys()) == PAGINATION_KEYS
    return payload


def _error_of(response):
    payload = json.loads(response.content)
    return payload["error"]


@override_settings(ROOT_URLCONF="tests.api_urls")
def test_default_page_size_is_20(client):
    """Without parameters the server returns pages of 20 items."""
    response = client.get("/items/", secure=True)

    assert response.status_code == 200
    payload = _payload_of(response)
    assert payload["count"] == TOTAL_ITEMS
    assert len(payload["results"]) == 20
    assert payload["results"][0]["id"] == 0


@override_settings(ROOT_URLCONF="tests.api_urls")
def test_requested_page_is_served(client):
    """``page=2`` returns the second slice of results."""
    response = client.get("/items/?page=2", secure=True)

    assert response.status_code == 200
    payload = _payload_of(response)
    assert payload["results"][0]["id"] == 20


@override_settings(ROOT_URLCONF="tests.api_urls")
def test_page_size_never_exceeds_100(client):
    """``page_size=100`` is the largest accepted size."""
    response = client.get("/items/?page_size=100", secure=True)

    assert response.status_code == 200
    payload = _payload_of(response)
    assert len(payload["results"]) == 100


@override_settings(ROOT_URLCONF="tests.api_urls")
def test_page_size_above_100_returns_400(client):
    """A ``page_size`` over the maximum is an invalid filter: ``400``."""
    response = client.get("/items/?page_size=101", secure=True)

    assert response.status_code == 400
    error = _error_of(response)
    assert error["code"] == "VALIDATION_ERROR"
    assert "page_size" in error["details"]
    assert error["request_id"] == response["X-Request-ID"]


@override_settings(ROOT_URLCONF="tests.api_urls")
def test_non_integer_page_size_returns_400(client):
    """A malformed ``page_size`` is an invalid filter: ``400``."""
    response = client.get("/items/?page_size=many", secure=True)

    assert response.status_code == 400
    assert _error_of(response)["code"] == "VALIDATION_ERROR"


@override_settings(ROOT_URLCONF="tests.api_urls")
def test_zero_page_size_returns_400(client):
    """``page_size=0`` is rejected instead of being silently ignored."""
    response = client.get("/items/?page_size=0", secure=True)

    assert response.status_code == 400
    assert _error_of(response)["code"] == "VALIDATION_ERROR"


@override_settings(ROOT_URLCONF="tests.api_urls")
def test_non_integer_page_returns_400(client):
    """A malformed ``page`` is an invalid filter: ``400``."""
    response = client.get("/items/?page=soon", secure=True)

    assert response.status_code == 400
    error = _error_of(response)
    assert error["code"] == "VALIDATION_ERROR"
    assert "page" in error["details"]


@override_settings(ROOT_URLCONF="tests.api_urls")
def test_zero_page_returns_400(client):
    """``page=0`` is rejected: pages are 1-based."""
    response = client.get("/items/?page=0", secure=True)

    assert response.status_code == 400
    assert _error_of(response)["code"] == "VALIDATION_ERROR"


@override_settings(ROOT_URLCONF="tests.api_urls")
def test_out_of_range_page_returns_404_in_spanish(client):
    """An out-of-range page keeps ``404`` semantics with a clear message."""
    response = client.get("/items/?page=999", secure=True)

    assert response.status_code == 404
    error = _error_of(response)
    assert error["code"] == "NOT_FOUND"
    assert error["message"] == "La página solicitada no existe."


@override_settings(ROOT_URLCONF="tests.api_urls")
def test_last_page_alias_is_supported(client):
    """The ``last`` alias still resolves to the final page."""
    response = client.get("/items/?page=last&page_size=50", secure=True)

    assert response.status_code == 200
    payload = _payload_of(response)
    assert payload["results"][0]["id"] == 200
    assert len(payload["results"]) == 50
