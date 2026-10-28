"""Administrator view of the audit trail (plan sections 2.7 and 2.8, TSK-73).

``AdminAuditSerializer`` shows who did what, to which entity, with which
result and when, plus the chain hashes. It never carries manuscript
content, confidential comments, free text (``reason``) or personal data
(``ip_address``, ``user_agent``); the actor is an opaque id, never a name
or an e-mail. ``details`` goes through an allowlist of scalar keys, so a
future event cannot leak a field nobody reviewed, and the reviewer id some
assignment events store is left out.

The correction eligibility (``can_authorize_correction``) is *not* here: it
is computed and exposed by TSK-77, so this detail never implies a write
permission.
"""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from apps.audit.models import AuditLog

#: ``details`` keys an administrator may see. Anything else is dropped.
DETAILS_ALLOWLIST = frozenset(
    {
        "assignment_id",
        "assignment_revoked",
        "cause",
        "code",
        "due_at",
        "is_active",
        "lock_version",
        "manuscript_id",
        "previous_status",
        "report_type",
        "resolution",
        "round_number",
        "status",
        "version_number",
    }
)
MANUSCRIPT_ENTITY = "MANUSCRIPT"


def safe_details(details: Any) -> dict[str, Any]:
    """Keep only allowlisted keys whose value is a plain scalar."""
    if not isinstance(details, dict):
        return {}
    return {
        key: value
        for key, value in details.items()
        if key in DETAILS_ALLOWLIST
        and (value is None or isinstance(value, (str, int, float, bool)))
    }


def manuscript_id_of(entry: AuditLog) -> str | None:
    """Manuscript an event is about: its own entity or the one in ``details``."""
    if entry.entity_type == MANUSCRIPT_ENTITY and entry.entity_id:
        return str(entry.entity_id)
    value = entry.details.get("manuscript_id") if isinstance(entry.details, dict) else None
    return value if isinstance(value, str) else None


class AdminAuditSerializer(serializers.ModelSerializer):
    """One audit event, minimized for the administrator."""

    id = serializers.UUIDField(source="event_id", read_only=True)
    actor_id = serializers.SerializerMethodField()
    manuscript_id = serializers.SerializerMethodField()
    manuscript_code = serializers.SerializerMethodField()
    details = serializers.SerializerMethodField()

    class Meta:
        model = AuditLog
        fields = (
            "id",
            "occurred_at",
            "actor_id",
            "actor_role",
            "action",
            "entity_type",
            "entity_id",
            "manuscript_id",
            "manuscript_code",
            "result",
            "request_id",
            "details",
            "previous_hash",
            "entry_hash",
        )
        read_only_fields = fields

    def get_actor_id(self, entry: AuditLog) -> str | None:
        return str(entry.actor_id) if entry.actor_id else None

    def get_manuscript_id(self, entry: AuditLog) -> str | None:
        return manuscript_id_of(entry)

    def get_manuscript_code(self, entry: AuditLog) -> str | None:
        codes: dict[str, str] = self.context.get("manuscript_codes", {})
        manuscript_id = manuscript_id_of(entry)
        return codes.get(manuscript_id) if manuscript_id else None

    def get_details(self, entry: AuditLog) -> dict[str, Any]:
        return safe_details(entry.details)
