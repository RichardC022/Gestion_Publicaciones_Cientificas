"""El contrato universal en los endpoints reales de ``/api/v1/``.

``test_envelope.py`` prueba el renderer y el manejador de excepciones con vistas
de prueba; aquí se comprueba que los endpoints de verdad —éxito, lista paginada,
error de autenticación, error de validación, recurso inexistente y health— lo
cumplen. Todo se lee de ``response.content`` en bruto (``tests/contract.py``),
no de ``response.json()``, que en la suite entrega la carga de dominio.
"""

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from tests.contract import ENVELOPE_KEYS, error_of, failure_of, raw_payload, success_of

pytestmark = pytest.mark.django_db


@pytest.fixture
def api() -> APIClient:
    return APIClient()


def test_api_root_is_a_success_envelope(api) -> None:
    response = api.get("/api/v1/", secure=True)

    assert response.status_code == 200
    payload = success_of(response)
    assert payload["data"] == {"service": "gestion-publicaciones-cientificas", "api": "v1"}
    assert payload["meta"]["request_id"] == response["X-Request-ID"]


def test_public_catalog_list_is_paginated_in_meta(api) -> None:
    response = api.get("/api/v1/catalog/", secure=True)

    assert response.status_code == 200
    payload = success_of(response)
    assert isinstance(payload["data"], list)
    assert set(payload["meta"]["pagination"]) == {"count", "next", "previous"}
    # Los contadores viven en meta: ``data`` es la lista, sin ``results``.
    assert "results" not in payload["data"]


def test_missing_credentials_is_an_error_envelope(api) -> None:
    response = api.get("/api/v1/auth/me/", secure=True)

    assert response.status_code == 401
    payload = failure_of(response)
    assert payload["errors"][0]["code"] == "AUTH_INVALID"
    assert payload["meta"]["request_id"] == response["X-Request-ID"]


def test_unknown_catalog_entry_is_a_not_found_envelope(api) -> None:
    response = api.get("/api/v1/catalog/GPC-0000-000000/", secure=True)

    assert response.status_code == 404
    assert error_of(response)["code"] == "NOT_FOUND"


def test_invalid_login_body_is_a_validation_envelope(api) -> None:
    response = api.post("/api/v1/auth/login/", {}, format="json", secure=True)

    assert response.status_code == 400
    payload = failure_of(response)
    assert {entry["code"] for entry in payload["errors"]} == {"VALIDATION_ERROR"}
    # Una entrada por campo faltante, con el detalle original del campo.
    assert all(entry["field"] for entry in payload["errors"])


def test_health_answers_with_the_envelope_on_both_paths(api, tmp_path) -> None:
    with override_settings(MEDIA_ROOT=tmp_path):
        versioned = api.get("/api/v1/health/", secure=True)
        unversioned = api.get("/api/health/", secure=True)

    for response in (versioned, unversioned):
        assert response.status_code == 200
        assert success_of(response)["data"] == {"status": "ok"}


def test_every_json_response_is_an_envelope_or_has_no_body(api) -> None:
    """Ningún endpoint devuelve JSON fuera del contrato: éxito o error, nunca otra forma."""
    for url in ("/api/v1/", "/api/v1/auth/me/", "/api/v1/catalog/", "/api/v1/nope/"):
        response = api.get(url, secure=True)
        assert response["Content-Type"].startswith("application/json"), url
        assert set(raw_payload(response)) == ENVELOPE_KEYS, url
