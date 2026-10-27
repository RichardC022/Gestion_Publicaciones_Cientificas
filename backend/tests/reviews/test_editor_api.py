"""Tests for the editor endpoints of the reviews module (TSK-47).

Covers the acceptance criteria: the inbox only lists ``SUBMITTED`` and the
detail carries metadata, authors, PDFs and history; a second ``ACTIVE``
assignment answers ``409`` and an ``EXPIRED`` one must be revoked before
reassigning; an editor who registered or co-authored a manuscript can
neither see nor assign it.

Plus the contracts of the plan: the deadline is fixed by PostgreSQL,
the transition to ``UNDER_REVIEW`` and the assignment are atomic, early
revocation is limited to its three causes, and an unavailable audit
trail reverts the action with ``503``.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.audit.services import AuditService, AuditUnavailable
from apps.publications.models import Manuscript, StatusEvent
from apps.reviews.models import Assignment, Evaluation
from apps.users.models import ReviewerProfile
from tests.factories import (
    ManuscriptAuthorFactory,
    ManuscriptFactory,
    ManuscriptVersionFactory,
    UserFactory,
    UserRoleFactory,
)
from tests.publications.test_manuscript_api import actor, client_for, error_code

pytestmark = pytest.mark.django_db

BASE = "/api/editor/"
AREA = "Agronomía"


@pytest.fixture(autouse=True)
def seeded_roles(db) -> None:
    call_command("seed_roles", verbosity=0)


def make_reviewer(*, areas=(AREA,), available=True, **overrides):
    """Active reviewer with a profile."""
    user = actor("REVIEWER", **overrides)
    ReviewerProfile.objects.create(
        user=user, expertise_areas=list(areas), is_available=available
    )
    return user


def submitted(owner=None, *, status="SUBMITTED", **overrides) -> Manuscript:
    """A formally submitted manuscript: author row, version 1 and initial event."""
    owner = owner or actor("AUTHOR")
    manuscript = ManuscriptFactory(
        created_by=owner,
        status=status,
        current_version=1,
        area=overrides.pop("area", AREA),
        **overrides,
    )
    ManuscriptAuthorFactory(
        manuscript=manuscript,
        user=owner,
        email=owner.email,
        is_corresponding=True,
        author_order=1,
    )
    ManuscriptVersionFactory(manuscript=manuscript, submitted_by=owner)
    return manuscript


def make_assignment(manuscript, reviewer, editor, *, days_ago=0, **overrides) -> Assignment:
    assigned_at = timezone.now() - timedelta(days=days_ago)
    values = {
        "manuscript": manuscript,
        "version": manuscript.versions.get(version_number=1),
        "reviewer": reviewer,
        "assigned_by": editor,
        "assigned_at": assigned_at,
        "due_at": assigned_at + timedelta(days=20),
        **overrides,
    }
    return Assignment.objects.create(**values)


@pytest.fixture
def editor():
    return actor("EDITOR")


@pytest.fixture
def reviewer():
    return make_reviewer()


def results(response) -> list[dict]:
    return response.json()["results"]


class TestAccess:
    @pytest.mark.parametrize(
        "path",
        ["submissions/", "reviewers/", "assignments/expired/"],
    )
    def test_anonymous_gets_401(self, path) -> None:
        from rest_framework.test import APIClient

        assert APIClient().get(BASE + path).status_code == 401

    @pytest.mark.parametrize("role", ["AUTHOR", "REVIEWER"])
    @pytest.mark.parametrize(
        "path",
        ["submissions/", "reviewers/", "assignments/expired/"],
    )
    def test_other_roles_get_403(self, role, path) -> None:
        assert client_for(actor(role)).get(BASE + path).status_code == 403

    def test_a_revoked_editor_role_blocks_the_next_request(self, editor) -> None:
        client = client_for(editor)
        assert client.get(BASE + "submissions/").status_code == 200

        editor.role_assignments.update(is_active=False)

        assert client.get(BASE + "submissions/").status_code == 403


class TestInbox:
    def test_lists_only_submitted_manuscripts(self, editor) -> None:
        inbox = submitted()
        submitted(status="UNDER_REVIEW")
        submitted(status="REQUIRES_CORRECTIONS")
        ManuscriptFactory(created_by=actor("AUTHOR"), status="DRAFT")

        response = client_for(editor).get(BASE + "submissions/")

        assert response.status_code == 200
        assert [row["id"] for row in results(response)] == [str(inbox.pk)]

    def test_rows_carry_the_submission_date_and_no_authors(self, editor) -> None:
        manuscript = submitted()

        row = results(client_for(editor).get(BASE + "submissions/"))[0]

        assert row["code"] == manuscript.code
        assert row["submitted_at"] is not None
        assert "authors" not in row and "created_by" not in row

    def test_rows_name_the_corresponding_author_without_extra_queries(
        self, editor, django_assert_max_num_queries
    ) -> None:
        first = submitted()
        ManuscriptAuthorFactory(
            manuscript=first, user=None, full_name="Luis Pérez", email="luis@x.edu", author_order=2
        )
        for _ in range(4):
            submitted()

        with django_assert_max_num_queries(12):
            rows = results(client_for(editor).get(BASE + "submissions/"))

        by_id = {row["id"]: row for row in rows}
        assert len(rows) == 5
        corresponding = first.authors.get(is_corresponding=True)
        assert by_id[str(first.pk)]["corresponding_author"] == corresponding.full_name
        assert by_id[str(first.pk)]["corresponding_author"] != "Luis Pérez"
        assert all(row["corresponding_author"] for row in rows)
        assert "email" not in str(rows) and "affiliation" not in str(rows)

    def test_withdrawn_manuscripts_are_not_listed(self, editor) -> None:
        submitted(is_active=False, withdrawn_at=timezone.now())

        assert results(client_for(editor).get(BASE + "submissions/")) == []

    def test_a_manuscript_with_conflict_of_interest_is_not_listed(self) -> None:
        both = actor("AUTHOR", "EDITOR")
        own = submitted(both)
        coauthored = submitted()
        ManuscriptAuthorFactory(manuscript=coauthored, user=both, author_order=2)
        free = submitted()

        response = client_for(both).get(BASE + "submissions/")

        assert [row["id"] for row in results(response)] == [str(free.pk)]
        assert str(own.pk) not in str(response.json())

    def test_filters_by_area_and_validates_them(self, editor) -> None:
        submitted(area="Medicina")
        agro = submitted()

        by_area = client_for(editor).get(BASE + "submissions/", {"area": AREA})
        malformed = client_for(editor).get(BASE + "submissions/", {"date_from": "ayer"})

        assert [row["id"] for row in results(by_area)] == [str(agro.pk)]
        assert malformed.status_code == 400

    def test_is_paginated(self, editor) -> None:
        for _ in range(3):
            submitted()

        body = client_for(editor).get(BASE + "submissions/", {"page_size": 2}).json()

        assert body["count"] == 3 and len(body["results"]) == 2


class TestDetail:
    def test_returns_metadata_authors_pdfs_and_history(self, editor) -> None:
        manuscript = submitted()
        StatusEvent.objects.create(manuscript=manuscript, to_status="SUBMITTED")

        response = client_for(editor).get(f"{BASE}submissions/{manuscript.pk}/")

        body = response.json()
        assert response.status_code == 200
        assert body["code"] == manuscript.code and body["abstract"]
        assert body["authors"][0]["email"] == manuscript.created_by.email
        version = body["versions"][0]
        assert version["file_url"] == (
            f"/api/manuscripts/{manuscript.pk}/versions/{version['id']}/file/"
        )
        assert {entry["type"] for entry in body["history"]} >= {"VERSION_SUBMITTED"}
        assert body["open_assignment"] is None
        assert response["ETag"] == f'"{manuscript.lock_version}"'

    def test_never_exposes_volume_paths(self, editor) -> None:
        manuscript = submitted()

        text = client_for(editor).get(f"{BASE}submissions/{manuscript.pk}/").content.decode()

        assert "file_path" not in text and "sanitized" not in text

    def test_shows_the_open_assignment(self, editor, reviewer) -> None:
        manuscript = submitted(status="UNDER_REVIEW")
        make_assignment(manuscript, reviewer, editor)

        body = client_for(editor).get(f"{BASE}submissions/{manuscript.pk}/").json()

        assert body["open_assignment"]["reviewer"]["email"] == reviewer.email

    def test_a_draft_answers_404(self, editor) -> None:
        draft = ManuscriptFactory(created_by=actor("AUTHOR"), status="DRAFT")

        assert client_for(editor).get(f"{BASE}submissions/{draft.pk}/").status_code == 404

    def test_a_conflicted_editor_answers_404(self) -> None:
        both = actor("AUTHOR", "EDITOR")
        own = submitted(both)

        assert client_for(both).get(f"{BASE}submissions/{own.pk}/").status_code == 404


class TestStartReview:
    def url(self, manuscript) -> str:
        return f"{BASE}submissions/{manuscript.pk}/start-review/"

    def test_moves_to_under_review_and_records_the_event_and_audit(self, editor) -> None:
        manuscript = submitted()

        response = client_for(editor).post(self.url(manuscript), {}, format="json")

        assert response.status_code == 200
        assert response.json()["status"] == "UNDER_REVIEW"
        assert response.json()["assignment"] is None
        manuscript.refresh_from_db()
        assert manuscript.status == "UNDER_REVIEW" and manuscript.lock_version == 1
        event = manuscript.status_events.get()
        assert (event.from_status, event.to_status, event.actor) == (
            "SUBMITTED",
            "UNDER_REVIEW",
            editor,
        )
        audit = AuditLog.objects.get(action="REVIEW_STARTED")
        assert audit.actor_role == "EDITOR" and audit.entity_id == manuscript.pk

    def test_can_assign_the_reviewer_in_the_same_request(self, editor, reviewer) -> None:
        manuscript = submitted()

        response = client_for(editor).post(
            self.url(manuscript), {"reviewer_id": str(reviewer.pk)}, format="json"
        )

        assert response.status_code == 200
        assignment = Assignment.objects.get(manuscript=manuscript)
        assert response.json()["assignment"]["id"] == str(assignment.pk)
        assert assignment.due_at - assignment.assigned_at == timedelta(days=20)
        assert assignment.assigned_by == editor and assignment.status == "ACTIVE"

    def test_an_invalid_reviewer_reverts_the_transition(self, editor) -> None:
        manuscript = submitted()
        not_a_reviewer = actor("AUTHOR")

        response = client_for(editor).post(
            self.url(manuscript), {"reviewer_id": str(not_a_reviewer.pk)}, format="json"
        )

        assert response.status_code == 400 and error_code(response) == "VALIDATION_ERROR"
        manuscript.refresh_from_db()
        assert manuscript.status == "SUBMITTED" and manuscript.lock_version == 0
        assert not manuscript.status_events.exists()
        assert not AuditLog.objects.filter(action="REVIEW_STARTED").exists()

    @pytest.mark.parametrize("status", ["UNDER_REVIEW", "ACCEPTED", "REJECTED", "REQUIRES_CORRECTIONS"])
    def test_only_a_submitted_manuscript_can_start_review(self, editor, status) -> None:
        manuscript = submitted(status=status)

        response = client_for(editor).post(self.url(manuscript), {}, format="json")

        assert response.status_code == 409 and error_code(response) == "STATE_CONFLICT"

    def test_a_second_start_answers_409(self, editor) -> None:
        manuscript = submitted()
        client = client_for(editor)
        assert client.post(self.url(manuscript), {}, format="json").status_code == 200

        assert client.post(self.url(manuscript), {}, format="json").status_code == 409
        assert manuscript.status_events.count() == 1

    def test_a_withdrawn_manuscript_answers_409(self, editor) -> None:
        manuscript = submitted(is_active=False, withdrawn_at=timezone.now())

        assert client_for(editor).post(self.url(manuscript), {}, format="json").status_code == 409

    def test_a_conflicted_editor_answers_404(self) -> None:
        both = actor("AUTHOR", "EDITOR")
        own = submitted(both)

        assert client_for(both).post(self.url(own), {}, format="json").status_code == 404

    def test_a_malformed_reviewer_id_answers_400(self, editor) -> None:
        manuscript = submitted()

        response = client_for(editor).post(self.url(manuscript), {"reviewer_id": "x"}, format="json")

        assert response.status_code == 400

    def test_audit_failure_reverts_everything_with_503(self, editor, reviewer, monkeypatch) -> None:
        manuscript = submitted()

        def fail(**kwargs):
            raise AuditUnavailable("sin auditoría")

        monkeypatch.setattr(AuditService, "record", staticmethod(fail))
        response = client_for(editor).post(
            self.url(manuscript), {"reviewer_id": str(reviewer.pk)}, format="json"
        )

        assert response.status_code == 503 and error_code(response) == "AUDIT_UNAVAILABLE"
        manuscript.refresh_from_db()
        assert manuscript.status == "SUBMITTED"
        assert not Assignment.objects.exists() and not manuscript.status_events.exists()


class TestAssign:
    def url(self, manuscript) -> str:
        return f"{BASE}manuscripts/{manuscript.pk}/assignments/"

    def assign(self, editor, manuscript, reviewer):
        return client_for(editor).post(
            self.url(manuscript), {"reviewer_id": str(reviewer.pk)}, format="json"
        )

    def test_creates_the_assignment_with_a_twenty_day_deadline_set_by_postgresql(
        self, editor, reviewer
    ) -> None:
        manuscript = submitted(status="UNDER_REVIEW")

        response = self.assign(editor, manuscript, reviewer)

        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "ACTIVE" and body["is_overdue"] is False
        assert body["reviewer"]["email"] == reviewer.email
        assert body["version_number"] == 1
        assignment = Assignment.objects.get(pk=body["id"])
        assert assignment.due_at - assignment.assigned_at == timedelta(days=20)
        assert abs(timezone.now() - assignment.assigned_at) < timedelta(minutes=1)
        audit = AuditLog.objects.get(action="ASSIGNMENT_CREATED")
        assert audit.entity_id == assignment.pk and audit.actor_role == "EDITOR"

    def test_a_second_active_assignment_answers_409(self, editor, reviewer) -> None:
        manuscript = submitted(status="UNDER_REVIEW")
        assert self.assign(editor, manuscript, reviewer).status_code == 201

        response = self.assign(editor, manuscript, make_reviewer())

        assert response.status_code == 409 and error_code(response) == "ASSIGNMENT_CONFLICT"
        assert manuscript.assignments.count() == 1

    def test_an_expired_assignment_must_be_revoked_before_reassigning(
        self, editor, reviewer
    ) -> None:
        manuscript = submitted(status="UNDER_REVIEW")
        expired = make_assignment(manuscript, reviewer, editor, days_ago=25, status="EXPIRED")
        other = make_reviewer()

        blocked = self.assign(editor, manuscript, other)
        revoked = client_for(editor).post(
            f"{BASE}assignments/{expired.pk}/revoke/",
            {"cause": "OVERDUE", "reason": "Sin respuesta del Revisor."},
            format="json",
        )
        reassigned = self.assign(editor, manuscript, other)

        assert blocked.status_code == 409 and error_code(blocked) == "ASSIGNMENT_CONFLICT"
        assert revoked.status_code == 200
        assert reassigned.status_code == 201

    def test_reassigning_keeps_round_and_version(self, editor, reviewer) -> None:
        manuscript = submitted(status="UNDER_REVIEW", current_round=1)
        old = make_assignment(manuscript, reviewer, editor, status="REVOKED")

        self.assign(editor, manuscript, make_reviewer())

        manuscript.refresh_from_db()
        assert (manuscript.current_round, manuscript.current_version) == (1, 1)
        assert old.pk != manuscript.assignments.get(status="ACTIVE").pk

    @pytest.mark.parametrize("status", ["SUBMITTED", "ACCEPTED", "REQUIRES_CORRECTIONS"])
    def test_requires_a_manuscript_under_review(self, editor, reviewer, status) -> None:
        manuscript = submitted(status=status)

        response = self.assign(editor, manuscript, reviewer)

        assert response.status_code == 409 and error_code(response) == "STATE_CONFLICT"

    def test_a_withdrawn_manuscript_answers_409(self, editor, reviewer) -> None:
        manuscript = submitted(
            status="UNDER_REVIEW", is_active=False, withdrawn_at=timezone.now()
        )

        assert self.assign(editor, manuscript, reviewer).status_code == 409

    def test_the_registrant_and_authors_are_never_assignable(self, editor) -> None:
        owner = make_reviewer()
        manuscript = submitted(owner, status="UNDER_REVIEW")
        coauthor_user = make_reviewer()
        ManuscriptAuthorFactory(
            manuscript=manuscript, user=coauthor_user, email=coauthor_user.email, author_order=2
        )
        by_email = make_reviewer()
        ManuscriptAuthorFactory(
            manuscript=manuscript, user=None, email=by_email.email.upper(), author_order=3
        )

        for conflicted in (owner, coauthor_user, by_email):
            response = self.assign(editor, manuscript, conflicted)
            assert response.status_code == 400, conflicted
            assert "reviewer_id" in response.json()["error"]["details"]

        assert not manuscript.assignments.exists()

    @pytest.mark.parametrize("kind", ["author", "inactive", "unknown"])
    def test_a_non_reviewer_account_is_rejected(self, editor, kind) -> None:
        manuscript = submitted(status="UNDER_REVIEW")
        if kind == "author":
            target = actor("AUTHOR")
        elif kind == "inactive":
            target = make_reviewer(is_active=False)
        else:
            target = UserFactory.build()

        response = self.assign(editor, manuscript, target)

        assert response.status_code == 400 and error_code(response) == "VALIDATION_ERROR"

    def test_requires_a_reviewer_id(self, editor) -> None:
        manuscript = submitted(status="UNDER_REVIEW")

        response = client_for(editor).post(self.url(manuscript), {}, format="json")

        assert response.status_code == 400

    def test_a_conflicted_editor_cannot_assign(self, reviewer) -> None:
        both = actor("AUTHOR", "EDITOR")
        own = submitted(both, status="UNDER_REVIEW")

        response = self.assign(both, own, reviewer)

        assert response.status_code == 404 and not Assignment.objects.exists()

    def test_audit_failure_reverts_the_assignment_with_503(
        self, editor, reviewer, monkeypatch
    ) -> None:
        manuscript = submitted(status="UNDER_REVIEW")

        def fail(**kwargs):
            raise AuditUnavailable("sin auditoría")

        monkeypatch.setattr(AuditService, "record", staticmethod(fail))
        response = self.assign(editor, manuscript, reviewer)

        assert response.status_code == 503 and error_code(response) == "AUDIT_UNAVAILABLE"
        assert not Assignment.objects.exists()

    def test_history_lists_every_assignment_with_the_reviewer_identity(
        self, editor, reviewer
    ) -> None:
        manuscript = submitted(status="UNDER_REVIEW")
        make_assignment(
            manuscript, reviewer, editor, days_ago=30, status="REVOKED",
            revocation_reason="Error de asignación",
        )
        current = make_assignment(manuscript, make_reviewer(), editor)

        response = client_for(editor).get(self.url(manuscript))

        rows = results(response)
        assert [row["status"] for row in rows] == ["ACTIVE", "REVOKED"]
        assert rows[0]["id"] == str(current.pk)
        assert rows[1]["reviewer"]["email"] == reviewer.email
        assert rows[1]["revocation_reason"] == "Error de asignación"

    def test_history_of_a_conflicted_editor_answers_404(self) -> None:
        both = actor("AUTHOR", "EDITOR")
        own = submitted(both, status="UNDER_REVIEW")

        assert client_for(both).get(self.url(own)).status_code == 404


class TestRevoke:
    def url(self, assignment) -> str:
        return f"{BASE}assignments/{assignment.pk}/revoke/"

    def revoke(self, editor, assignment, **body):
        return client_for(editor).post(self.url(assignment), body, format="json")

    @pytest.fixture
    def active(self, editor, reviewer) -> Assignment:
        return make_assignment(submitted(status="UNDER_REVIEW"), reviewer, editor)

    @pytest.mark.parametrize(
        "cause", ["CONFLICT_OF_INTEREST", "ASSIGNMENT_ERROR", "ACCOUNT_DISABLED"]
    )
    def test_an_early_revocation_accepts_its_three_causes(self, editor, active, cause) -> None:
        response = self.revoke(editor, active, cause=cause, reason="Motivo escrito.")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "REVOKED" and body["revocation_reason"] == "Motivo escrito."
        assert body["revoked_by"]["id"] == str(editor.pk) and body["revoked_at"]
        active.refresh_from_db()
        assert active.status == "REVOKED" and active.lock_version == 1
        audit = AuditLog.objects.get(action="ASSIGNMENT_REVOKED")
        assert audit.details["cause"] == cause and audit.reason == "Motivo escrito."

    def test_overdue_cause_is_invalid_before_the_deadline(self, editor, active) -> None:
        response = self.revoke(editor, active, cause="OVERDUE", reason="Se demora.")

        assert response.status_code == 400
        assert "cause" in response.json()["error"]["details"]
        active.refresh_from_db()
        assert active.status == "ACTIVE"

    def test_an_active_assignment_past_its_deadline_accepts_any_cause(
        self, editor, reviewer
    ) -> None:
        late = make_assignment(submitted(status="UNDER_REVIEW"), reviewer, editor, days_ago=21)

        assert self.revoke(editor, late, cause="OVERDUE", reason="Venció.").status_code == 200

    def test_an_expired_assignment_can_be_revoked(self, editor, reviewer) -> None:
        expired = make_assignment(
            submitted(status="UNDER_REVIEW"), reviewer, editor, days_ago=25, status="EXPIRED"
        )

        response = self.revoke(editor, expired, cause="OVERDUE", reason="Venció.")

        assert response.status_code == 200 and response.json()["status"] == "REVOKED"

    @pytest.mark.parametrize("body", [{}, {"cause": "OVERDUE"}, {"reason": "x"}, {"cause": "OTHER", "reason": "x"}])
    def test_cause_and_reason_are_mandatory(self, editor, active, body) -> None:
        assert self.revoke(editor, active, **body).status_code == 400

    @pytest.mark.parametrize("reason", ["", "   "])
    def test_a_blank_reason_is_rejected(self, editor, active, reason) -> None:
        response = self.revoke(editor, active, cause="ASSIGNMENT_ERROR", reason=reason)

        assert response.status_code == 400
        active.refresh_from_db()
        assert active.status == "ACTIVE"

    @pytest.mark.parametrize("status", ["REVOKED", "COMPLETED"])
    def test_a_closed_assignment_answers_409(self, editor, reviewer, status) -> None:
        closed = make_assignment(submitted(status="UNDER_REVIEW"), reviewer, editor, status=status)

        response = self.revoke(editor, closed, cause="ASSIGNMENT_ERROR", reason="x")

        assert response.status_code == 409 and error_code(response) == "STATE_CONFLICT"

    def test_the_manuscript_stays_under_review_and_the_evaluation_is_untouched(
        self, editor, active
    ) -> None:
        evaluation = Evaluation.objects.create(
            assignment=active,
            manuscript=active.manuscript,
            version=active.version,
            reviewer=active.reviewer,
            clarity_score=3,
        )

        self.revoke(editor, active, cause="ASSIGNMENT_ERROR", reason="Se equivocó.")

        active.manuscript.refresh_from_db()
        evaluation.refresh_from_db()
        assert active.manuscript.status == "UNDER_REVIEW"
        assert evaluation.status == "DRAFT" and evaluation.clarity_score == 3

    def test_an_assignment_of_a_conflicted_editor_answers_404(self, reviewer) -> None:
        both = actor("AUTHOR", "EDITOR")
        own = submitted(both, status="UNDER_REVIEW")
        assignment = make_assignment(own, reviewer, both)

        response = self.revoke(both, assignment, cause="ASSIGNMENT_ERROR", reason="x")

        assert response.status_code == 404

    def test_audit_failure_keeps_the_assignment_active(self, editor, active, monkeypatch) -> None:
        def fail(**kwargs):
            raise AuditUnavailable("sin auditoría")

        monkeypatch.setattr(AuditService, "record", staticmethod(fail))
        response = self.revoke(editor, active, cause="ASSIGNMENT_ERROR", reason="x")

        assert response.status_code == 503
        active.refresh_from_db()
        assert active.status == "ACTIVE" and active.revoked_at is None


class TestExpired:
    URL = BASE + "assignments/expired/"

    def test_lists_expired_and_overdue_active_assignments(self, editor, reviewer) -> None:
        expired = make_assignment(
            submitted(status="UNDER_REVIEW"), reviewer, editor, days_ago=30, status="EXPIRED"
        )
        overdue = make_assignment(submitted(status="UNDER_REVIEW"), make_reviewer(), editor, days_ago=21)
        make_assignment(submitted(status="UNDER_REVIEW"), make_reviewer(), editor, days_ago=5)
        make_assignment(
            submitted(status="UNDER_REVIEW"), make_reviewer(), editor, days_ago=40, status="REVOKED"
        )

        rows = results(client_for(editor).get(self.URL))

        assert [row["id"] for row in rows] == [str(expired.pk), str(overdue.pk)]
        assert rows[0]["reviewer"]["email"] == reviewer.email
        assert rows[1]["status"] == "ACTIVE" and rows[1]["is_overdue"] is True

    def test_excludes_withdrawn_manuscripts_and_conflicts(self, editor, reviewer) -> None:
        withdrawn = submitted(
            status="UNDER_REVIEW", is_active=False, withdrawn_at=timezone.now()
        )
        make_assignment(withdrawn, reviewer, editor, days_ago=30, status="EXPIRED")
        both = actor("AUTHOR", "EDITOR")
        own = submitted(both, status="UNDER_REVIEW")
        make_assignment(own, make_reviewer(), editor, days_ago=30, status="EXPIRED")

        assert results(client_for(both).get(self.URL)) == []
        assert results(client_for(editor).get(self.URL))[0]["manuscript"] == str(own.pk)

    def test_is_empty_without_overdue_assignments(self, editor, reviewer) -> None:
        make_assignment(submitted(status="UNDER_REVIEW"), reviewer, editor)

        assert results(client_for(editor).get(self.URL)) == []


class TestEligibleReviewers:
    URL = BASE + "reviewers/"

    def test_lists_available_reviewers_with_their_load(self, editor) -> None:
        busy = make_reviewer()
        make_assignment(submitted(status="UNDER_REVIEW"), busy, editor)
        make_reviewer(available=False)
        make_reviewer(is_active=False)
        actor("AUTHOR")

        rows = results(client_for(editor).get(self.URL))

        assert [row["id"] for row in rows] == [str(busy.pk)]
        assert rows[0]["active_assignments"] == 1 and rows[0]["max_active_assignments"] == 3
        assert rows[0]["expertise_areas"] == [AREA] and rows[0]["email"] == busy.email

    def test_filters_by_area(self, editor) -> None:
        agro = make_reviewer()
        make_reviewer(areas=("Medicina",))

        rows = results(client_for(editor).get(self.URL, {"area": AREA}))

        assert [row["id"] for row in rows] == [str(agro.pk)]

    def test_a_manuscript_defaults_the_area_and_excludes_its_authors(self, editor) -> None:
        owner = make_reviewer()
        manuscript = submitted(owner, status="UNDER_REVIEW")
        coauthor = make_reviewer()
        ManuscriptAuthorFactory(manuscript=manuscript, user=coauthor, email="otro@x.edu", author_order=2)
        by_email = make_reviewer()
        ManuscriptAuthorFactory(manuscript=manuscript, user=None, email=by_email.email, author_order=3)
        make_reviewer(areas=("Medicina",))
        eligible = make_reviewer()

        rows = results(
            client_for(editor).get(self.URL, {"manuscript_id": str(manuscript.pk)})
        )

        assert [row["id"] for row in rows] == [str(eligible.pk)]

    def test_a_foreign_manuscript_answers_404(self) -> None:
        both = actor("AUTHOR", "EDITOR")
        own = submitted(both)

        response = client_for(both).get(self.URL, {"manuscript_id": str(own.pk)})

        assert response.status_code == 404

    def test_a_malformed_manuscript_id_answers_400(self, editor) -> None:
        assert client_for(editor).get(self.URL, {"manuscript_id": "x"}).status_code == 400
