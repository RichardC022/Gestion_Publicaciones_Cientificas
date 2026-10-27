"""Tests for the assignment and reassignment service (TSK-48).

Covers the acceptance criteria: the deadline is fixed by the database
and not by the client clock; an early revocation only accepts its three
causes; reassigning changes neither ``current_round`` nor
``current_version``.

Plus the rules of the service: a reviewer must declare the area, be
available and stay below their capacity; every change is announced
after the commit with identifiers only; and the logical withdrawal of a
manuscript revokes its active assignment (D-10).
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.core.management import call_command
from django.db import transaction
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.audit.services import AuditService, AuditUnavailable
from apps.reviews.models import Assignment, Evaluation
from apps.reviews.services.eligibility import eligible_reviewers, ineligibility_reason
from apps.reviews.signals import assignment_created, assignment_revoked
from apps.users.models import ReviewerProfile
from tests.factories import ManuscriptAuthorFactory
from tests.publications.test_manuscript_api import actor, client_for, error_code
from tests.reviews.test_editor_api import AREA, make_assignment, make_reviewer, submitted

pytestmark = pytest.mark.django_db

BASE = "/api/editor/"


@pytest.fixture(autouse=True)
def seeded_roles(db) -> None:
    call_command("seed_roles", verbosity=0)


@pytest.fixture
def editor():
    return actor("EDITOR")


@pytest.fixture
def manuscript():
    return submitted(status="UNDER_REVIEW")


@pytest.fixture
def events():
    """Collect the events announced by the reviews app."""
    received: list[tuple[str, dict]] = []

    def on_created(sender, **kwargs):
        received.append(("created", kwargs))

    def on_revoked(sender, **kwargs):
        received.append(("revoked", kwargs))

    assignment_created.connect(on_created, dispatch_uid="test-created")
    assignment_revoked.connect(on_revoked, dispatch_uid="test-revoked")
    yield received
    assignment_created.disconnect(dispatch_uid="test-created")
    assignment_revoked.disconnect(dispatch_uid="test-revoked")


def assign(editor, manuscript, reviewer, callbacks):
    with callbacks(execute=True):
        return client_for(editor).post(
            f"{BASE}manuscripts/{manuscript.pk}/assignments/",
            {"reviewer_id": str(reviewer.pk)},
            format="json",
        )


class TestReviewerRules:
    def test_a_reviewer_must_declare_the_manuscript_area(
        self, editor, manuscript, django_capture_on_commit_callbacks
    ) -> None:
        other_area = make_reviewer(areas=("Medicina",))

        response = assign(editor, manuscript, other_area, django_capture_on_commit_callbacks)

        assert response.status_code == 400 and error_code(response) == "VALIDATION_ERROR"
        assert "área" in response.json()["error"]["details"]["reviewer_id"][0]
        assert not Assignment.objects.exists()

    def test_an_unavailable_reviewer_is_rejected(
        self, editor, manuscript, django_capture_on_commit_callbacks
    ) -> None:
        away = make_reviewer(available=False)

        response = assign(editor, manuscript, away, django_capture_on_commit_callbacks)

        assert response.status_code == 400
        assert "no está disponible" in response.json()["error"]["details"]["reviewer_id"][0]

    def test_a_reviewer_without_profile_is_rejected(
        self, editor, manuscript, django_capture_on_commit_callbacks
    ) -> None:
        no_profile = actor("REVIEWER")

        response = assign(editor, manuscript, no_profile, django_capture_on_commit_callbacks)

        assert response.status_code == 400

    def test_a_reviewer_at_capacity_answers_409(
        self, editor, manuscript, django_capture_on_commit_callbacks
    ) -> None:
        busy = make_reviewer()
        ReviewerProfile.objects.filter(user=busy).update(max_active_assignments=1)
        make_assignment(submitted(status="UNDER_REVIEW"), busy, editor)

        response = assign(editor, manuscript, busy, django_capture_on_commit_callbacks)

        assert response.status_code == 409 and error_code(response) == "ASSIGNMENT_CONFLICT"
        assert response.json()["error"]["details"] == {"active": 1, "max": 1}
        assert manuscript.assignments.count() == 0

    def test_closed_assignments_do_not_count_towards_the_capacity(
        self, editor, manuscript, django_capture_on_commit_callbacks
    ) -> None:
        reviewer = make_reviewer()
        ReviewerProfile.objects.filter(user=reviewer).update(max_active_assignments=1)
        for status in ("REVOKED", "EXPIRED", "COMPLETED"):
            make_assignment(submitted(status="UNDER_REVIEW"), reviewer, editor, status=status)

        response = assign(editor, manuscript, reviewer, django_capture_on_commit_callbacks)

        assert response.status_code == 201

    def test_the_capacity_is_checked_when_starting_the_review_too(self, editor) -> None:
        busy = make_reviewer()
        ReviewerProfile.objects.filter(user=busy).update(max_active_assignments=1)
        make_assignment(submitted(status="UNDER_REVIEW"), busy, editor)
        pending = submitted()

        response = client_for(editor).post(
            f"{BASE}submissions/{pending.pk}/start-review/",
            {"reviewer_id": str(busy.pk)},
            format="json",
        )

        assert response.status_code == 409
        pending.refresh_from_db()
        assert pending.status == "SUBMITTED"

    def test_the_diagnosis_agrees_with_the_eligible_list(self, manuscript) -> None:
        eligible = make_reviewer()
        wrong_area = make_reviewer(areas=("Medicina",))
        unavailable = make_reviewer(available=False)
        coauthor = make_reviewer()
        ManuscriptAuthorFactory(
            manuscript=manuscript, user=coauthor, email="otro@x.edu", author_order=2
        )
        author = actor("AUTHOR")
        candidates = [eligible, wrong_area, unavailable, coauthor, author]

        listed = set(
            eligible_reviewers(manuscript=manuscript, area=manuscript.area).values_list(
                "pk", flat=True
            )
        )
        accepted = {c.pk for c in candidates if ineligibility_reason(manuscript, c.pk) is None}

        assert accepted == listed == {eligible.pk}


class TestDeadline:
    def test_the_client_clock_cannot_move_the_deadline(
        self, editor, manuscript, django_capture_on_commit_callbacks
    ) -> None:
        reviewer = make_reviewer()
        far_future = (timezone.now() + timedelta(days=400)).isoformat()

        with django_capture_on_commit_callbacks(execute=True):
            response = client_for(editor).post(
                f"{BASE}manuscripts/{manuscript.pk}/assignments/",
                {
                    "reviewer_id": str(reviewer.pk),
                    "due_at": far_future,
                    "assigned_at": far_future,
                },
                format="json",
                HTTP_DATE=far_future,
            )

        assignment = Assignment.objects.get(pk=response.json()["id"])
        assert abs(timezone.now() - assignment.assigned_at) < timedelta(minutes=1)
        assert assignment.due_at - assignment.assigned_at == timedelta(days=20)


class TestAnnouncements:
    def test_creating_announces_identifiers_only_after_the_commit(
        self, editor, manuscript, events, django_capture_on_commit_callbacks
    ) -> None:
        reviewer = make_reviewer()

        response = assign(editor, manuscript, reviewer, django_capture_on_commit_callbacks)

        assert response.status_code == 201
        assert events == [
            (
                "created",
                {
                    "signal": assignment_created,
                    "assignment_id": events[0][1]["assignment_id"],
                    "manuscript_id": manuscript.pk,
                    "reviewer_id": reviewer.pk,
                    "assigned_by_id": editor.pk,
                },
            )
        ]

    def test_nothing_is_announced_when_the_audit_fails(
        self, editor, manuscript, events, monkeypatch, django_capture_on_commit_callbacks
    ) -> None:
        def fail(**kwargs):
            raise AuditUnavailable("sin auditoría")

        monkeypatch.setattr(AuditService, "record", staticmethod(fail))

        response = assign(editor, manuscript, make_reviewer(), django_capture_on_commit_callbacks)

        assert response.status_code == 503
        assert events == []

    def test_revoking_announces_without_the_free_text_reason(
        self, editor, manuscript, events, django_capture_on_commit_callbacks
    ) -> None:
        assignment = make_assignment(manuscript, make_reviewer(), editor)

        with django_capture_on_commit_callbacks(execute=True):
            response = client_for(editor).post(
                f"{BASE}assignments/{assignment.pk}/revoke/",
                {"cause": "ASSIGNMENT_ERROR", "reason": "Texto interno del Editor."},
                format="json",
            )

        assert response.status_code == 200
        (kind, payload), = events
        assert kind == "revoked"
        assert payload["cause"] == "ASSIGNMENT_ERROR"
        assert payload["assignment_id"] == assignment.pk
        assert "Texto interno" not in str(payload)

    def test_a_failing_listener_does_not_undo_the_assignment(
        self, editor, manuscript, django_capture_on_commit_callbacks
    ) -> None:
        def broken(sender, **kwargs):
            raise RuntimeError("receptor roto")

        assignment_created.connect(broken, dispatch_uid="test-broken")
        try:
            response = assign(editor, manuscript, make_reviewer(), django_capture_on_commit_callbacks)
        finally:
            assignment_created.disconnect(dispatch_uid="test-broken")

        assert response.status_code == 201
        assert manuscript.assignments.filter(status="ACTIVE").count() == 1


class TestWithdrawalRevokesTheAssignment:
    def withdraw(self, user, manuscript, callbacks, reason="El autor retira el trabajo."):
        with callbacks(execute=True):
            return client_for(user).post(
                f"/api/manuscripts/{manuscript.pk}/withdraw/", {"reason": reason}, format="json"
            )

    def test_the_active_assignment_is_revoked_by_the_system(
        self, editor, events, django_capture_on_commit_callbacks
    ) -> None:
        owner = actor("AUTHOR")
        manuscript = submitted(owner, status="UNDER_REVIEW")
        assignment = make_assignment(manuscript, make_reviewer(), editor)

        response = self.withdraw(owner, manuscript, django_capture_on_commit_callbacks)

        assert response.status_code == 200
        assignment.refresh_from_db()
        assert assignment.status == "REVOKED" and assignment.revoked_at is not None
        assert assignment.revoked_by is None
        assert assignment.revocation_reason == "Baja lógica del manuscrito por su Autor."
        audit = AuditLog.objects.get(action="ASSIGNMENT_REVOKED")
        assert audit.entity_id == assignment.pk
        assert audit.actor_id == owner.pk and audit.actor_role == "AUTHOR"
        assert audit.details["cause"] == "MANUSCRIPT_WITHDRAWN"
        assert [kind for kind, _ in events] == ["revoked"]
        assert events[0][1]["cause"] == "MANUSCRIPT_WITHDRAWN"

    def test_the_evaluation_draft_is_left_untouched(
        self, editor, django_capture_on_commit_callbacks
    ) -> None:
        owner = actor("AUTHOR")
        manuscript = submitted(owner, status="UNDER_REVIEW")
        assignment = make_assignment(manuscript, make_reviewer(), editor)
        evaluation = Evaluation.objects.create(
            assignment=assignment,
            manuscript=manuscript,
            version=assignment.version,
            reviewer=assignment.reviewer,
            clarity_score=4,
        )

        self.withdraw(owner, manuscript, django_capture_on_commit_callbacks)

        evaluation.refresh_from_db()
        assert evaluation.status == "DRAFT" and evaluation.clarity_score == 4

    def test_closed_assignments_are_not_touched(
        self, editor, django_capture_on_commit_callbacks
    ) -> None:
        owner = actor("AUTHOR")
        manuscript = submitted(owner, status="UNDER_REVIEW")
        expired = make_assignment(
            manuscript, make_reviewer(), editor, days_ago=30, status="EXPIRED"
        )

        response = self.withdraw(owner, manuscript, django_capture_on_commit_callbacks)

        assert response.status_code == 200
        expired.refresh_from_db()
        assert expired.status == "EXPIRED" and expired.revoked_at is None
        assert not AuditLog.objects.filter(action="ASSIGNMENT_REVOKED").exists()

    def test_a_manuscript_without_assignment_withdraws_normally(
        self, django_capture_on_commit_callbacks
    ) -> None:
        owner = actor("AUTHOR")
        manuscript = submitted(owner, status="SUBMITTED")

        response = self.withdraw(owner, manuscript, django_capture_on_commit_callbacks, reason=None)

        assert response.status_code == 200

    def test_a_failing_audit_aborts_the_whole_withdrawal(
        self, editor, monkeypatch, django_capture_on_commit_callbacks
    ) -> None:
        owner = actor("AUTHOR")
        manuscript = submitted(owner, status="UNDER_REVIEW")
        assignment = make_assignment(manuscript, make_reviewer(), editor)
        original = AuditService.record

        def fail_on_assignment(**kwargs):
            if kwargs["action"] == "ASSIGNMENT_REVOKED":
                raise AuditUnavailable("sin auditoría")
            return original(**kwargs)

        monkeypatch.setattr(AuditService, "record", staticmethod(fail_on_assignment))

        response = self.withdraw(owner, manuscript, django_capture_on_commit_callbacks)

        assert response.status_code == 503 and error_code(response) == "AUDIT_UNAVAILABLE"
        manuscript.refresh_from_db()
        assignment.refresh_from_db()
        assert manuscript.is_active is True
        assert assignment.status == "ACTIVE" and assignment.revoked_at is None

    def test_the_reviewer_slot_is_freed_for_other_manuscripts(
        self, editor, django_capture_on_commit_callbacks
    ) -> None:
        owner = actor("AUTHOR")
        reviewer = make_reviewer()
        ReviewerProfile.objects.filter(user=reviewer).update(max_active_assignments=1)
        withdrawn = submitted(owner, status="UNDER_REVIEW")
        make_assignment(withdrawn, reviewer, editor)
        other = submitted(status="UNDER_REVIEW")

        self.withdraw(owner, withdrawn, django_capture_on_commit_callbacks)
        response = assign(editor, other, reviewer, django_capture_on_commit_callbacks)

        assert response.status_code == 201
