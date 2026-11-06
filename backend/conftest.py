"""Configuración compartida de pytest.

``response.json()`` entrega la carga de dominio, no el sobre
-------------------------------------------------------------
La API responde con el contrato universal ``{success, message, data, errors,
meta}`` (``config.renderers``). Las pruebas de dominio —cientos de lecturas de
``response.json()``— se escribieron antes de ese contrato y comprueban *qué
dice* la API, no *cómo la envuelve*. Para que sigan leyéndose como el dominio,
este módulo hace que ``response.json()`` desenvuelva el sobre:

* éxito → ``data``; una lista paginada → ``{count, next, previous, results}``
  (más cualquier dato extra que la vista haya puesto en ``meta``);
* error → ``{"error": {code, message, details, request_id}}``, con ``details``
  reconstruido desde ``errors``.

Esto **no** debilita la prueba del contrato: ``tests/contract.py`` lee
``response.content`` en bruto y es lo que usan ``test_envelope.py``,
``test_pagination.py``, ``test_health.py`` y ``test_contract_envelope.py`` para
verificar la forma exacta que ve un cliente HTTP. ``response.content`` nunca se
altera.
"""

from __future__ import annotations

from typing import Any

from django.test import client as django_client

from config.renderers import is_envelope

_PAGE_META_KEYS = {"request_id", "pagination"}


def unwrap_envelope(payload: Any) -> Any:
    """Return the domain payload of a universal-contract body (identity otherwise)."""
    if not is_envelope(payload):
        return payload

    meta = payload["meta"] or {}
    if not payload["success"]:
        errors = payload["errors"] or [{}]
        if all(entry.get("field") is not None for entry in errors):
            details: Any = {entry["field"]: entry["details"] for entry in errors}
        else:
            details = errors[0].get("details", {})
        return {
            "error": {
                "code": errors[0].get("code"),
                "message": payload["message"],
                "details": details,
                "request_id": meta.get("request_id"),
            }
        }

    pagination = meta.get("pagination")
    if pagination is None:
        return payload["data"]
    page = {**pagination, "results": payload["data"]}
    page.update({key: value for key, value in meta.items() if key not in _PAGE_META_KEYS})
    return page


_original_parse_json = django_client.Client._parse_json


def _parse_json_unwrapped(self, response, **extra):
    if not hasattr(response, "_domain_json"):
        response._domain_json = unwrap_envelope(_original_parse_json(self, response, **extra))
    return response._domain_json


django_client.Client._parse_json = _parse_json_unwrapped
