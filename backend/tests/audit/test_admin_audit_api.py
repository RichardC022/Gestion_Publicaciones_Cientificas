"""Tests for the administrator audit query (TSK-73, plan section 2.7).

Acceptance criteria: only ``ADMIN`` gets in and every query is audited; the
response carries no manuscript content, confidential comments or personal
data; and the detail does not infer a write permission (the correction
eligibility belongs to TSK-77).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone as dt_timezone
from uuid import uuid4

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.audit.services import AuditService, AuditUnavailable
from tests.factories import ManuscriptFactory, UserFactory
from tests.publications.test_manuscript_api import actor, client_for

pytestmark = pytest.mark.django_db

LIST_URL = "/api/admin/audit/"


@pytest.fixture(autouse=True)
def seeded_roles(db) -> None:
    call_command("seed_roles", verbosity=0)


@pytest.fixture
def admin():
    return actor("ADMIN")


@pytest.fixture
def client(admin):
    return client_for(admin)


def record(action="LOGIN", entity_type="SESSION", **overrides) -> AuditLog:
    return AuditService.record(action=action, entity_type=entity_type, **overrides)


def queries() -> list[AuditLog]:
    return list(AuditLog.objects.filter(action__in=("AUDIT_QUERIED", "AUDIT_DETAIL_VIEWED")))


class TestAccess:
    def test_anonymous_gets_401(self) -> None:
        from rest_framework.test import APIClient

        assert APIClient().get(LIST_URL).status_code == 401

    @pytest.mark.parametrize("role", ["AUTHOR", "REVIEWER", "EDITOR"])
    def test_other_roles_get_403_on_list_and_detail(self, role) -> None:
        user = client_for(actor(role))
        entry = record()

        assert user.get(LIST_URL).status_code == 403
        assert user.get(f"{LIST_URL}{entry.event_id}/").status_code == 403
        assert queries() == []

    def test_admin_gets_200(self, client) -> None:
        assert client.get(LIST_URL).status_code == 200

    def test_a_user_without_active_admin_role_is_refused(self) -> None:
        user = actor("ADMIN")
        user.role_assignments.update(is_active=False, revoked_at=timezone.now())

        assert client_for(user).get(LIST_URL).status_code == 403


class TestSelfAudit:
    def test_each_list_query_is_audited_with_its_filters(self, client, admin) -> None:
        client.get(LIST_URL, {"action": "LOGIN", "result": "SUCCESS"})

        (event,) = queries()
        assert event.action == "AUDIT_QUERIED"
        assert event.entity_type == "AUDIT_LOG"
        assert event.actor_id == admin.pk
        assert event.actor_role == "ADMIN"
        assert event.result == "SUCCESS"
        assert event.details["filters"] == {"action": "LOGIN", "result": "SUCCESS"}

    def test_each_detail_view_is_audited_against_the_event(self, client, admin) -> None:
        entry = record()

        client.get(f"{LIST_URL}{entry.event_id}/")

        (event,) = queries()
        assert event.action == "AUDIT_DETAIL_VIEWED"
        assert event.entity_id == entry.event_id
        assert event.actor_id == admin.pk

    def test_queries_extend_the_hash_chain(self, client) -> None:
        client.get(LIST_URL)
        client.get(LIST_URL)

        first, second = AuditLog.objects.order_by("id")
        assert first.previous_hash is None
        assert second.previous_hash == first.entry_hash

    def test_a_rejected_filter_is_not_audited(self, client) -> None:
        assert client.get(LIST_URL, {"result": "NOPE"}).status_code == 400
        assert queries() == []

    def test_if_the_query_cannot_be_audited_nothing_is_returned(self, client, monkeypatch) -> None:
        record()

        def broken(**kwargs):
            raise AuditUnavailable("sin auditoría")

        monkeypatch.setattr("apps.audit.views.AuditService.record", broken)
        response = client.get(LIST_URL)

        assert response.status_code == 503
        assert response.json()["error"]["code"] == "AUDIT_UNAVAILABLE"
        assert "results" not in response.json()


class TestMinimization:
    def test_response_has_no_personal_data_or_free_text(self, client) -> None:
        person = UserFactory(email="privado.persona@unl.edu.ec", first_name="Marcela", last_name="Quizhpe")
        record(
            action="ASSIGNMENT_REVOKED",
            entity_type="ASSIGNMENT",
            actor=person,
            actor_role="EDITOR",
            reason="Texto libre del editor con el nombre Marcela",
            ip_address="10.20.30.40",
            user_agent="Mozilla/5.0 (X11)",
        )

        text = client.get(LIST_URL).content.decode()
        row = client.get(LIST_URL).json()["results"][-1]

        for forbidden in ("privado.persona", "Marcela", "Quizhpe", "10.20.30.40", "Mozilla", "Texto libre"):
            assert forbidden not in text
        assert not {"ip_address", "user_agent", "reason", "actor_email", "actor_name"} & set(row)
        assert row["actor_id"] == str(person.pk)

    def test_fields_are_exactly_the_planned_ones(self, client) -> None:
        record()

        row = client.get(LIST_URL).json()["results"][-1]

        assert set(row) == {
            "id", "occurred_at", "actor_id", "actor_role", "action", "entity_type",
            "entity_id", "manuscript_id", "manuscript_code", "result", "request_id",
            "details", "previous_hash", "entry_hash",
        }

    def test_details_keep_only_allowlisted_scalars(self, client) -> None:
        record(
            action="ASSIGNMENT_CREATED",
            entity_type="ASSIGNMENT",
            details={
                "manuscript_id": str(uuid4()),
                "reviewer_id": str(uuid4()),
                "code": "MS-1",
                "due_at": "2026-11-20T10:00:00",
                "free_text": "contenido del manuscrito",
                "nested": {"status": "x"},
                "list": [1, 2],
                "status": "ACTIVE",
            },
        )

        details = client.get(LIST_URL).json()["results"][-1]["details"]

        assert set(details) == {"manuscript_id", "code", "due_at", "status"}

    def test_response_never_mentions_the_reviewer_id(self, client) -> None:
        reviewer_id = str(uuid4())
        record(action="ASSIGNMENT_CREATED", entity_type="ASSIGNMENT", details={"reviewer_id": reviewer_id})

        assert reviewer_id not in client.get(LIST_URL).content.decode()


class TestManuscriptReference:
    def test_manuscript_code_is_resolved_and_nothing_else_of_it(self, client) -> None:
        manuscript = ManuscriptFactory(title="Titulo confidencial del articulo")
        record(action="MANUSCRIPT_SUBMITTED", entity_type="MANUSCRIPT", entity_id=manuscript.pk)
        record(
            action="EVALUATION_SUBMITTED",
            entity_type="EVALUATION",
            entity_id=uuid4(),
            details={"manuscript_id": str(manuscript.pk)},
        )

        response = client.get(LIST_URL)
        rows = [r for r in response.json()["results"] if r["manuscript_id"]]

        assert {r["manuscript_id"] for r in rows} == {str(manuscript.pk)}
        assert {r["manuscript_code"] for r in rows} == {manuscript.code}
        assert "Titulo confidencial" not in response.content.decode()


class TestFilters:
    def test_by_actor(self, client) -> None:
        one, other = UserFactory(), UserFactory()
        record(actor=one)
        record(actor=other)

        rows = client.get(LIST_URL, {"actor": str(one.pk)}).json()["results"]

        assert [r["actor_id"] for r in rows] == [str(one.pk)]

    def test_by_action_and_result(self, client) -> None:
        record("LOGIN", result="SUCCESS")
        record("LOGIN", result="DENIED")
        record("LOGOUT", result="SUCCESS")

        rows = client.get(LIST_URL, {"action": "LOGIN", "result": "DENIED"}).json()["results"]

        assert [(r["action"], r["result"]) for r in rows] == [("LOGIN", "DENIED")]

    def test_by_manuscript_matches_entity_and_details(self, client) -> None:
        manuscript, other = uuid4(), uuid4()
        record("MANUSCRIPT_SUBMITTED", "MANUSCRIPT", entity_id=manuscript)
        record("EVALUATION_SUBMITTED", "EVALUATION", details={"manuscript_id": str(manuscript)})
        record("MANUSCRIPT_SUBMITTED", "MANUSCRIPT", entity_id=other)

        rows = client.get(LIST_URL, {"manuscript": str(manuscript)}).json()["results"]

        assert sorted(r["action"] for r in rows) == ["EVALUATION_SUBMITTED", "MANUSCRIPT_SUBMITTED"]

    def test_by_date_range_is_inclusive(self, client) -> None:
        today = timezone.localdate()
        old = record("OLD", occurred_at=timezone.now() - timedelta(days=10))
        record("TODAY")

        by_to = client.get(LIST_URL, {"date_to": (today - timedelta(days=5)).isoformat()}).json()
        by_from = client.get(LIST_URL, {"date_from": today.isoformat()}).json()
        both = client.get(
            LIST_URL,
            {"date_from": timezone.localtime(old.occurred_at).date().isoformat(), "date_to": today.isoformat()},
        ).json()

        assert [r["action"] for r in by_to["results"]] == ["OLD"]
        assert "OLD" not in [r["action"] for r in by_from["results"]]
        assert {"OLD", "TODAY"} <= {r["action"] for r in both["results"]}

    @pytest.mark.parametrize(
        "params",
        [
            {"date_from": "ayer"},
            {"date_to": "2026-13-45"},
            {"date_from": "2026-05-02", "date_to": "2026-05-01"},
            {"actor": "no-es-uuid"},
            {"manuscript": "123"},
            {"action": "login minuscula"},
            {"result": "OK"},
        ],
    )
    def test_malformed_filters_answer_400(self, client, params) -> None:
        response = client.get(LIST_URL, params)

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"


class TestListing:
    def test_newest_first_and_paginated(self, client) -> None:
        base = datetime(2026, 1, 1, tzinfo=dt_timezone.utc)
        for index in range(5):
            record(f"EVT_{index}", occurred_at=base + timedelta(hours=index))

        body = client.get(LIST_URL, {"page_size": 2, "action": "EVT_4"}).json()
        first = client.get(LIST_URL, {"page_size": 2}).json()

        assert body["count"] == 1
        assert first["results"][0]["action"] in {"AUDIT_QUERIED", "EVT_4"}
        assert len(first["results"]) == 2 and first["next"]

    def test_invalid_page_size_answers_400(self, client) -> None:
        assert client.get(LIST_URL, {"page_size": 101}).status_code == 400


class TestDetail:
    def test_detail_returns_the_event_by_its_public_id(self, client) -> None:
        entry = record(request_id="rid-77", details={"status": "ACTIVE"})

        body = client.get(f"{LIST_URL}{entry.event_id}/").json()

        assert body["id"] == str(entry.event_id)
        assert body["entry_hash"] == entry.entry_hash
        assert body["request_id"] == "rid-77"
        assert body["details"] == {"status": "ACTIVE"}

    def test_unknown_event_answers_404_and_is_not_audited(self, client) -> None:
        assert client.get(f"{LIST_URL}{uuid4()}/").status_code == 404
        assert queries() == []

    def test_detail_does_not_infer_write_permissions(self, client) -> None:
        entry = record("VERDICT_REGISTERED", "VERDICT", entity_id=uuid4())

        body = client.get(f"{LIST_URL}{entry.event_id}/").json()

        assert "can_authorize_correction" not in body
        assert not any(key.startswith("can_") for key in body)

    def test_the_integer_primary_key_is_not_exposed(self, client) -> None:
        entry = record()

        body = client.get(f"{LIST_URL}{entry.event_id}/").json()

        assert body["id"] != str(entry.pk)
        assert client.get(f"{LIST_URL}{entry.pk}/").status_code == 404


class TestAdminScope:
    def test_admin_still_cannot_reach_editorial_endpoints(self, client) -> None:
        manuscript = ManuscriptFactory()

        assert client.get(f"/api/manuscripts/{manuscript.pk}/").status_code in (403, 404)
        assert client.get("/api/editor/submissions/").status_code == 403
        assert client.get("/api/reviewer/assignments/").status_code == 403
