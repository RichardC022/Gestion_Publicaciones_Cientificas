"""Sanitized payload of a notice (plan sections 1.18, 2.9 and 6.7, TSK-75).

A payload is built ONLY from the fields below, each one a plain string
chosen by the receiver that creates the notice: the event, the public
manuscript code and title, the action expected, the deadline and a link
into the SPA. :func:`build_payload` rejects any other key, so nothing
(an author's name, a reviewer's id, a confidential comment, the free text
of a revocation or an incident) can ride along by accident. The double-blind
guarantee is therefore structural: the notices addressed to a reviewer are
made of the same allowlisted fields as the ones addressed to an author, and
none of those fields is an identity.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

#: The only keys a payload may carry.
PAYLOAD_FIELDS = (
    "title",
    "message",
    "manuscript_code",
    "manuscript_title",
    "action",
    "due_at",
    "link",
)
REQUIRED_FIELDS = ("title", "message", "link")


def build_payload(**fields: Any) -> dict[str, str | None]:
    """The sanitized payload, or ``ValueError`` if a field is not allowed."""
    unknown = set(fields) - set(PAYLOAD_FIELDS)
    if unknown:
        raise ValueError(f"Campos no permitidos en el aviso: {', '.join(sorted(unknown))}")
    missing = [name for name in REQUIRED_FIELDS if not fields.get(name)]
    if missing:
        raise ValueError(f"Faltan campos del aviso: {', '.join(missing)}")
    payload: dict[str, str | None] = {}
    for name in PAYLOAD_FIELDS:
        value = fields.get(name)
        if isinstance(value, datetime):
            value = value.isoformat()
        payload[name] = None if value is None else str(value)
    return payload
