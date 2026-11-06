"""Aserciones del contrato JSON universal ``{success, message, data, errors, meta}``.

Estas funciones leen ``response.content`` en bruto, sin la ayuda de
``conftest.py`` que entrega la carga de dominio en ``response.json()``, y por eso
son las que prueban de verdad la forma que ve un cliente HTTP.
"""

from __future__ import annotations

import json
from typing import Any

ENVELOPE_KEYS = {"success", "message", "data", "errors", "meta"}
ERROR_ENTRY_KEYS = {"code", "message", "field", "details"}


def raw_payload(response) -> dict[str, Any]:
    """Return the decoded JSON body exactly as the client receives it."""
    return json.loads(response.content)


def success_of(response) -> dict[str, Any]:
    """Assert the success envelope and return the whole payload."""
    payload = raw_payload(response)
    assert set(payload.keys()) == ENVELOPE_KEYS
    assert payload["success"] is True
    assert isinstance(payload["message"], str) and payload["message"]
    assert payload["errors"] == []
    assert "request_id" in payload["meta"]
    return payload


def failure_of(response) -> dict[str, Any]:
    """Assert the error envelope and return the whole payload."""
    payload = raw_payload(response)
    assert set(payload.keys()) == ENVELOPE_KEYS
    assert payload["success"] is False
    assert isinstance(payload["message"], str) and payload["message"]
    assert payload["data"] is None
    assert payload["errors"], "un error debe traer al menos una entrada en errors"
    for entry in payload["errors"]:
        assert set(entry.keys()) == ERROR_ENTRY_KEYS
    assert "request_id" in payload["meta"]
    return payload


def error_of(response) -> dict[str, Any]:
    """Assert the error envelope and return its first error as a flat dict.

    The result has ``code``, ``message`` (the top-level one), ``details`` and
    ``request_id`` so assertions read like the domain they check.
    """
    payload = failure_of(response)
    first = payload["errors"][0]
    return {
        "code": first["code"],
        "message": payload["message"],
        "details": first["details"],
        "request_id": payload["meta"]["request_id"],
    }
