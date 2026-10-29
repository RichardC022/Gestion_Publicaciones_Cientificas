"""Administrator view of the audit trail (plan sections 2.7 and 2.8, TSK-73).

``AdminAuditSerializer`` shows who did what, to which entity, with which
result and when, plus the chain hashes. It never carries manuscript
content, confidential comments, free text (``reason``) or personal data
(``ip_address``, ``user_agent``); the actor is an opaque id, never a name
or an e-mail. ``details`` goes through an allowlist of scalar keys, so a
future event cannot leak a field nobody reviewed, and the reviewer id some
assignment events store is left out.

The list never computes a write permission. The detail
(:class:`AdminAuditDetailSerializer`, TSK-77) adds ``can_authorize_correction``
and a minimal ``verdict`` block (code, decision, date) ONLY for the events
that are about a verdict; the flag comes from the same rule the
authorization endpoint applies, so the SPA never infers it.
"""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError
from rest_framework import serializers

from apps.audit.models import AuditLog

#: ``details`` keys an administrator may see. Anything else is dropped.
DETAILS_ALLOWLIST = frozenset(
    {
        "assignment_id",
        "assignment_revoked",
        "cause",
        "code",
        "decision",
        "due_at",
        "is_active",
        "lock_version",
        "manuscript_id",
        "previous_status",
        "report_type",
        "resolution",
        "round_number",
        "status",
        "verdict_id",
        "version_number",
    }
)
#: Events whose detail tells whether the verdict can be corrected.
VERDICT_ACTIONS = frozenset(
    {"VERDICT_REGISTERED", "VERDICT_CORRECTED", "VERDICT_CORRECTION_AUTHORIZED"}
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


class AdminAuditDetailSerializer(AdminAuditSerializer):
    """The detail of an event; for verdict events it adds the correction flag."""

    class Meta(AdminAuditSerializer.Meta):
        pass

    def to_representation(self, entry: AuditLog) -> dict[str, Any]:
        data = super().to_representation(entry)
        if entry.action not in VERDICT_ACTIONS:
            return data
        # Import tardío: `audit` no depende de `publications` al cargar.
        from apps.publications.models import Verdict
        from apps.publications.services.corrections import can_authorize_correction

        verdict = None
        raw = entry.details.get("verdict_id") if isinstance(entry.details, dict) else None
        if isinstance(raw, str):
            try:
                verdict = (
                    Verdict.objects.select_related("manuscript", "version").filter(pk=raw).first()
                )
            except (ValueError, ValidationError):
                verdict = None
        data["can_authorize_correction"] = bool(verdict) and can_authorize_correction(verdict)
        if verdict is not None:
            data["verdict"] = {
                "id": str(verdict.pk),
                "manuscript_code": verdict.manuscript.code,
                "decision": verdict.decision,
                "decided_at": serializers.DateTimeField().to_representation(verdict.created_at),
            }
        return data
