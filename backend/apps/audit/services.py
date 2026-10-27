"""Audit service: canonical hashing and chain serialization.

`AuditService.record()` must be called **inside** the same transaction as
the critical action it documents (plan section 6.5). If the audit row
cannot be written, the service raises :class:`AuditUnavailable` and the
caller rolls the action back and answers with ``503``.

The insert is serialized across concurrent workers with a transaction
scoped advisory lock (plan section 1.20):

    SELECT pg_advisory_xact_lock(hashtext('audit_audit_log'));

The chain is ``entry_hash = sha256(canonical_json(event) + previous_hash)``
with ``previous_hash=NULL`` for the very first entry (plan section 4.5).
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any
from uuid import UUID

from django.db import connection
from django.utils import timezone

from apps.audit.models import AuditLog

AUDIT_LOCK_KEY = "audit_audit_log"

# Campos que participan en el hash canónico; nunca previous_hash ni entry_hash.
HASH_FIELDS: tuple[str, ...] = (
    "occurred_at",
    "actor_id",
    "actor_role",
    "action",
    "entity_type",
    "entity_id",
    "result",
    "reason",
    "request_id",
    "ip_address",
    "user_agent",
    "details",
)


class AuditUnavailable(Exception):
    """The audit trail cannot be written; the critical action must roll back."""


def canonical_event_json(event: dict[str, Any]) -> str:
    """Serialize the audited fields to canonical JSON.

    Sorted keys, no unnecessary whitespace, UTF-8 (plan section 4.5).
    ``occurred_at`` is normalized to an ISO-8601 UTC string so the hash is
    reproducible by ``verify_integrity`` (TSK-76).
    """

    def normalize(value: Any) -> Any:
        if isinstance(value, datetime):
            return value.astimezone().isoformat()
        if isinstance(value, UUID):
            return str(value)
        return value

    payload = {field: normalize(event.get(field)) for field in sorted(HASH_FIELDS)}
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def compute_entry_hash(canonical_json: str, previous_hash: str | None) -> str:
    """SHA-256 over the canonical JSON plus the previous entry hash."""
    digest = hashlib.sha256()
    digest.update(canonical_json.encode("utf-8"))
    digest.update((previous_hash or "").encode("utf-8"))
    return digest.hexdigest()


class AuditService:
    """Append a chained, immutable audit event to the current transaction."""

    @staticmethod
    def record(
        *,
        action: str,
        entity_type: str,
        result: str = AuditLog.Result.SUCCESS,
        actor: Any = None,
        actor_id: UUID | None = None,
        actor_role: str | None = None,
        entity_id: UUID | None = None,
        reason: str | None = None,
        request_id: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        details: dict[str, Any] | None = None,
        occurred_at: datetime | None = None,
    ) -> AuditLog:
        """Persist one audit row, chaining it to the previous entry.

        Raises :class:`AuditUnavailable` if the audit row cannot be
        written, so the caller can revert the critical action and
        respond with ``503``.
        """
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_advisory_xact_lock(hashtext(%s))",
                    [AUDIT_LOCK_KEY],
                )

            latest = (
                AuditLog.objects.order_by("-id")
                .values_list("entry_hash", flat=True)
                .first()
            )

            event = {
                "occurred_at": occurred_at or timezone.now(),
                "actor_id": str(actor.pk) if actor is not None else (
                    str(actor_id) if actor_id else None
                ),
                "actor_role": actor_role,
                "action": action,
                "entity_type": entity_type,
                "entity_id": str(entity_id) if entity_id else None,
                "result": result,
                "reason": reason,
                "request_id": request_id,
                "ip_address": ip_address,
                "user_agent": user_agent,
                "details": details or {},
            }
            canonical = canonical_event_json(event)
            entry_hash = compute_entry_hash(canonical, latest)

            return AuditLog.objects.create(
                occurred_at=event["occurred_at"],
                actor_id=event["actor_id"],
                actor_role=actor_role,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                result=result,
                reason=reason,
                request_id=request_id,
                ip_address=ip_address,
                user_agent=user_agent,
                details=event["details"],
                previous_hash=latest,
                entry_hash=entry_hash,
            )
        except AuditUnavailable:
            raise
        except Exception as exc:
            raise AuditUnavailable(
                f"No se pudo registrar el evento de auditoría: {exc}"
            ) from exc
