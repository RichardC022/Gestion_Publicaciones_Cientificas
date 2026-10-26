"""Tests for the logical withdrawal of a manuscript (TSK-37).

Covers the acceptance criteria:

1. The reason is mandatory in ``UNDER_REVIEW`` and ``ACCEPTED`` and
   optional in every other state.
2. Nothing is ever deleted: the manuscript, versions, rounds, history
   and audit stay, and ``status`` does not change.
3. The manuscript leaves the active listings at once, and a second
   withdrawal repeats neither events nor notices.

Plus HU-08: only the owner, the audit with actor, previous status and
reason, no operation can slip through after the withdrawal, and the two
extension signals (in-transaction and after-commit).
"""

from __future__ import annotations

import pytest
from django.db import connection

from apps.audit.models import AuditLog
from apps.audit.services import AuditService, AuditUnavailable
from apps.publications.models import (
    CorrectionRound,
    Manuscript,
    ManuscriptAuthor,
    ManuscriptVersion,
    StatusEvent,
)
from apps.publications.services.pdf import sha256_of_file
from apps.publications.services.withdraw import withdraw_manuscript
from apps.publications.signals import manuscript_withdrawing, manuscript_withdrawn
from tests.publications.test_draft_file import draft_url, pdf_file
from tests.publications.test_manuscript_api import (  # noqa: F401
    URL,
    actor,
    client_for,
    detail_url,
    error_code,
    owned_manuscript,
)
from tests.publications.test_new_version import (  # noqa: F401
    request_corrections,
    send,
    versions_url,
)
from tests.publications.test_submission import (  # noqa: F401
    media_root,
    owner,
    ready_draft,
    seeded_roles,
    submit,
    submit_url,
    version_dir_of,
)

pytestmark = pytest.mark.django_db

ALL_STATES = ["DRAFT", "SUBMITTED", "UNDER_REVIEW", "REQUIRES_CORRECTIONS", "ACCEPTED", "REJECTED"]
REASON_REQUIRED = ["UNDER_REVIEW", "ACCEPTED"]
REASON_OPTIONAL = ["DRAFT", "SUBMITTED", "REQUIRES_CORRECTIONS", "REJECTED"]


def withdraw_url(manuscript) -> str:
    return f"{detail_url(manuscript)}withdraw/"


@pytest.fixture
def withdraw(django_capture_on_commit_callbacks):
    """POST the withdrawal, running the after-commit callbacks."""

    def run(user, manuscript, body=None):
        with django_capture_on_commit_callbacks(execute=True):
            return client_for(user).post(
                withdraw_url(manuscript), {} if body is None else body, format="json"
            )

    return run


def counts(manuscript) -> dict:
    """Everything the withdrawal must leave exactly as it was."""
    return {
        "versions": ManuscriptVersion.objects.filter(manuscript=manuscript).count(),
        "rounds": CorrectionRound.objects.filter(manuscript=manuscript).count(),
        "authors": ManuscriptAuthor.objects.filter(manuscript=manuscript).count(),
        "exists": Manuscript.objects.filter(pk=manuscript.pk).exists(),
    }


class TestReason:
    @pytest.mark.parametrize("status", REASON_OPTIONAL)
    def test_the_reason_is_optional_in_the_other_states(self, owner, withdraw, status) -> None:
        manuscript = owned_manuscript(owner, status=status)

        response = withdraw(owner, manuscript)

        assert response.status_code == 200
        manuscript.refresh_from_db()
        assert manuscript.is_active is False and manuscript.withdrawal_reason is None

    @pytest.mark.parametrize("status", REASON_REQUIRED)
    @pytest.mark.parametrize("body", [{}, {"reason": ""}, {"reason": "   "}, {"reason": None}])
    def test_the_reason_is_mandatory_in_review_and_accepted(self, owner, withdraw, status, body) -> None:
        manuscript = owned_manuscript(owner, status=status)

        response = withdraw(owner, manuscript, body)

        assert response.status_code == 400 and error_code(response) == "VALIDATION_ERROR"
        assert "reason" in response.json()["error"]["details"]
        manuscript.refresh_from_db()
        assert manuscript.is_active is True and manuscript.withdrawn_at is None
        assert not StatusEvent.objects.filter(manuscript=manuscript).exists()
        assert not AuditLog.objects.filter(action="MANUSCRIPT_WITHDRAWN").exists()

    @pytest.mark.parametrize("status", REASON_REQUIRED)
    def test_a_reason_in_review_or_accepted_is_stored_trimmed(self, owner, withdraw, status) -> None:
        manuscript = owned_manuscript(owner, status=status)

        response = withdraw(owner, manuscript, {"reason": "  Retiro por decisión del equipo.  "})

        assert response.status_code == 200
        manuscript.refresh_from_db()
        assert manuscript.withdrawal_reason == "Retiro por decisión del equipo."
        assert response.json()["withdrawal_reason"] == "Retiro por decisión del equipo."

    def test_an_optional_reason_is_kept_when_given(self, owner, withdraw) -> None:
        manuscript = owned_manuscript(owner, status="REJECTED")

        withdraw(owner, manuscript, {"reason": "Archivo el rechazo."})

        manuscript.refresh_from_db()
        assert manuscript.withdrawal_reason == "Archivo el rechazo."

    def test_a_too_long_reason_answers_400(self, owner, withdraw) -> None:
        manuscript = owned_manuscript(owner)

        assert withdraw(owner, manuscript, {"reason": "x" * 2001}).status_code == 400
        manuscript.refresh_from_db()
        assert manuscript.is_active is True


class TestWithdrawal:
    @pytest.mark.parametrize("status", ALL_STATES)
    def test_it_marks_the_manuscript_and_keeps_its_status(self, owner, withdraw, status) -> None:
        manuscript = owned_manuscript(owner, status=status)
        before = manuscript.lock_version

        response = withdraw(owner, manuscript, {"reason": "Motivo de la baja."})

        assert response.status_code == 200
        manuscript.refresh_from_db()
        assert manuscript.is_active is False
        assert manuscript.withdrawn_at is not None and manuscript.withdrawn_by == owner
        assert manuscript.status == status
        assert manuscript.lock_version == before + 1 and response["ETag"] == f'"{before + 1}"'
        body = response.json()
        assert body["is_active"] is False and body["status"] == status and body["withdrawn_at"]

    def test_the_database_constraint_is_satisfied(self, owner, withdraw) -> None:
        manuscript = owned_manuscript(owner)

        withdraw(owner, manuscript)

        manuscript.refresh_from_db()
        assert (manuscript.is_active, manuscript.withdrawn_at is None) == (False, False)

    def test_nothing_is_deleted_from_a_manuscript_with_history(self, owner, submit, send, withdraw, media_root) -> None:
        manuscript = ready_draft(owner)
        assert submit(owner, manuscript).status_code == 201
        request_corrections(manuscript)
        assert send(owner, manuscript).status_code == 201
        before = counts(manuscript)
        rows = list(
            ManuscriptVersion.objects.filter(manuscript=manuscript).values(
                "version_number", "original_sha256", "sanitized_sha256", "metadata_sha256"
            )
        )
        files = {
            path: sha256_of_file(path)
            for number in (1, 2)
            for path in version_dir_of(media_root, manuscript, number).iterdir()
        }
        audit_before = AuditLog.objects.count()
        events_before = StatusEvent.objects.filter(manuscript=manuscript).count()

        response = withdraw(owner, manuscript)

        assert response.status_code == 200
        assert counts(manuscript) == before
        assert list(
            ManuscriptVersion.objects.filter(manuscript=manuscript).values(
                "version_number", "original_sha256", "sanitized_sha256", "metadata_sha256"
            )
        ) == rows
        assert {path: sha256_of_file(path) for path in files} == files
        assert AuditLog.objects.count() == audit_before + 1
        assert StatusEvent.objects.filter(manuscript=manuscript).count() == events_before + 1
        manuscript.refresh_from_db()
        assert (manuscript.current_version, manuscript.current_round) == (2, 1)

    def test_the_status_history_records_the_withdrawal(self, owner, withdraw) -> None:
        manuscript = owned_manuscript(owner, status="SUBMITTED")

        withdraw(owner, manuscript, {"reason": "Ya no deseo continuar."})

        event = StatusEvent.objects.get(manuscript=manuscript)
        assert (event.from_status, event.to_status) == ("SUBMITTED", "SUBMITTED")
        assert event.actor == owner and event.reason == "Ya no deseo continuar."
        assert event.metadata == {"withdrawn": True}

    def test_the_audit_records_actor_previous_status_and_reason(self, owner, withdraw) -> None:
        manuscript = owned_manuscript(owner, status="UNDER_REVIEW")

        withdraw(owner, manuscript, {"reason": "Retiro del manuscrito."})

        audit = AuditLog.objects.get(action="MANUSCRIPT_WITHDRAWN")
        assert audit.result == "SUCCESS" and audit.entity_id == manuscript.pk
        assert audit.actor_id == owner.pk and audit.actor_role == "AUTHOR" and audit.request_id
        assert audit.reason == "Retiro del manuscrito."
        assert audit.details == {"code": manuscript.code, "previous_status": "UNDER_REVIEW"}
        assert audit.occurred_at is not None

    def test_a_draft_with_an_attached_pdf_is_withdrawn_without_losing_the_file(self, owner, withdraw, media_root) -> None:
        manuscript = ready_draft(owner)
        stored = media_root / "private" / manuscript.draft_file_path

        assert withdraw(owner, manuscript).status_code == 200

        assert stored.is_file()
        assert Manuscript.objects.filter(pk=manuscript.pk).exists()


class TestVisibility:
    def test_it_leaves_the_active_listings_and_shows_in_the_archived_view(self, owner, withdraw) -> None:
        kept = owned_manuscript(owner)
        gone = owned_manuscript(owner)
        withdraw(owner, gone)
        client = client_for(owner)

        active = client.get(URL).json()["results"]
        archived = client.get(URL, {"archived": "true"}).json()["results"]

        assert [item["id"] for item in active] == [str(kept.pk)]
        assert [item["id"] for item in archived] == [str(gone.pk)]
        assert archived[0]["is_active"] is False and archived[0]["withdrawn_at"]

    def test_the_owner_can_still_read_the_archived_manuscript(self, owner, withdraw) -> None:
        manuscript = owned_manuscript(owner, status="ACCEPTED")
        withdraw(owner, manuscript, {"reason": "Retiro."})

        response = client_for(owner).get(detail_url(manuscript))

        assert response.status_code == 200
        assert response.json()["withdrawal_reason"] == "Retiro."
        assert response.json()["status"] == "ACCEPTED"

    def test_the_editor_loses_it_from_the_active_inbox_but_keeps_the_archive(self, owner, withdraw) -> None:
        manuscript = owned_manuscript(owner, status="SUBMITTED")
        editor = client_for(actor("EDITOR"))
        assert [i["id"] for i in editor.get(URL).json()["results"]] == [str(manuscript.pk)]

        withdraw(owner, manuscript)

        assert editor.get(URL).json()["results"] == []
        archived = editor.get(URL, {"archived": "true"}).json()["results"]
        assert [i["id"] for i in archived] == [str(manuscript.pk)]


class TestRepeatedWithdrawal:
    def test_a_second_withdrawal_answers_409_and_repeats_nothing(self, owner, withdraw) -> None:
        manuscript = owned_manuscript(owner, status="SUBMITTED")
        received = []

        def on_committed(sender, **kwargs):
            received.append(kwargs)

        manuscript_withdrawn.connect(on_committed, dispatch_uid="repeat")
        try:
            first = withdraw(owner, manuscript, {"reason": "Primera."})
            manuscript.refresh_from_db()
            stamp, version = manuscript.withdrawn_at, manuscript.lock_version
            second = withdraw(owner, manuscript, {"reason": "Segunda."})
        finally:
            manuscript_withdrawn.disconnect(dispatch_uid="repeat")

        assert first.status_code == 200
        assert second.status_code == 409 and error_code(second) == "STATE_CONFLICT"
        assert "ya se encuentra dado de baja" in second.json()["error"]["message"]
        manuscript.refresh_from_db()
        assert (manuscript.withdrawn_at, manuscript.lock_version) == (stamp, version)
        assert manuscript.withdrawal_reason == "Primera."
        assert StatusEvent.objects.filter(manuscript=manuscript).count() == 1
        assert AuditLog.objects.filter(action="MANUSCRIPT_WITHDRAWN").count() == 1
        assert len(received) == 1

    def test_the_repeated_request_answers_409_even_with_an_invalid_body(self, owner, withdraw) -> None:
        manuscript = owned_manuscript(owner)
        withdraw(owner, manuscript)

        assert withdraw(owner, manuscript, {"reason": "x" * 5000}).status_code == 409


class TestNothingSlipsThroughAfterWithdrawal:
    def test_edition_upload_submission_and_versions_are_all_blocked(self, owner, withdraw, send) -> None:
        manuscript = ready_draft(owner)
        withdraw(owner, manuscript)
        manuscript.refresh_from_db()
        client = client_for(owner)

        patched = client.patch(
            detail_url(manuscript), {"title": "X"}, format="json", HTTP_IF_MATCH=f'"{manuscript.lock_version}"'
        )
        uploaded = client.post(draft_url(manuscript), {"file": pdf_file()}, format="multipart")
        submitted = client.post(submit_url(manuscript), format="json")

        assert (patched.status_code, uploaded.status_code, submitted.status_code) == (409, 409, 409)
        assert not ManuscriptVersion.objects.filter(manuscript=manuscript).exists()

    def test_a_new_version_is_blocked_even_in_requires_corrections(self, owner, submit, send, withdraw) -> None:
        manuscript = ready_draft(owner)
        submit(owner, manuscript)
        request_corrections(manuscript)
        withdraw(owner, manuscript)

        response = send(owner, manuscript)

        assert response.status_code == 409
        assert ManuscriptVersion.objects.filter(manuscript=manuscript).count() == 1

    def test_the_withdrawal_of_a_submitted_manuscript_leaves_its_version_valid(self, owner, submit, withdraw) -> None:
        manuscript = ready_draft(owner)
        submit(owner, manuscript)

        withdraw(owner, manuscript)

        version = ManuscriptVersion.objects.get(manuscript=manuscript)
        assert version.version_number == 1 and version.original_sha256


class TestAccess:
    def test_anonymous_answers_401(self, owner) -> None:
        from rest_framework.test import APIClient

        manuscript = owned_manuscript(owner)

        assert APIClient().post(withdraw_url(manuscript), {}, format="json").status_code == 401

    @pytest.mark.parametrize("roles", [("EDITOR",), ("REVIEWER",), ("ADMIN",), ()])
    def test_roles_without_the_author_module_answer_403(self, owner, withdraw, roles) -> None:
        manuscript = owned_manuscript(owner)

        assert withdraw(actor(*roles), manuscript).status_code == 403
        manuscript.refresh_from_db()
        assert manuscript.is_active is True

    def test_someone_elses_manuscript_answers_404_without_revealing_it(self, owner, withdraw) -> None:
        manuscript = owned_manuscript(owner)

        response = withdraw(actor("AUTHOR"), manuscript)

        assert response.status_code == 404 and error_code(response) == "NOT_FOUND"
        manuscript.refresh_from_db()
        assert manuscript.is_active is True and manuscript.withdrawn_at is None

    def test_multirole_user_cannot_withdraw_a_manuscript_seen_as_editor(self, owner, withdraw) -> None:
        manuscript = owned_manuscript(owner, status="SUBMITTED")

        assert withdraw(actor("AUTHOR", "EDITOR"), manuscript).status_code == 404
        manuscript.refresh_from_db()
        assert manuscript.is_active is True

    def test_unknown_manuscript_answers_404(self, owner) -> None:
        response = client_for(owner).post(
            "/api/manuscripts/00000000-0000-0000-0000-000000000000/withdraw/", {}, format="json"
        )

        assert response.status_code == 404

    def test_get_is_not_allowed_and_there_is_still_no_delete(self, owner) -> None:
        manuscript = owned_manuscript(owner)

        assert client_for(owner).get(withdraw_url(manuscript)).status_code == 405
        assert client_for(owner).delete(detail_url(manuscript)).status_code == 405
        assert Manuscript.objects.filter(pk=manuscript.pk).exists()


class TestSignals:
    def test_the_in_transaction_signal_runs_before_the_commit_with_ids_only(self, owner, withdraw) -> None:
        manuscript = owned_manuscript(owner, status="UNDER_REVIEW")
        seen = []

        def on_withdrawing(sender, **kwargs):
            seen.append((connection.in_atomic_block, dict(kwargs)))

        manuscript_withdrawing.connect(on_withdrawing, dispatch_uid="pre")
        try:
            withdraw(owner, manuscript, {"reason": "Texto libre del autor."})
        finally:
            manuscript_withdrawing.disconnect(dispatch_uid="pre")

        [(in_transaction, kwargs)] = seen
        assert in_transaction is True
        assert kwargs["manuscript_id"] == manuscript.pk and kwargs["withdrawn_by_id"] == owner.pk
        assert kwargs["previous_status"] == "UNDER_REVIEW" and kwargs["withdrawn_at"]
        assert "Texto libre" not in str(kwargs)

    def test_a_failing_in_transaction_receiver_aborts_the_whole_withdrawal(self, owner, django_capture_on_commit_callbacks) -> None:
        manuscript = owned_manuscript(owner, status="UNDER_REVIEW")
        announced = []

        def failing(sender, **kwargs):
            raise RuntimeError("no se pudo revocar la asignación")

        def on_committed(sender, **kwargs):
            announced.append(kwargs)

        manuscript_withdrawing.connect(failing, dispatch_uid="failing")
        manuscript_withdrawn.connect(on_committed, dispatch_uid="aborted")
        try:
            with django_capture_on_commit_callbacks(execute=True):
                with pytest.raises(RuntimeError):
                    withdraw_manuscript(
                        manuscript_id=manuscript.pk, user=owner, reason="Motivo.", context={}
                    )
        finally:
            manuscript_withdrawing.disconnect(dispatch_uid="failing")
            manuscript_withdrawn.disconnect(dispatch_uid="aborted")

        manuscript.refresh_from_db()
        assert manuscript.is_active is True and manuscript.withdrawn_at is None
        assert not StatusEvent.objects.filter(manuscript=manuscript).exists()
        assert not AuditLog.objects.filter(action="MANUSCRIPT_WITHDRAWN").exists()
        assert announced == []

    def test_the_committed_signal_is_sent_once_after_the_commit_without_the_reason(
        self, owner, django_capture_on_commit_callbacks
    ) -> None:
        manuscript = owned_manuscript(owner, status="ACCEPTED")
        received = []

        def on_committed(sender, **kwargs):
            received.append(kwargs)

        manuscript_withdrawn.connect(on_committed, dispatch_uid="post")
        try:
            with django_capture_on_commit_callbacks(execute=False) as callbacks:
                response = client_for(owner).post(
                    withdraw_url(manuscript), {"reason": "Texto libre del autor."}, format="json"
                )
            assert response.status_code == 200
            assert len(callbacks) == 1 and received == []
            callbacks[0]()
        finally:
            manuscript_withdrawn.disconnect(dispatch_uid="post")

        [kwargs] = received
        assert kwargs["manuscript_id"] == manuscript.pk and kwargs["previous_status"] == "ACCEPTED"
        assert kwargs["withdrawn_by_id"] == owner.pk
        assert "reason" not in kwargs and "Texto libre" not in str(kwargs)

    def test_a_failing_committed_receiver_never_breaks_the_withdrawal(self, owner, withdraw) -> None:
        manuscript = owned_manuscript(owner)

        def broken(sender, **kwargs):
            raise RuntimeError("listener roto")

        manuscript_withdrawn.connect(broken, dispatch_uid="broken-post")
        try:
            response = withdraw(owner, manuscript)
        finally:
            manuscript_withdrawn.disconnect(dispatch_uid="broken-post")

        assert response.status_code == 200
        manuscript.refresh_from_db()
        assert manuscript.is_active is False


class TestAuditUnavailable:
    def test_audit_failure_reverts_the_withdrawal_and_answers_503(self, owner, withdraw, monkeypatch) -> None:
        manuscript = owned_manuscript(owner, status="SUBMITTED")
        received = []

        def on_committed(sender, **kwargs):
            received.append(kwargs)

        def fail(**kwargs):
            raise AuditUnavailable("sin auditoría")

        manuscript_withdrawn.connect(on_committed, dispatch_uid="audit-fail-withdraw")
        monkeypatch.setattr(AuditService, "record", staticmethod(fail))
        try:
            response = withdraw(owner, manuscript)
        finally:
            manuscript_withdrawn.disconnect(dispatch_uid="audit-fail-withdraw")

        assert response.status_code == 503 and error_code(response) == "AUDIT_UNAVAILABLE"
        manuscript.refresh_from_db()
        assert manuscript.is_active is True and manuscript.withdrawn_at is None
        assert manuscript.lock_version == 0
        assert not StatusEvent.objects.filter(manuscript=manuscript).exists()
        assert received == []
