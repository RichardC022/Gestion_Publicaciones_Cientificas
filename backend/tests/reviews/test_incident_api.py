"""Tests for the confidential identity-leak report and its resolution (TSK-64).

Covers the acceptance criteria: only the owner of an ``ACTIVE`` assignment
reports, privately, without changing the evaluation; ``REQUEST_ANONYMIZED_VERSION``
leaves the manuscript in ``REQUIRES_CORRECTIONS``, opens the round and stores
``correction_round_id``, ``REASSIGN`` revokes and keeps ``UNDER_REVIEW`` and
``DISMISS`` changes no state; and the resolution is recorded once (``409``
when repeated) and never exposes the reviewer to the author.

The author-side checks read the real author endpoints and look at the
serialized text, so a value under any key would fail too.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.audit.models import AuditLog
from apps.audit.services import AuditService, AuditUnavailable
from apps.publications.models import CorrectionRound, Manuscript, StatusEvent, Verdict
from apps.reviews.models import Assignment, Evaluation, IncidentReport
from apps.reviews.signals import (
    assignment_revoked,
    incident_reported,
    incident_resolved,
)
from tests.factories import EvaluationFactory, ManuscriptAuthorFactory
from tests.publications.test_manuscript_api import (  # noqa: F401
    actor,
    client_for,
    detail_url as manuscript_url,
    error_code,
)
from tests.publications.test_new_version import send  # noqa: F401
from tests.publications.test_submission import (  # noqa: F401
    media_root,
    owner,
    ready_draft,
    seeded_roles,
    submit,
)
from tests.reviews.test_editor_api import make_assignment, make_reviewer, submitted

pytestmark = pytest.mark.django_db

DESCRIPTION = "El PDF menciona la afiliación del grupo de investigación en la página 3."
REVIEWER_BASE = "/api/reviewer/assignments/"
EDITOR_BASE = "/api/editor/incidents/"


@pytest.fixture
def editor():
    return actor("EDITOR")


@pytest.fixture
def reviewer():
    return make_reviewer()


@pytest.fixture
def assignment(owner, reviewer, editor) -> Assignment:
    """An ``ACTIVE`` assignment over a manuscript ``UNDER_REVIEW``."""
    manuscript = submitted(owner, status="UNDER_REVIEW")
    return make_assignment(manuscript, reviewer, editor)


def leak_url(assignment) -> str:
    return f"{REVIEWER_BASE}{assignment.pk}/identity-leak/"


def report(user, assignment, body: dict | None = None):
    payload = {"report_type": "IDENTITY_LEAK", "description": DESCRIPTION}
    payload.update(body or {})
    return client_for(user).post(leak_url(assignment), payload, format="json")


def resolve_url(incident_id) -> str:
    return f"{EDITOR_BASE}{incident_id}/resolve/"


def resolve(user, incident_id, resolution: str | None):
    body = {} if resolution is None else {"resolution": resolution}
    return client_for(user).post(resolve_url(incident_id), body, format="json")


def open_incident(reviewer, assignment) -> IncidentReport:
    assert report(reviewer, assignment).status_code == 201
    return IncidentReport.objects.get(assignment=assignment)


@contextmanager
def listening(signal):
    received: list[dict] = []

    def listener(sender, **kwargs) -> None:
        kwargs.pop("signal", None)
        received.append(kwargs)

    signal.connect(listener, weak=False)
    try:
        yield received
    finally:
        signal.disconnect(listener)


def failing_audit(monkeypatch) -> None:
    def fail(**kwargs):
        raise AuditUnavailable("sin auditoría")

    monkeypatch.setattr(AuditService, "record", staticmethod(fail))


def set_status(assignment, status: str) -> None:
    Assignment.objects.filter(pk=assignment.pk).update(status=status)


class TestReportAccess:
    def test_anonymous_requests_answer_401(self, assignment) -> None:
        assert APIClient().post(leak_url(assignment), {}, format="json").status_code == 401

    @pytest.mark.parametrize("role", ["AUTHOR", "EDITOR", "ADMIN"])
    def test_other_roles_answer_403(self, assignment, role) -> None:
        assert report(actor(role), assignment).status_code == 403

    def test_a_foreign_assignment_answers_404(self, assignment) -> None:
        response = report(make_reviewer(), assignment)

        assert response.status_code == 404 and error_code(response) == "NOT_FOUND"
        assert not IncidentReport.objects.exists()

    def test_a_coauthor_reviewer_gets_404(self, reviewer, assignment) -> None:
        ManuscriptAuthorFactory(manuscript=assignment.manuscript, user=reviewer, author_order=9)

        assert report(reviewer, assignment).status_code == 404

    def test_only_post_is_allowed(self, reviewer, assignment) -> None:
        client = client_for(reviewer)

        assert client.get(leak_url(assignment)).status_code == 405
        assert client.put(leak_url(assignment), {}, format="json").status_code == 405
        assert client.delete(leak_url(assignment)).status_code == 405


class TestReport:
    def test_creates_an_open_report_and_returns_only_the_receipt(self, reviewer, assignment) -> None:
        response = report(reviewer, assignment, {"description": f"  {DESCRIPTION}  "})

        assert response.status_code == 201
        body = response.json()
        assert set(body) == {"id", "assignment", "report_type", "status", "created_at"}
        assert body["status"] == "OPEN" and body["report_type"] == "IDENTITY_LEAK"
        incident = IncidentReport.objects.get()
        assert str(incident.pk) == body["id"] and incident.description == DESCRIPTION
        assert incident.reporter_id == reviewer.pk
        assert incident.manuscript_id == assignment.manuscript_id
        assert incident.resolution is None and incident.correction_round_id is None
        assert DESCRIPTION not in response.content.decode()

    def test_other_is_a_valid_type(self, reviewer, assignment) -> None:
        assert report(reviewer, assignment, {"report_type": "OTHER"}).status_code == 201

    @pytest.mark.parametrize(
        "body",
        [
            {"report_type": "SPAM"},
            {"report_type": None},
            {"description": ""},
            {"description": "    "},
            {"description": "x" * 5001},
        ],
    )
    def test_an_invalid_body_answers_400(self, reviewer, assignment, body) -> None:
        response = report(reviewer, assignment, body)

        assert response.status_code == 400 and error_code(response) == "VALIDATION_ERROR"
        assert not IncidentReport.objects.exists()

    def test_missing_fields_answer_400(self, reviewer, assignment) -> None:
        response = client_for(reviewer).post(leak_url(assignment), {}, format="json")

        assert response.status_code == 400
        assert set(response.json()["error"]["details"]) == {"report_type", "description"}

    def test_a_second_open_report_answers_409(self, reviewer, assignment) -> None:
        open_incident(reviewer, assignment)

        response = report(reviewer, assignment)

        assert response.status_code == 409 and error_code(response) == "STATE_CONFLICT"
        assert IncidentReport.objects.count() == 1

    def test_a_new_report_is_allowed_once_the_previous_one_was_resolved(
        self, reviewer, assignment, editor
    ) -> None:
        incident = open_incident(reviewer, assignment)
        assert resolve(editor, incident.pk, "DISMISS").status_code == 200

        assert report(reviewer, assignment).status_code == 201
        assert IncidentReport.objects.count() == 2

    @pytest.mark.parametrize("status", ["COMPLETED", "REVOKED", "EXPIRED"])
    def test_a_non_active_assignment_answers_409(self, reviewer, assignment, status) -> None:
        set_status(assignment, status)

        response = report(reviewer, assignment)

        assert response.status_code == 409 and error_code(response) == "STATE_CONFLICT"
        assert not IncidentReport.objects.exists()

    def test_an_active_assignment_past_its_deadline_can_still_report(
        self, reviewer, assignment
    ) -> None:
        due_at = timezone.now() - timedelta(days=1)
        Assignment.objects.filter(pk=assignment.pk).update(
            due_at=due_at, assigned_at=due_at - timedelta(days=20)
        )

        assert report(reviewer, assignment).status_code == 201

    def test_it_changes_neither_the_evaluation_nor_the_manuscript_nor_the_assignment(
        self, reviewer, assignment
    ) -> None:
        draft = EvaluationFactory(assignment=assignment, lock_version=1, clarity_score=3)
        manuscript_before = Manuscript.objects.get(pk=assignment.manuscript_id)
        assignment_before = Assignment.objects.get(pk=assignment.pk)
        events_before = StatusEvent.objects.count()

        report(reviewer, assignment)

        draft.refresh_from_db()
        assert (draft.status, draft.lock_version, draft.clarity_score, draft.conflict_declared) == (
            "DRAFT", 1, 3, False,
        )
        manuscript_after = Manuscript.objects.get(pk=assignment.manuscript_id)
        assert (manuscript_after.status, manuscript_after.lock_version) == (
            manuscript_before.status, manuscript_before.lock_version,
        )
        assignment_after = Assignment.objects.get(pk=assignment.pk)
        assert (assignment_after.status, assignment_after.lock_version) == (
            assignment_before.status, assignment_before.lock_version,
        )
        assert StatusEvent.objects.count() == events_before

    def test_the_reviewer_keeps_evaluating_after_reporting(self, reviewer, assignment) -> None:
        open_incident(reviewer, assignment)

        response = client_for(reviewer).put(
            f"{REVIEWER_BASE}{assignment.pk}/evaluation/",
            {"clarity_score": 4},
            format="json",
            HTTP_IF_MATCH='"0"',
        )

        assert response.status_code == 200
        assert Evaluation.objects.get(assignment=assignment).clarity_score == 4

    def test_the_report_is_audited_without_the_description(self, reviewer, assignment) -> None:
        incident = open_incident(reviewer, assignment)

        row = AuditLog.objects.get(action="IDENTITY_LEAK_REPORTED")
        assert row.actor_id == reviewer.pk and row.actor_role == "REVIEWER"
        assert row.entity_type == "INCIDENT_REPORT" and row.entity_id == incident.pk
        assert row.request_id
        assert row.details == {
            "manuscript_id": str(assignment.manuscript_id),
            "assignment_id": str(assignment.pk),
            "report_type": "IDENTITY_LEAK",
        }
        assert DESCRIPTION not in str(row.details) + str(row.reason)

    def test_an_unavailable_audit_answers_503_and_keeps_nothing(
        self, reviewer, assignment, monkeypatch
    ) -> None:
        failing_audit(monkeypatch)

        response = report(reviewer, assignment)

        assert response.status_code == 503 and error_code(response) == "AUDIT_UNAVAILABLE"
        assert not IncidentReport.objects.exists()

    def test_the_editor_event_is_sent_after_the_commit_with_identifiers_only(
        self, reviewer, assignment, django_capture_on_commit_callbacks
    ) -> None:
        with listening(incident_reported) as received:
            with django_capture_on_commit_callbacks(execute=True):
                assert report(reviewer, assignment).status_code == 201

        incident = IncidentReport.objects.get()
        assert received == [
            {
                "incident_id": incident.pk,
                "assignment_id": assignment.pk,
                "manuscript_id": assignment.manuscript_id,
                "report_type": "IDENTITY_LEAK",
            }
        ]

    def test_no_event_is_sent_when_the_report_fails(
        self, reviewer, assignment, django_capture_on_commit_callbacks
    ) -> None:
        set_status(assignment, "REVOKED")

        with listening(incident_reported) as received:
            with django_capture_on_commit_callbacks(execute=True):
                report(reviewer, assignment)

        assert received == []


class TestEditorList:
    @pytest.mark.parametrize("role", ["AUTHOR", "REVIEWER", "ADMIN"])
    def test_other_roles_answer_403(self, role) -> None:
        user = make_reviewer() if role == "REVIEWER" else actor(role)

        assert client_for(user).get(EDITOR_BASE).status_code == 403

    def test_anonymous_requests_answer_401(self) -> None:
        assert APIClient().get(EDITOR_BASE).status_code == 401

    def test_the_editor_reads_the_report_with_the_reviewer_identity(
        self, reviewer, assignment, editor
    ) -> None:
        incident = open_incident(reviewer, assignment)

        body = client_for(editor).get(EDITOR_BASE).json()

        assert body["count"] == 1
        row = body["results"][0]
        assert set(row) == {
            "id", "status", "report_type", "description", "manuscript", "manuscript_code",
            "manuscript_title", "assignment", "reporter", "created_at", "resolution",
            "resolved_by", "resolved_at", "correction_round_number",
        }
        assert row["id"] == str(incident.pk) and row["description"] == DESCRIPTION
        assert row["reporter"]["email"] == reviewer.email
        assert row["manuscript_code"] == assignment.manuscript.code
        assert row["resolution"] is None and row["resolved_by"] is None
        assert row["correction_round_number"] is None

    def test_open_reports_come_first_and_the_status_filter_narrows_the_list(
        self, owner, reviewer, editor
    ) -> None:
        resolved_assignment = make_assignment(
            submitted(owner, status="UNDER_REVIEW"), reviewer, editor
        )
        resolved = open_incident(reviewer, resolved_assignment)
        resolve(editor, resolved.pk, "DISMISS")
        open_assignment = make_assignment(
            submitted(owner, status="UNDER_REVIEW"), reviewer, editor
        )
        opened = open_incident(reviewer, open_assignment)
        client = client_for(editor)

        ids = [row["id"] for row in client.get(EDITOR_BASE).json()["results"]]
        only_open = client.get(EDITOR_BASE, {"status": "OPEN"}).json()
        only_resolved = client.get(EDITOR_BASE, {"status": "RESOLVED"}).json()

        assert ids == [str(opened.pk), str(resolved.pk)]
        assert [row["id"] for row in only_open["results"]] == [str(opened.pk)]
        assert [row["id"] for row in only_resolved["results"]] == [str(resolved.pk)]

    def test_an_unknown_status_filter_answers_400(self, editor) -> None:
        response = client_for(editor).get(EDITOR_BASE, {"status": "CLOSED"})

        assert response.status_code == 400 and error_code(response) == "VALIDATION_ERROR"

    def test_the_list_is_paginated(self, owner, reviewer, editor) -> None:
        for _ in range(3):
            assignment = make_assignment(
                submitted(owner, status="UNDER_REVIEW"), reviewer, editor
            )
            report(reviewer, assignment)

        body = client_for(editor).get(EDITOR_BASE, {"page_size": 2}).json()

        assert body["count"] == 3 and len(body["results"]) == 2 and body["next"]

    def test_the_list_does_not_query_per_row(
        self, owner, reviewer, editor, django_assert_max_num_queries
    ) -> None:
        for _ in range(4):
            report(reviewer, make_assignment(submitted(owner, status="UNDER_REVIEW"), reviewer, editor))

        with django_assert_max_num_queries(6):
            assert client_for(editor).get(EDITOR_BASE).status_code == 200

    def test_an_editor_with_a_conflict_of_interest_does_not_see_the_report(
        self, reviewer, assignment
    ) -> None:
        conflicted = actor("EDITOR")
        ManuscriptAuthorFactory(manuscript=assignment.manuscript, user=conflicted, author_order=9)
        open_incident(reviewer, assignment)

        assert client_for(conflicted).get(EDITOR_BASE).json()["count"] == 0

    def test_the_list_is_read_only(self, editor) -> None:
        client = client_for(editor)

        assert client.post(EDITOR_BASE, {}, format="json").status_code == 405
        assert client.delete(EDITOR_BASE).status_code == 405


class TestResolveAccess:
    @pytest.mark.parametrize("role", ["AUTHOR", "REVIEWER", "ADMIN"])
    def test_other_roles_answer_403(self, reviewer, assignment, role) -> None:
        incident = open_incident(reviewer, assignment)
        user = make_reviewer() if role == "REVIEWER" else actor(role)

        assert resolve(user, incident.pk, "DISMISS").status_code == 403
        incident.refresh_from_db()
        assert incident.status == "OPEN"

    def test_the_reporter_cannot_resolve_their_own_report(self, reviewer, assignment) -> None:
        incident = open_incident(reviewer, assignment)

        assert resolve(reviewer, incident.pk, "DISMISS").status_code == 403

    def test_an_editor_with_a_conflict_of_interest_answers_404(
        self, reviewer, assignment
    ) -> None:
        incident = open_incident(reviewer, assignment)
        conflicted = actor("EDITOR")
        ManuscriptAuthorFactory(manuscript=assignment.manuscript, user=conflicted, author_order=9)

        response = resolve(conflicted, incident.pk, "DISMISS")

        assert response.status_code == 404 and error_code(response) == "NOT_FOUND"
        incident.refresh_from_db()
        assert incident.status == "OPEN"

    def test_an_unknown_incident_answers_404(self, editor) -> None:
        assert resolve(editor, "7f1c2d3e-0000-4000-8000-000000000000", "DISMISS").status_code == 404

    @pytest.mark.parametrize("resolution", [None, "", "IGNORE", "dismiss"])
    def test_a_missing_or_unknown_resolution_answers_400(
        self, reviewer, assignment, editor, resolution
    ) -> None:
        incident = open_incident(reviewer, assignment)

        response = resolve(editor, incident.pk, resolution)

        assert response.status_code == 400 and error_code(response) == "VALIDATION_ERROR"
        incident.refresh_from_db()
        assert incident.status == "OPEN"

    def test_only_post_is_allowed(self, reviewer, assignment, editor) -> None:
        incident = open_incident(reviewer, assignment)

        assert client_for(editor).get(resolve_url(incident.pk)).status_code == 405


class TestDismiss:
    def test_closes_the_report_without_touching_state_or_assignment(
        self, reviewer, assignment, editor
    ) -> None:
        incident = open_incident(reviewer, assignment)
        manuscript_before = Manuscript.objects.get(pk=assignment.manuscript_id)

        response = resolve(editor, incident.pk, "DISMISS")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "RESOLVED" and body["resolution"] == "DISMISS"
        assert body["resolved_by"]["id"] == str(editor.pk) and body["resolved_at"]
        assert body["correction_round_number"] is None
        incident.refresh_from_db()
        assert incident.resolved_by_id == editor.pk and incident.correction_round_id is None
        manuscript_after = Manuscript.objects.get(pk=assignment.manuscript_id)
        assert (manuscript_after.status, manuscript_after.lock_version, manuscript_after.current_round) == (
            manuscript_before.status, manuscript_before.lock_version, manuscript_before.current_round,
        )
        assignment.refresh_from_db()
        assert assignment.status == "ACTIVE" and assignment.revoked_at is None
        assert not CorrectionRound.objects.exists()

    def test_it_is_allowed_even_when_the_manuscript_is_no_longer_under_review(
        self, reviewer, assignment, editor
    ) -> None:
        incident = open_incident(reviewer, assignment)
        Manuscript.objects.filter(pk=assignment.manuscript_id).update(status="REJECTED")

        assert resolve(editor, incident.pk, "DISMISS").status_code == 200


class TestReassign:
    def test_revokes_the_assignment_and_keeps_the_manuscript_under_review(
        self, reviewer, assignment, editor
    ) -> None:
        incident = open_incident(reviewer, assignment)

        response = resolve(editor, incident.pk, "REASSIGN")

        assert response.status_code == 200 and response.json()["resolution"] == "REASSIGN"
        assignment.refresh_from_db()
        assert assignment.status == "REVOKED" and assignment.revoked_by_id == editor.pk
        assert assignment.revocation_reason == "Revocada al resolver un incidente confidencial."
        assert DESCRIPTION not in assignment.revocation_reason
        manuscript = Manuscript.objects.get(pk=assignment.manuscript_id)
        assert manuscript.status == "UNDER_REVIEW" and manuscript.current_round == 0
        assert not CorrectionRound.objects.exists()
        incident.refresh_from_db()
        assert incident.correction_round_id is None

    def test_a_new_reviewer_can_be_assigned_afterwards(
        self, reviewer, assignment, editor
    ) -> None:
        incident = open_incident(reviewer, assignment)
        resolve(editor, incident.pk, "REASSIGN")
        replacement = make_reviewer()

        response = client_for(editor).post(
            f"/api/editor/manuscripts/{assignment.manuscript_id}/assignments/",
            {"reviewer_id": str(replacement.pk)},
            format="json",
        )

        assert response.status_code == 201

    def test_an_expired_assignment_is_revoked_too(self, reviewer, assignment, editor) -> None:
        incident = open_incident(reviewer, assignment)
        set_status(assignment, "EXPIRED")

        assert resolve(editor, incident.pk, "REASSIGN").status_code == 200
        assignment.refresh_from_db()
        assert assignment.status == "REVOKED"

    def test_an_assignment_already_revoked_is_left_as_it_is(
        self, reviewer, assignment, editor
    ) -> None:
        incident = open_incident(reviewer, assignment)
        set_status(assignment, "REVOKED")

        assert resolve(editor, incident.pk, "REASSIGN").status_code == 200
        assert not AuditLog.objects.filter(
            action="ASSIGNMENT_REVOKED", entity_id=assignment.pk
        ).exists()

    @pytest.mark.parametrize("status", ["REQUIRES_CORRECTIONS", "ACCEPTED", "REJECTED"])
    def test_a_manuscript_not_under_review_answers_409_and_changes_nothing(
        self, reviewer, assignment, editor, status
    ) -> None:
        incident = open_incident(reviewer, assignment)
        Manuscript.objects.filter(pk=assignment.manuscript_id).update(status=status)

        response = resolve(editor, incident.pk, "REASSIGN")

        assert response.status_code == 409 and error_code(response) == "STATE_CONFLICT"
        incident.refresh_from_db()
        assert incident.status == "OPEN"
        assignment.refresh_from_db()
        assert assignment.status == "ACTIVE"

    def test_a_withdrawn_manuscript_answers_409(self, reviewer, assignment, editor) -> None:
        incident = open_incident(reviewer, assignment)
        Manuscript.objects.filter(pk=assignment.manuscript_id).update(
            is_active=False, withdrawn_at=timezone.now()
        )

        assert resolve(editor, incident.pk, "REASSIGN").status_code == 409


class TestRequestAnonymizedVersion:
    RESOLUTION = "REQUEST_ANONYMIZED_VERSION"

    def test_puts_the_manuscript_in_corrections_opens_the_round_and_links_it(
        self, reviewer, assignment, editor
    ) -> None:
        incident = open_incident(reviewer, assignment)
        before = Manuscript.objects.get(pk=assignment.manuscript_id)

        response = resolve(editor, incident.pk, self.RESOLUTION)

        assert response.status_code == 200
        body = response.json()
        assert body["resolution"] == self.RESOLUTION and body["correction_round_number"] == 1
        manuscript = Manuscript.objects.get(pk=assignment.manuscript_id)
        assert manuscript.status == "REQUIRES_CORRECTIONS"
        assert manuscript.current_round == before.current_round + 1
        assert manuscript.lock_version == before.lock_version + 1
        opened = CorrectionRound.objects.get(manuscript=manuscript)
        assert opened.round_number == 1 and opened.opened_by_verdict_id is None
        assert opened.closed_by_version_id is None
        incident.refresh_from_db()
        assert incident.correction_round_id == opened.pk
        assert incident.status == "RESOLVED" and incident.resolved_by_id == editor.pk

    def test_it_revokes_the_active_assignment_and_creates_no_verdict(
        self, reviewer, assignment, editor
    ) -> None:
        incident = open_incident(reviewer, assignment)

        resolve(editor, incident.pk, self.RESOLUTION)

        assignment.refresh_from_db()
        assert assignment.status == "REVOKED" and assignment.revoked_by_id == editor.pk
        assert not Verdict.objects.exists()

    def test_the_status_event_has_a_fixed_text_that_names_nobody(
        self, reviewer, assignment, editor
    ) -> None:
        incident = open_incident(reviewer, assignment)

        resolve(editor, incident.pk, self.RESOLUTION)

        event = StatusEvent.objects.filter(manuscript=assignment.manuscript).latest("id")
        assert (event.from_status, event.to_status) == ("UNDER_REVIEW", "REQUIRES_CORRECTIONS")
        assert event.reason == "Se solicita una versión anonimizada del manuscrito."
        assert event.metadata == {"round_number": 1, "cause": self.RESOLUTION}
        assert event.actor_id == editor.pk

    def test_it_is_audited_with_the_round_and_the_revocation(
        self, reviewer, assignment, editor
    ) -> None:
        incident = open_incident(reviewer, assignment)

        resolve(editor, incident.pk, self.RESOLUTION)

        resolved = AuditLog.objects.get(action="INCIDENT_RESOLVED")
        opened = CorrectionRound.objects.get()
        assert resolved.actor_id == editor.pk and resolved.actor_role == "EDITOR"
        assert resolved.entity_type == "INCIDENT_REPORT" and resolved.entity_id == incident.pk
        assert resolved.details == {
            "manuscript_id": str(assignment.manuscript_id),
            "assignment_id": str(assignment.pk),
            "resolution": self.RESOLUTION,
            "assignment_revoked": True,
            "correction_round_id": str(opened.pk),
            "round_number": 1,
        }
        revoked = AuditLog.objects.get(action="ASSIGNMENT_REVOKED", entity_id=assignment.pk)
        assert revoked.details["cause"] == "IDENTITY_LEAK"
        assert DESCRIPTION not in str(resolved.details) + str(revoked.details) + str(revoked.reason)

    def test_the_author_can_answer_with_a_new_version(
        self, owner, reviewer, editor, submit, send
    ) -> None:
        """The whole path with real PDFs: report, resolution and the author's reply."""
        manuscript = ready_draft(owner)
        assert submit(owner, manuscript).status_code == 201
        Manuscript.objects.filter(pk=manuscript.pk).update(status="UNDER_REVIEW")
        leaked = make_assignment(manuscript, reviewer, editor)
        incident = open_incident(reviewer, leaked)
        assert resolve(editor, incident.pk, self.RESOLUTION).status_code == 200

        response = send(owner, manuscript)

        assert response.status_code == 201, response.content
        assert response.json()["version_number"] == 2
        manuscript.refresh_from_db()
        assert manuscript.status == "SUBMITTED" and manuscript.current_version == 2
        opened = CorrectionRound.objects.get(manuscript=manuscript, round_number=1)
        assert opened.closed_by_version.version_number == 2


class TestResolveOnce:
    @pytest.mark.parametrize("again", ["DISMISS", "REASSIGN", "REQUEST_ANONYMIZED_VERSION"])
    def test_a_second_resolution_answers_409_and_changes_nothing(
        self, reviewer, assignment, editor, again
    ) -> None:
        incident = open_incident(reviewer, assignment)
        assert resolve(editor, incident.pk, "DISMISS").status_code == 200
        snapshot = (
            Manuscript.objects.values_list("status", "current_round", "lock_version").get(
                pk=assignment.manuscript_id
            ),
            Assignment.objects.values_list("status", flat=True).get(pk=assignment.pk),
        )

        response = resolve(editor, incident.pk, again)

        assert response.status_code == 409 and error_code(response) == "STATE_CONFLICT"
        incident.refresh_from_db()
        assert incident.resolution == "DISMISS"
        assert snapshot == (
            Manuscript.objects.values_list("status", "current_round", "lock_version").get(
                pk=assignment.manuscript_id
            ),
            Assignment.objects.values_list("status", flat=True).get(pk=assignment.pk),
        )
        assert AuditLog.objects.filter(action="INCIDENT_RESOLVED").count() == 1

    def test_a_second_request_after_the_anonymization_does_not_open_another_round(
        self, reviewer, assignment, editor
    ) -> None:
        incident = open_incident(reviewer, assignment)
        resolve(editor, incident.pk, "REQUEST_ANONYMIZED_VERSION")

        resolve(editor, incident.pk, "REQUEST_ANONYMIZED_VERSION")

        assert CorrectionRound.objects.count() == 1
        assert Manuscript.objects.get(pk=assignment.manuscript_id).current_round == 1


class TestResolveAtomicity:
    @pytest.mark.parametrize("resolution", ["DISMISS", "REASSIGN", "REQUEST_ANONYMIZED_VERSION"])
    def test_an_unavailable_audit_answers_503_and_reverts_everything(
        self, reviewer, assignment, editor, monkeypatch, resolution
    ) -> None:
        incident = open_incident(reviewer, assignment)
        before = Manuscript.objects.get(pk=assignment.manuscript_id)
        events_before = StatusEvent.objects.count()
        failing_audit(monkeypatch)

        response = resolve(editor, incident.pk, resolution)

        assert response.status_code == 503 and error_code(response) == "AUDIT_UNAVAILABLE"
        incident.refresh_from_db()
        assert incident.status == "OPEN" and incident.resolution is None
        assert incident.correction_round_id is None
        assignment.refresh_from_db()
        assert assignment.status == "ACTIVE" and assignment.revoked_at is None
        after = Manuscript.objects.get(pk=assignment.manuscript_id)
        assert (after.status, after.current_round, after.lock_version) == (
            before.status, before.current_round, before.lock_version,
        )
        assert not CorrectionRound.objects.exists()
        assert StatusEvent.objects.count() == events_before

    def test_the_events_are_sent_after_the_commit_with_identifiers_only(
        self, reviewer, assignment, editor, django_capture_on_commit_callbacks
    ) -> None:
        incident = open_incident(reviewer, assignment)

        with listening(incident_resolved) as resolved, listening(assignment_revoked) as revoked:
            with django_capture_on_commit_callbacks(execute=True):
                assert resolve(editor, incident.pk, "REQUEST_ANONYMIZED_VERSION").status_code == 200

        opened = CorrectionRound.objects.get()
        assert resolved == [
            {
                "incident_id": incident.pk,
                "assignment_id": assignment.pk,
                "manuscript_id": assignment.manuscript_id,
                "resolution": "REQUEST_ANONYMIZED_VERSION",
                "correction_round_id": opened.pk,
            }
        ]
        assert revoked == [
            {
                "assignment_id": assignment.pk,
                "manuscript_id": assignment.manuscript_id,
                "reviewer_id": reviewer.pk,
                "cause": "IDENTITY_LEAK",
            }
        ]

    def test_no_event_is_sent_when_the_resolution_fails(
        self, reviewer, assignment, editor, django_capture_on_commit_callbacks
    ) -> None:
        incident = open_incident(reviewer, assignment)
        resolve(editor, incident.pk, "DISMISS")

        with listening(incident_resolved) as resolved:
            with django_capture_on_commit_callbacks(execute=True):
                resolve(editor, incident.pk, "REASSIGN")

        assert resolved == []


class TestAuthorNeverLearns:
    """CA-HU-16-06: the author reads nothing of the report nor of the reviewer."""

    @pytest.fixture
    def secrets(self, reviewer, assignment) -> list[str]:
        return [
            reviewer.get_full_name(),
            reviewer.email,
            reviewer.institutional_id,
            DESCRIPTION,
            "IDENTITY_LEAK",
            "identity-leak",
            "incident",
            "fuga",
        ]

    def author_text(self, owner, assignment) -> str:
        client = client_for(owner)
        manuscript = assignment.manuscript
        responses = [
            client.get(manuscript_url(manuscript)),
            client.get(f"{manuscript_url(manuscript)}history/"),
            client.get(f"{manuscript_url(manuscript)}versions/"),
            client.get("/api/manuscripts/"),
        ]
        assert all(r.status_code == 200 for r in responses)
        return "".join(r.content.decode() + str(r.headers) for r in responses)

    def test_while_the_report_is_open(self, owner, reviewer, assignment, secrets) -> None:
        incident = open_incident(reviewer, assignment)

        text = self.author_text(owner, assignment)

        for secret in [*secrets, str(incident.pk)]:
            assert secret.lower() not in text.lower()

    @pytest.mark.parametrize("resolution", ["DISMISS", "REASSIGN", "REQUEST_ANONYMIZED_VERSION"])
    def test_after_each_resolution(
        self, owner, reviewer, assignment, editor, secrets, resolution
    ) -> None:
        incident = open_incident(reviewer, assignment)
        resolve(editor, incident.pk, resolution)

        text = self.author_text(owner, assignment)

        for secret in [*secrets, str(incident.pk)]:
            assert secret.lower() not in text.lower()

    def test_the_author_sees_the_request_and_the_new_round_only(
        self, owner, reviewer, assignment, editor
    ) -> None:
        incident = open_incident(reviewer, assignment)
        resolve(editor, incident.pk, "REQUEST_ANONYMIZED_VERSION")
        client = client_for(owner)

        detail = client.get(manuscript_url(assignment.manuscript)).json()
        history = client.get(f"{manuscript_url(assignment.manuscript)}history/").json()["results"]

        assert detail["status"] == "REQUIRES_CORRECTIONS" and detail["current_round"] == 1
        assert detail["feedback"] is None
        changed = [e for e in history if e["type"] == "STATUS_CHANGED"][-1]
        assert changed["to_status"] == "REQUIRES_CORRECTIONS"
        assert changed["reason"] == "Se solicita una versión anonimizada del manuscrito."
        assert any(e["type"] == "ROUND_OPENED" and e["round_number"] == 1 for e in history)

    def test_the_author_cannot_reach_the_incident_endpoints(
        self, owner, reviewer, assignment
    ) -> None:
        incident = open_incident(reviewer, assignment)
        client = client_for(owner)

        assert client.get(EDITOR_BASE).status_code == 403
        assert client.post(resolve_url(incident.pk), {}, format="json").status_code == 403
        assert client.post(leak_url(assignment), {}, format="json").status_code == 403
