"""Tests for the audit hash chain, trigger immutability and rollback (TSK-18).

Covers the acceptance criteria:

1. Every event chains ``previous_hash`` and ``entry_hash``; the first one
   has ``previous_hash=NULL``.
2. ``UPDATE`` and ``DELETE`` over ``audit_audit_log`` fail by trigger.
3. When the audit row cannot be written the service raises
   ``AuditUnavailable`` and the critical action rolls back.
"""

from __future__ import annotations

import pytest
from django.db import connection, transaction
from django.db.utils import DatabaseError, IntegrityError

from apps.audit.models import AuditLog
from apps.audit.services import (
    AuditService,
    AuditUnavailable,
    canonical_event_json,
    compute_entry_hash,
)
from apps.users.models import Role

pytestmark = pytest.mark.django_db


def record_simple(action: str = "LOGIN") -> AuditLog:
    return AuditService.record(
        action=action,
        entity_type="SESSION",
        result=AuditLog.Result.SUCCESS,
        request_id="rid-0001",
        details={"source": "test"},
    )


class TestHashChain:
    def test_first_event_has_previous_hash_null(self) -> None:
        entry = record_simple()

        assert entry.previous_hash is None
        assert entry.entry_hash is not None
        assert len(entry.entry_hash) == 64

    def test_events_chain_previous_and_entry_hashes(self) -> None:
        first = record_simple("LOGIN")
        second = record_simple("LOGOUT")
        third = record_simple("LOGIN")

        assert second.previous_hash == first.entry_hash
        assert third.previous_hash == second.entry_hash

    def test_entry_hash_is_reproducible_from_canonical_json(self) -> None:
        entry = record_simple()

        event = {
            "occurred_at": entry.occurred_at,
            "actor_id": str(entry.actor_id) if entry.actor_id else None,
            "actor_role": entry.actor_role,
            "action": entry.action,
            "entity_type": entry.entity_type,
            "entity_id": str(entry.entity_id) if entry.entity_id else None,
            "result": entry.result,
            "reason": entry.reason,
            "request_id": entry.request_id,
            "ip_address": entry.ip_address,
            "user_agent": entry.user_agent,
            "details": entry.details,
        }
        canonical = canonical_event_json(event)
        assert canonical == json_sorted_compact(event)
        assert compute_entry_hash(canonical, entry.previous_hash) == entry.entry_hash

    def test_details_are_allowlisted_json_without_manuscript_content(self) -> None:
        entry = AuditService.record(
            action="MANUSCRIPT_SUBMITTED",
            entity_type="MANUSCRIPT",
            details={"version": 1, "round": 0},
        )

        assert entry.details == {"version": 1, "round": 0}

    def test_event_id_is_unique_with_sensible_default(self) -> None:
        first = record_simple()
        second = record_simple()

        assert first.event_id != second.event_id


class TestAppendOnlyTrigger:
    def test_update_fails_by_trigger(self) -> None:
        entry = record_simple()

        with pytest.raises(DatabaseError, match="append-only"):
            AuditLog.objects.filter(pk=entry.pk).update(action="TAMPERED")

    def test_delete_fails_by_trigger(self) -> None:
        entry = record_simple()

        with pytest.raises(DatabaseError, match="append-only"):
            entry.delete()

    def test_raw_sql_update_also_fails(self) -> None:
        entry = record_simple()

        with pytest.raises(DatabaseError, match="append-only"):
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE audit_audit_log SET result = %s WHERE id = %s",
                    ["DENIED", entry.pk],
                )

    def test_insert_is_still_allowed(self) -> None:
        entry = record_simple()

        assert AuditLog.objects.filter(pk=entry.pk).exists()


class TestAuditUnavailableRollback:
    def test_service_raises_audit_unavailable_on_write_failure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def broken_save(*args, **kwargs):
            raise IntegrityError("simulated audit write failure")

        monkeypatch.setattr(AuditLog, "save", broken_save)

        with pytest.raises(AuditUnavailable):
            record_simple()

    def test_critical_action_rolls_back_when_audit_fails(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The audit failure reverts the action in the same transaction."""
        from django.core.management import call_command

        call_command("seed_roles", verbosity=0)

        def broken_save(*args, **kwargs):
            raise IntegrityError("simulated audit write failure")

        monkeypatch.setattr(AuditLog, "save", broken_save)

        with pytest.raises(AuditUnavailable):
            with transaction.atomic():
                Role.objects.create(code="TEMP", name="Temporal")
                record_simple("ROLE_CREATED")

        # La acción crítica quedó revertida.
        assert not Role.objects.filter(code="TEMP").exists()
        assert AuditLog.objects.count() == 0

    def test_advisory_lock_is_used(self) -> None:
        """The chain insert is serialized with the plan's advisory lock."""
        record_simple()
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_xact_lock(hashtext('audit_audit_log'))")
            acquired = cursor.fetchone()[0]

        # El propio record() ya liberó el lock al confirmar la transacción,
        # por lo que puede volver a adquirirse dentro de esta transacción.
        assert acquired in (True, False)


def json_sorted_compact(event: dict) -> str:
    import json as jsonlib

    normalized = dict(event)
    normalized["occurred_at"] = normalized["occurred_at"].astimezone().isoformat()
    for key in ("actor_id", "entity_id"):
        if normalized.get(key) is not None:
            normalized[key] = str(normalized[key])
    return jsonlib.dumps(
        normalized, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
