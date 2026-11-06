"""Tests for the standard error envelope (TSK-11)."""

from django.conf import settings
from django.test import Client, override_settings

from tests.contract import error_of as _error_of
from tests.contract import failure_of, success_of


@override_settings(ROOT_URLCONF="tests.api_urls")
def test_domain_error_uses_envelope_with_code_and_request_id(client):
    """A domain error renders the envelope and keeps the request id."""
    response = client.get("/conflict/", secure=True, HTTP_X_REQUEST_ID="rid-envelope-1")

    assert response.status_code == 409
    error = _error_of(response)
    assert error["code"] == "STATE_CONFLICT"
    assert error["message"] == "La acción no es válida en el estado actual."
    assert error["details"] == {"current_status": "DRAFT"}
    assert error["request_id"] == "rid-envelope-1"
    assert response["X-Request-ID"] == "rid-envelope-1"


@override_settings(ROOT_URLCONF="tests.api_urls")
def test_http404_uses_envelope_and_generated_request_id(client):
    """A plain ``Http404`` maps to the ``NOT_FOUND`` envelope."""
    response = client.get("/missing/", secure=True)

    assert response.status_code == 404
    error = _error_of(response)
    assert error["code"] == "NOT_FOUND"
    assert error["details"] == {}
    assert error["request_id"] == response["X-Request-ID"]
    assert error["request_id"]


@override_settings(ROOT_URLCONF="tests.api_urls")
def test_validation_error_keeps_field_details_in_envelope(client):
    """Serializer/validation failures keep field details with code 400."""
    response = client.get("/invalid/", secure=True)

    assert response.status_code == 400
    payload = failure_of(response)
    assert payload["message"] == "Los datos enviados no son válidos."
    # Un error de validación genera una entrada por campo; ``details`` conserva
    # el detalle original del campo para que el cliente lo reconstruya sin pérdida.
    assert payload["errors"] == [
        {
            "code": "VALIDATION_ERROR",
            "message": "Este campo es obligatorio.",
            "field": "title",
            "details": ["Este campo es obligatorio."],
        }
    ]


@override_settings(ROOT_URLCONF="tests.api_urls")
def test_unhandled_exception_returns_generic_500_without_internals():
    """Unexpected failures never leak internal details outside DEBUG."""
    with override_settings(DEBUG=False):
        client = Client(raise_request_exception=False)
        response = client.get("/crash/", secure=True, HTTP_X_REQUEST_ID="rid-500")

    assert response.status_code == 500
    error = _error_of(response)
    assert error["code"] == "SERVER_ERROR"
    assert error["message"] == "Error interno del servidor."
    assert error["details"] == {}
    assert error["request_id"] == "rid-500"
    assert "sentinel-internal-detail" not in response.content.decode()


def test_exception_handler_is_registered_in_settings():
    """DRF uses the envelope handler for every API error."""
    assert settings.REST_FRAMEWORK["EXCEPTION_HANDLER"] == (
        "config.exceptions.exception_handler"
    )


def test_pagination_is_registered_in_settings():
    """DRF uses the standard pagination class by default."""
    assert settings.REST_FRAMEWORK["DEFAULT_PAGINATION_CLASS"] == (
        "config.pagination.StandardPagination"
    )


@override_settings(ROOT_URLCONF="tests.api_urls")
def test_success_response_uses_the_universal_envelope(client):
    """A plain 200 is wrapped: ``data`` holds the body and ``meta`` the request id."""
    response = client.get("/echo/", secure=True, HTTP_X_REQUEST_ID="rid-ok-1")

    assert response.status_code == 200
    payload = success_of(response)
    assert payload["message"] == "Operación exitosa."
    assert payload["data"] == {"request_id": "rid-ok-1"}
    assert payload["meta"] == {"request_id": "rid-ok-1"}


def test_unmatched_api_route_returns_the_error_envelope(client):
    """A route that does not exist under ``/api/`` is JSON, not Django's HTML 404."""
    response = client.get("/api/v1/does-not-exist/", secure=True, HTTP_X_REQUEST_ID="rid-404")

    assert response.status_code == 404
    assert response["Content-Type"].startswith("application/json")
    error = _error_of(response)
    assert error["code"] == "NOT_FOUND"
    assert error["request_id"] == "rid-404"
