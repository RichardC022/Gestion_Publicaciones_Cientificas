"""Tests for the administrative authorization of a verdict correction (TSK-77).

Acceptance criteria: the administrator never modifies the original verdict
nor reaches manuscripts, evaluations or PDFs; an outdated verdict, one with
a later version or one with an active authorization answers ``409``; and
``can_authorize_correction`` is true only for the latest verdict without a
later version, without exposing authors or comments.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIClient

from apps.audit.models import AuditLog
from apps.audit.services import AuditService, AuditUnavailable
from apps.notifications.models import Notification
from apps.publications.models import Manuscript, Verdict, VerdictCorrection
from apps.publications.services.verdicts import register_verdict
from tests.factories import ManuscriptVersionFactory
from tests.parallel import api_task, run_parallel, statuses
from tests.publications.test_lifecycle import assert_audit_chain_intact
from tests.publications.test_manuscript_api import actor, client_for, error_code
from tests.publications.test_verdicts import reviewed

pytestmark = pytest.mark.django_db

REASON = "El veredicto se registró sobre la evaluación equivocada."
JUSTIFICATION = "JUSTIFICACION_INTERNA_DEL_EDITOR"


@pytest.fixture(autouse=True)
def seeded_roles(db) -> None:
    call_command("seed_roles", verbosity=0)


@pytest.fixture(autouse=True)
def media_root(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    return tmp_path


@pytest.fixture
def editor():
    return actor("EDITOR")


@pytest.fixture
def admin():
    return actor("ADMIN")


@pytest.fixture
def decided(editor, django_capture_on_commit_callbacks):
    """A manuscript rejected by the editor: its verdict is the latest and the only one."""
    owner = actor("AUTHOR", first_name="Marcela", last_name="Quizhpe Ordóñez")
    manuscript = reviewed(editor, owner=owner)
    with django_capture_on_commit_callbacks(execute=True):
        result = register_verdict(
            manuscript_id=manuscript.pk, editor=editor, decision="REJECTED",
            justification=JUSTIFICATION, context={},
        )
    return result.verdict


def url(verdict) -> str:
    return f"/api/admin/verdicts/{verdict.pk}/authorize-correction/"


def authorize(user, verdict, *, key="clave-1", reason=REASON, **extra):
    headers = {} if key is None else {"HTTP_IDEMPOTENCY_KEY": key}
    return client_for(user).post(url(verdict), {"reason": reason}, format="json", **headers, **extra)


class TestAccess:
    def test_anonymous_gets_401(self, decided) -> None:
        response = APIClient().post(url(decided), {"reason": REASON}, format="json")

        assert response.status_code == 401

    @pytest.mark.parametrize("role", ["AUTHOR", "REVIEWER", "EDITOR"])
    def test_other_roles_get_403(self, decided, role) -> None:
        assert authorize(actor(role), decided).status_code == 403
        assert not VerdictCorrection.objects.exists()

    def test_a_revoked_admin_role_blocks_the_request(self, decided, admin) -> None:
        admin.role_assignments.update(is_active=False, revoked_at=timezone.now())

        assert authorize(admin, decided).status_code == 403

    def test_admin_gets_201(self, decided, admin) -> None:
        response = authorize(admin, decided)

        assert response.status_code == 201
        correction = VerdictCorrection.objects.get()
        assert correction.original_verdict_id == decided.pk
        assert correction.authorized_by_id == admin.pk
        assert correction.is_active and correction.consumed_at is None
        assert correction.reason == REASON

    def test_unknown_verdict_answers_404(self, admin) -> None:
        response = client_for(admin).post(
            "/api/admin/verdicts/5d0f4d0e-0000-4000-8000-000000000000/authorize-correction/",
            {"reason": REASON}, format="json", HTTP_IDEMPOTENCY_KEY="k",
        )

        assert response.status_code == 404


class TestBody:
    def test_idempotency_key_is_mandatory(self, decided, admin) -> None:
        response = authorize(admin, decided, key=None)

        assert response.status_code == 400
        assert not VerdictCorrection.objects.exists()

    @pytest.mark.parametrize("reason", [None, "", "   ", "corto", "x" * 9, "x" * 1001])
    def test_reason_must_have_10_to_1000_characters(self, decided, admin, reason) -> None:
        body = {} if reason is None else {"reason": reason}
        response = client_for(admin).post(url(decided), body, format="json", HTTP_IDEMPOTENCY_KEY="k")

        assert response.status_code == 400
        assert "reason" in response.json()["error"]["details"]
        assert not VerdictCorrection.objects.exists()

    @pytest.mark.parametrize("reason", ["x" * 10, "x" * 1000])
    def test_the_limits_are_accepted(self, decided, admin, reason) -> None:
        assert authorize(admin, decided, reason=reason).status_code == 201

    def test_reason_is_trimmed(self, decided, admin) -> None:
        authorize(admin, decided, reason=f"   {REASON}   ")

        assert VerdictCorrection.objects.get().reason == REASON


class TestResponse:
    def test_only_minimal_data_comes_back(self, decided, admin) -> None:
        response = authorize(admin, decided)
        body = response.json()

        assert set(body) == {
            "id", "verdict_id", "manuscript_code", "decision", "decided_at",
            "reason", "authorized_at", "is_active",
        }
        assert body["manuscript_code"] == decided.manuscript.code
        assert body["decision"] == "REJECTED" and body["is_active"] is True
        text = response.content.decode()
        for forbidden in ("Marcela", "Quizhpe", JUSTIFICATION, "comments_for_author", "pdf"):
            assert forbidden not in text

    def test_admin_still_cannot_reach_the_manuscript(self, decided, admin) -> None:
        authorize(admin, decided)
        client = client_for(admin)

        assert client.get(f"/api/manuscripts/{decided.manuscript_id}/").status_code in (403, 404)
        assert client.get(f"/api/editor/manuscripts/{decided.manuscript_id}/evaluations/").status_code == 403


class TestOriginalIsUntouched:
    def test_verdict_manuscript_and_catalog_do_not_change(self, decided, admin) -> None:
        manuscript = Manuscript.objects.get(pk=decided.manuscript_id)
        before = (
            list(Verdict.objects.values_list("pk", "decision", "justification", "observations", "previous_verdict_id")),
            manuscript.status, manuscript.lock_version, manuscript.current_version,
            manuscript.current_round, manuscript.updated_at,
        )

        authorize(admin, decided)

        manuscript.refresh_from_db()
        after = (
            list(Verdict.objects.values_list("pk", "decision", "justification", "observations", "previous_verdict_id")),
            manuscript.status, manuscript.lock_version, manuscript.current_version,
            manuscript.current_round, manuscript.updated_at,
        )
        assert after == before
        assert Verdict.objects.count() == 1


class TestEligibility:
    def test_outdated_verdict_answers_409(self, decided, admin) -> None:
        Verdict.objects.create(
            manuscript=decided.manuscript, version=decided.version, evaluation=decided.evaluation,
            editor=decided.editor, decision="ACCEPTED", previous_verdict=decided,
        )

        response = authorize(admin, decided)

        assert response.status_code == 409
        assert error_code(response) == "CORRECTION_NOT_AUTHORIZED"
        assert not VerdictCorrection.objects.exists()

    def test_a_later_version_answers_409(self, decided, admin) -> None:
        ManuscriptVersionFactory(
            manuscript=decided.manuscript, version_number=decided.version.version_number + 1,
            round_number=1, submitted_by=decided.manuscript.created_by,
        )

        response = authorize(admin, decided)

        assert response.status_code == 409 and error_code(response) == "CORRECTION_NOT_AUTHORIZED"
        assert not VerdictCorrection.objects.exists()

    def test_an_active_authorization_answers_409(self, decided, admin) -> None:
        assert authorize(admin, decided, key="a").status_code == 201

        again = authorize(admin, decided, key="b", reason="Otro motivo igualmente válido.")

        assert again.status_code == 409 and error_code(again) == "CORRECTION_NOT_AUTHORIZED"
        assert VerdictCorrection.objects.count() == 1

    def test_a_withdrawn_manuscript_answers_409(self, decided, admin) -> None:
        Manuscript.objects.filter(pk=decided.manuscript_id).update(
            is_active=False, withdrawn_at=timezone.now()
        )

        assert authorize(admin, decided).status_code == 409

    def test_a_consumed_authorization_leaves_the_original_outdated(self, decided, admin) -> None:
        correction = VerdictCorrection.objects.create(
            manuscript=decided.manuscript, original_verdict=decided, authorized_by=admin, reason=REASON,
        )
        newer = Verdict.objects.create(
            manuscript=decided.manuscript, version=decided.version, evaluation=decided.evaluation,
            editor=decided.editor, decision="ACCEPTED", previous_verdict=decided,
        )
        VerdictCorrection.objects.filter(pk=correction.pk).update(
            is_active=False, consumed_at=timezone.now(), consumed_by_verdict=newer
        )

        assert authorize(admin, decided).status_code == 409
        assert authorize(admin, newer).status_code == 201


class TestIdempotency:
    def test_same_key_replays_the_answer_and_creates_one(self, decided, admin) -> None:
        first = authorize(admin, decided, key="repite")
        second = authorize(admin, decided, key="repite")

        assert first.status_code == 201 and second.status_code == 201
        assert second["Idempotent-Replayed"] == "true"
        assert second.json() == first.json()
        assert VerdictCorrection.objects.count() == 1
        assert AuditLog.objects.filter(action="VERDICT_CORRECTION_AUTHORIZED").count() == 1

    def test_same_key_with_another_reason_is_a_conflict(self, decided, admin) -> None:
        authorize(admin, decided, key="repite")

        response = authorize(admin, decided, key="repite", reason="Un motivo distinto del primero.")

        assert response.status_code == 409
        assert VerdictCorrection.objects.count() == 1

    def test_a_refused_attempt_does_not_consume_its_key(self, decided, admin) -> None:
        ManuscriptVersionFactory(
            manuscript=decided.manuscript, version_number=decided.version.version_number + 1,
            round_number=1, submitted_by=decided.manuscript.created_by,
        )

        assert authorize(admin, decided, key="k").status_code == 409
        assert authorize(admin, decided, key="k").status_code == 409  # no replay de un error


class TestAudit:
    def test_the_authorization_is_audited(self, decided, admin) -> None:
        authorize(admin, decided)

        event = AuditLog.objects.get(action="VERDICT_CORRECTION_AUTHORIZED")
        correction = VerdictCorrection.objects.get()
        assert event.actor_id == admin.pk and event.actor_role == "ADMIN"
        assert event.entity_type == "VERDICT_CORRECTION" and event.entity_id == correction.pk
        assert event.reason == REASON and event.result == "SUCCESS"
        assert event.details["verdict_id"] == str(decided.pk)
        assert event.details["code"] == decided.manuscript.code
        assert_audit_chain_intact()

    def test_without_audit_nothing_is_created(self, decided, admin, monkeypatch) -> None:
        def broken(**kwargs):
            raise AuditUnavailable("sin auditoría")

        monkeypatch.setattr(AuditService, "record", staticmethod(broken))
        response = authorize(admin, decided, key="sin-auditoria")
        monkeypatch.undo()

        assert response.status_code == 503 and error_code(response) == "AUDIT_UNAVAILABLE"
        assert not VerdictCorrection.objects.exists()
        # La clave no se consumió: el reintento con la auditoría restablecida funciona.
        assert authorize(admin, decided, key="sin-auditoria").status_code == 201


class TestNotification:
    def test_the_issuing_editor_is_told_without_the_reason(
        self, decided, admin, editor, django_capture_on_commit_callbacks
    ) -> None:
        with django_capture_on_commit_callbacks(execute=True):
            authorize(admin, decided)

        notice = Notification.objects.get(recipient=editor, event_type="VERDICT_CORRECTION_AUTHORIZED", channel="PANEL")
        assert notice.payload["action"] == "Registre la nueva decisión."
        assert REASON not in str(notice.payload)
        assert "Marcela" not in str(notice.payload)


class TestAuditDetailFlag:
    def event(self, decided):
        return AuditLog.objects.get(action="VERDICT_REGISTERED", entity_id=decided.manuscript_id)

    def detail(self, admin, decided) -> dict:
        response = client_for(admin).get(f"/api/admin/audit/{self.event(decided).event_id}/")
        assert response.status_code == 200
        return response.json()

    def test_true_for_the_latest_verdict_without_a_later_version(self, decided, admin) -> None:
        body = self.detail(admin, decided)

        assert body["can_authorize_correction"] is True
        assert body["verdict"] == {
            "id": str(decided.pk),
            "manuscript_code": decided.manuscript.code,
            "decision": "REJECTED",
            "decided_at": body["verdict"]["decided_at"],
        }

    def test_false_after_the_authorization(self, decided, admin) -> None:
        authorize(admin, decided)

        assert self.detail(admin, decided)["can_authorize_correction"] is False

    def test_false_with_a_later_version(self, decided, admin) -> None:
        ManuscriptVersionFactory(
            manuscript=decided.manuscript, version_number=decided.version.version_number + 1,
            round_number=1, submitted_by=decided.manuscript.created_by,
        )

        assert self.detail(admin, decided)["can_authorize_correction"] is False

    def test_false_for_an_outdated_verdict(self, decided, admin) -> None:
        Verdict.objects.create(
            manuscript=decided.manuscript, version=decided.version, evaluation=decided.evaluation,
            editor=decided.editor, decision="ACCEPTED", previous_verdict=decided,
        )

        assert self.detail(admin, decided)["can_authorize_correction"] is False

    def test_non_verdict_events_carry_no_flag(self, decided, admin) -> None:
        other = AuditService.record(action="LOGIN", entity_type="SESSION")

        body = client_for(admin).get(f"/api/admin/audit/{other.event_id}/").json()

        assert "can_authorize_correction" not in body and "verdict" not in body

    def test_the_list_never_carries_the_flag(self, decided, admin) -> None:
        rows = client_for(admin).get("/api/admin/audit/").json()["results"]

        assert not any("can_authorize_correction" in row for row in rows)

    def test_the_detail_exposes_no_authors_or_comments(self, decided, admin) -> None:
        text = client_for(admin).get(f"/api/admin/audit/{self.event(decided).event_id}/").content.decode()

        for forbidden in ("Marcela", "Quizhpe", JUSTIFICATION, "comments_for_author", "email"):
            assert forbidden not in text


@pytest.mark.django_db(transaction=True)
class TestSimultaneous:
    def test_two_simultaneous_authorizations_leave_one(self) -> None:
        editor, admin = actor("EDITOR"), actor("ADMIN")
        manuscript = reviewed(editor)
        verdict = register_verdict(
            manuscript_id=manuscript.pk, editor=editor, decision="REJECTED",
            justification=JUSTIFICATION, context={},
        ).verdict

        def task(key):
            return api_task(
                admin,
                lambda client: client.post(
                    url(verdict), {"reason": REASON}, format="json", HTTP_IDEMPOTENCY_KEY=key
                ),
            )

        responses = run_parallel([task("carrera-1"), task("carrera-2")])

        assert statuses(responses) == [201, 409]
        assert VerdictCorrection.objects.filter(original_verdict=verdict, is_active=True).count() == 1
        assert AuditLog.objects.filter(action="VERDICT_CORRECTION_AUTHORIZED").count() == 1
        assert_audit_chain_intact()
