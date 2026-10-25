"""Audit chain and rollback over the real authentication flow (TSK-23).

The hash chain built by ``AuditService`` is verified over events
produced by the actual API flow — login and logout through
``APIClient`` — and the critical actions are proven to roll back with
``503`` when the audit trail cannot be written (plan section 6.5).
"""

from __future__ import annotations

import base64
import json

import pytest
from django.conf import settings
from django.core.management import call_command
from django.db.utils import IntegrityError
from rest_framework.test import APIClient

from apps.audit.models import AuditLog
from apps.audit.services import canonical_event_json, compute_entry_hash
from apps.users.models import LoginAttempt
from apps.users.models import RefreshToken as RefreshTokenRecord
from tests.factories import FACTORY_PASSWORD, UserFactory, UserRoleFactory

pytestmark = pytest.mark.django_db

LOGIN_URL = "/api/auth/login/"
LOGOUT_URL = "/api/auth/logout/"
COOKIE = settings.REFRESH_COOKIE_NAME


def with_roles(user, *codes):
    """Seed the catalog and attach active roles to a factory account."""
    call_command("seed_roles", verbosity=0)
    for code in codes:
        UserRoleFactory(user=user, role_code=code)
    return user


def login(identifier: str):
    """Log in through the real endpoint and return the authenticated client."""
    client = APIClient()
    response = client.post(
        LOGIN_URL,
        {"identifier": identifier, "password": FACTORY_PASSWORD},
        format="json",
    )
    assert response.status_code == 200
    return client, response


def _jti_of(token: str) -> str:
    """Extract the ``jti`` claim of a JWT without verifying it."""
    segment = token.split(".")[1]
    padded = segment + "=" * (-len(segment) % 4)
    return json.loads(base64.urlsafe_b64decode(padded))["jti"]


def _event_payload(entry: AuditLog) -> dict:
    """Rebuild the canonical event of a persisted audit row."""
    return {
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


def _break_audit_writes(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken_save(*args, **kwargs):
        raise IntegrityError("simulated audit write failure")

    monkeypatch.setattr(AuditLog, "save", broken_save)


class TestAuthFlowChain:
    def test_login_and_logout_events_stay_chained(self) -> None:
        user = with_roles(UserFactory(), "EDITOR")
        client, response = login(user.institutional_id)
        access = response.json()["access"]

        logout = client.post(LOGOUT_URL, HTTP_AUTHORIZATION=f"Bearer {access}")
        assert logout.status_code == 204

        events = list(
            AuditLog.objects.filter(action__in=("LOGIN", "LOGOUT")).order_by("id")
        )
        assert [entry.action for entry in events] == ["LOGIN", "LOGOUT"]
        assert events[0].previous_hash is None

        # Cada entrada enlaza con la anterior y su hash se recalcula
        # exactamente desde el JSON canónico persistido.
        previous = None
        for entry in events:
            assert entry.previous_hash == previous
            canonical = canonical_event_json(_event_payload(entry))
            assert (
                compute_entry_hash(canonical, entry.previous_hash)
                == entry.entry_hash
            )
            previous = entry.entry_hash

    def test_failed_audit_answers_503_and_reverts_the_login(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        user = with_roles(UserFactory(), "AUTHOR")
        _break_audit_writes(monkeypatch)

        client = APIClient()
        response = client.post(
            LOGIN_URL,
            {"identifier": user.institutional_id, "password": FACTORY_PASSWORD},
            format="json",
        )

        assert response.status_code == 503
        assert response.json()["error"]["code"] == "AUDIT_UNAVAILABLE"
        # La operación crítica quedó revertida por completo.
        assert RefreshTokenRecord.objects.count() == 0
        assert LoginAttempt.objects.count() == 0
        assert AuditLog.objects.count() == 0

    def test_failed_audit_on_logout_keeps_the_refresh_valid(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        user = with_roles(UserFactory(), "AUTHOR")
        client, response = login(user.institutional_id)
        access = response.json()["access"]
        jti = _jti_of(client.cookies[COOKIE].value)

        _break_audit_writes(monkeypatch)
        logout = client.post(LOGOUT_URL, HTTP_AUTHORIZATION=f"Bearer {access}")

        assert logout.status_code == 503
        assert logout.json()["error"]["code"] == "AUDIT_UNAVAILABLE"
        # La revocación se revirtió con la auditoría: el refresh sigue vigente.
        record = RefreshTokenRecord.objects.get(jti=jti)
        assert record.revoked_at is None
