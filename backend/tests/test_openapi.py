"""Documentación OpenAPI y Swagger UI (Fase 2).

Comprueba que el schema se genera y valida sin advertencias, que describe el
contrato universal tal como lo emite la API, que la página de Swagger UI respeta
la CSP de Nginx (`script-src 'self'`: ningún `<script>` en línea) y que, apagada,
la documentación no existe.
"""

from __future__ import annotations

import importlib
import json
import re
from io import StringIO

import pytest
import yaml
from django.core.management import call_command
from django.test import Client
from django.urls import clear_url_caches, set_urlconf


@pytest.fixture(scope="module")
def schema() -> dict:
    """El schema completo, generado con las mismas opciones que usa el CI."""
    out = StringIO()
    call_command("spectacular", validate=True, fail_on_warn=True, stdout=out)
    return yaml.safe_load(out.getvalue())


def _operations(schema: dict):
    for path, item in schema["paths"].items():
        for method, operation in item.items():
            if method in {"get", "post", "put", "patch", "delete"}:
                yield path, method, operation


def _json_schema(operation: dict, status: str) -> dict | None:
    content = operation["responses"].get(status, {}).get("content", {})
    return content.get("application/json", {}).get("schema")


class TestSchema:
    def test_it_generates_without_warnings_and_is_valid(self, schema) -> None:
        # ``fail_on_warn`` y ``validate`` del fixture ya fallan ante cualquier advertencia.
        assert schema["openapi"].startswith("3.")
        assert schema["info"]["title"] == "API de Gestión de Publicaciones Científicas"

    def test_every_path_is_versioned(self, schema) -> None:
        assert all(path.startswith("/api/v1/") for path in schema["paths"])

    def test_bearer_authentication_is_documented(self, schema) -> None:
        scheme = schema["components"]["securitySchemes"]["bearerAuth"]
        assert (scheme["type"], scheme["scheme"], scheme["bearerFormat"]) == (
            "http",
            "bearer",
            "JWT",
        )

    def test_every_operation_has_a_tag_and_a_summary(self, schema) -> None:
        for path, method, operation in _operations(schema):
            assert operation.get("tags"), (method, path)
            assert operation.get("summary"), (method, path)

    def test_public_endpoints_declare_no_security(self, schema) -> None:
        public = {
            ("post", "/api/v1/auth/login/"),
            ("post", "/api/v1/auth/refresh/"),
            ("get", "/api/v1/catalog/"),
            ("get", "/api/v1/health/"),
        }
        for path, method, operation in _operations(schema):
            if (method, path) in public:
                assert not operation.get("security"), (method, path)

    def test_protected_endpoints_document_401_and_403(self, schema) -> None:
        for path, method, operation in _operations(schema):
            if operation.get("security"):
                assert {"401", "403"} <= set(operation["responses"]), (method, path)

    def test_the_unversioned_health_alias_is_not_duplicated(self, schema) -> None:
        assert "/api/health/" not in schema["paths"]
        assert "/api/v1/health/" in schema["paths"]


class TestEnvelopeInTheSchema:
    def test_the_contract_components_exist(self, schema) -> None:
        components = schema["components"]["schemas"]
        for name in (
            "SuccessEnvelope",
            "PaginatedSuccessEnvelope",
            "ErrorEnvelope",
            "ErrorEntry",
            "ResponseMeta",
            "PaginationMeta",
        ):
            assert name in components, name
        assert set(components["ErrorEnvelope"]["required"]) == {
            "success",
            "message",
            "data",
            "errors",
            "meta",
        }

    def test_every_json_success_is_wrapped(self, schema) -> None:
        for path, method, operation in _operations(schema):
            for status in operation["responses"]:
                if not status.startswith("2"):
                    continue
                body = _json_schema(operation, status)
                if body is None:
                    continue
                refs = json.dumps(body)
                assert "SuccessEnvelope" in refs, (method, path, status)

    def test_every_error_response_is_the_error_envelope(self, schema) -> None:
        for path, method, operation in _operations(schema):
            for status, response in operation["responses"].items():
                if status[0] in "45":
                    body = _json_schema(operation, status)
                    assert body == {"$ref": "#/components/schemas/ErrorEnvelope"}, (
                        method,
                        path,
                        status,
                    )

    def test_lists_are_documented_as_paginated_with_page_parameters(self, schema) -> None:
        lists = 0
        for path, method, operation in _operations(schema):
            names = {parameter["name"] for parameter in operation.get("parameters", [])}
            paginated = "PaginatedSuccessEnvelope" in json.dumps(_json_schema(operation, "200"))
            assert ("page" in names) == paginated, (method, path)
            lists += paginated
        assert lists >= 14

    def test_file_downloads_are_not_wrapped(self, schema) -> None:
        for path in (
            "/api/v1/catalog/{code}/document/",
            "/api/v1/reviewer/assignments/{id}/document/",
        ):
            content = schema["paths"][path]["get"]["responses"]["200"]["content"]
            assert set(content) == {"application/pdf"}, path

    def test_the_no_content_endpoints_have_no_body(self, schema) -> None:
        assert "content" not in schema["paths"]["/api/v1/auth/logout/"]["post"]["responses"]["204"]


class TestSwaggerUi:
    def test_the_schema_endpoint_serves_yaml(self, client: Client) -> None:
        response = client.get("/api/v1/schema/", secure=True)

        assert response.status_code == 200
        assert yaml.safe_load(response.content)["info"]["version"] == "1.0.0"

    def test_the_docs_page_has_no_inline_script(self, client: Client) -> None:
        """Nginx sirve ``script-src 'self'``: un `<script>` en línea no se ejecutaría."""
        response = client.get("/api/v1/docs/", secure=True)

        assert response.status_code == 200
        html = response.content.decode()
        scripts = re.findall(r"<script\b([^>]*)>(.*?)</script>", html, re.S)
        assert scripts, "la página debe cargar Swagger UI"
        for attributes, body in scripts:
            assert "src=" in attributes, "script en línea: lo bloquearía la CSP"
            assert not body.strip(), "script en línea: lo bloquearía la CSP"

    def test_the_docs_assets_come_from_this_origin(self, client: Client) -> None:
        html = client.get("/api/v1/docs/", secure=True).content.decode()

        sources = re.findall(r'(?:src|href)="([^"]+)"', html)
        assert sources
        assert all(not source.startswith(("http:", "https:", "//")) for source in sources)

    def test_the_docs_script_is_served_separately(self, client: Client) -> None:
        html = client.get("/api/v1/docs/", secure=True).content.decode()
        script_url = next(
            source for source in re.findall(r'src="([^"]+)"', html) if "script" in source
        )

        response = client.get(script_url, secure=True)

        assert response.status_code == 200
        assert "javascript" in response["Content-Type"]
        assert "/api/v1/schema/" in response.content.decode()

    def test_the_docs_need_no_session(self, client: Client) -> None:
        assert client.get("/api/v1/docs/", secure=True).status_code == 200
        assert client.get("/api/v1/schema/", secure=True).status_code == 200


def _reload_urls() -> None:
    from config import api as api_module
    from config import urls as project_urls

    importlib.reload(api_module)
    importlib.reload(project_urls)
    clear_url_caches()
    set_urlconf(None)


def test_the_docs_do_not_exist_when_switched_off(settings, client: Client) -> None:
    """Con ``API_DOCS_ENABLED`` apagado las rutas no se montan y responden 404."""
    try:
        settings.API_DOCS_ENABLED = False
        _reload_urls()
        for path in ("/api/v1/docs/", "/api/v1/schema/", "/api/v1/schema.json"):
            assert client.get(path, secure=True).status_code == 404, path
        # La API sigue funcionando.
        assert client.get("/api/v1/", secure=True).status_code == 200
    finally:
        settings.API_DOCS_ENABLED = True  # el valor de desarrollo con el que corre la suite
        _reload_urls()
        assert client.get("/api/v1/docs/", secure=True).status_code == 200
