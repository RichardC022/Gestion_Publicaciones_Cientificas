"""Real concurrency on assignments and their expiration (TSK-53).

Requests and service calls run in parallel threads, each with its own
database connection, released together by a barrier. They check the
guarantees the row locks, the partial unique index and the audit chain
give, whatever the order the threads happen to take:

* two editors assigning at once leave a single ``ACTIVE`` assignment;
* the load limit of a reviewer holds across manuscripts;
* two starts of the same review move the manuscript once;
* revoking and expiring the same assignment never double-closes it;
* a withdrawal racing an assignment leaves no active assignment behind.
"""

from __future__ import annotations

import pytest
from django.core.management import call_command

from apps.audit.models import AuditLog
from apps.publications.models import Manuscript
from apps.reviews.models import Assignment
from apps.reviews.services.expiration import mark_expired_assignments
from tests.factories import ReviewerProfileFactory, UserRoleFactory
from tests.parallel import api_task, run_parallel, statuses
from tests.publications.test_lifecycle import assert_audit_chain_intact
from tests.publications.test_manuscript_api import actor, error_code
from tests.reviews.test_editor_api import make_assignment, submitted

pytestmark = pytest.mark.django_db(transaction=True)

BASE = "/api/editor/"


@pytest.fixture(autouse=True)
def seeded_roles(db) -> None:
    call_command("seed_roles", verbosity=0)


def reviewer(*, capacity: int = 3):
    """Eligible reviewer for the area of ``submitted()`` manuscripts."""
    profile = ReviewerProfileFactory(max_active_assignments=capacity)
    UserRoleFactory(user=profile.user, role_code="REVIEWER")
    return profile.user


def assign(editor, manuscript, target):
    return api_task(
        editor,
        lambda client: client.post(
            f"{BASE}manuscripts/{manuscript.pk}/assignments/",
            {"reviewer_id": str(target.pk)},
            format="json",
        ),
    )


class TestSimultaneousAssignments:
    def test_two_editors_leave_a_single_active_assignment(self) -> None:
        manuscript = submitted(status="UNDER_REVIEW")
        first, second = actor("EDITOR"), actor("EDITOR")

        responses = run_parallel(
            [assign(first, manuscript, reviewer()), assign(second, manuscript, reviewer())]
        )

        assert statuses(responses) == [201, 409]
        loser = next(r for r in responses if r.status_code == 409)
        assert error_code(loser) == "ASSIGNMENT_CONFLICT"
        assert Assignment.objects.filter(manuscript=manuscript, status="ACTIVE").count() == 1
        assert AuditLog.objects.filter(action="ASSIGNMENT_CREATED").count() == 1
        assert_audit_chain_intact()

    def test_the_same_editor_double_clicking_creates_one_assignment(self) -> None:
        manuscript = submitted(status="UNDER_REVIEW")
        editor, target = actor("EDITOR"), reviewer()

        responses = run_parallel([assign(editor, manuscript, target)] * 2)

        assert statuses(responses) == [201, 409]
        assert manuscript.assignments.count() == 1

    def test_the_capacity_of_a_reviewer_holds_across_manuscripts(self) -> None:
        editor = actor("EDITOR")
        busy = reviewer(capacity=1)
        first, second = submitted(status="UNDER_REVIEW"), submitted(status="UNDER_REVIEW")

        responses = run_parallel([assign(editor, first, busy), assign(editor, second, busy)])

        assert statuses(responses) == [201, 409]
        loser = next(r for r in responses if r.status_code == 409)
        assert error_code(loser) == "ASSIGNMENT_CONFLICT"
        assert loser.json()["error"]["details"] == {"active": 1, "max": 1}
        assert Assignment.objects.filter(reviewer=busy, status="ACTIVE").count() == 1

    def test_two_starts_of_the_same_review_move_the_manuscript_once(self) -> None:
        editor = actor("EDITOR")
        manuscript = submitted(status="SUBMITTED")

        def start(client):
            return client.post(
                f"{BASE}submissions/{manuscript.pk}/start-review/", {}, format="json"
            )

        responses = run_parallel([api_task(editor, start)] * 2)

        assert statuses(responses) == [200, 409]
        loser = next(r for r in responses if r.status_code == 409)
        assert error_code(loser) == "STATE_CONFLICT"
        manuscript.refresh_from_db()
        assert manuscript.status == "UNDER_REVIEW" and manuscript.lock_version == 1
        assert manuscript.status_events.count() == 1
        assert AuditLog.objects.filter(action="REVIEW_STARTED").count() == 1


class TestRevocationAndExpiration:
    def test_revoking_while_the_task_expires_closes_the_assignment_once(self) -> None:
        editor = actor("EDITOR")
        late = make_assignment(
            submitted(status="UNDER_REVIEW"), reviewer(), editor, days_ago=21
        )

        revoke = api_task(
            editor,
            lambda client: client.post(
                f"{BASE}assignments/{late.pk}/revoke/",
                {"cause": "OVERDUE", "reason": "Sin respuesta."},
                format="json",
            ),
        )
        revoked, expired = run_parallel([revoke, mark_expired_assignments])

        # Gane quien gane el bloqueo, el Editor decide: queda revocada una vez.
        assert revoked.status_code == 200
        late.refresh_from_db()
        assert late.status == "REVOKED" and late.revoked_by == editor
        assert AuditLog.objects.filter(action="ASSIGNMENT_REVOKED").count() == 1
        assert AuditLog.objects.filter(action="ASSIGNMENT_EXPIRED").count() == expired.expired
        assert expired.failed == 0 and expired.expired in (0, 1)
        assert_audit_chain_intact()

    def test_two_runs_of_the_task_expire_it_once(self) -> None:
        editor = actor("EDITOR")
        late = make_assignment(
            submitted(status="UNDER_REVIEW"), reviewer(), editor, days_ago=25
        )

        first, second = run_parallel([mark_expired_assignments, mark_expired_assignments])

        assert first.expired + second.expired == 1
        late.refresh_from_db()
        assert late.status == "EXPIRED" and late.lock_version == 1
        assert AuditLog.objects.filter(action="ASSIGNMENT_EXPIRED").count() == 1
        assert_audit_chain_intact()


class TestWithdrawalRacingAnAssignment:
    def test_no_active_assignment_survives_the_withdrawal(self) -> None:
        owner, editor = actor("AUTHOR"), actor("EDITOR")
        manuscript = submitted(owner, status="UNDER_REVIEW")

        withdraw = api_task(
            owner,
            lambda client: client.post(
                f"/api/manuscripts/{manuscript.pk}/withdraw/",
                {"reason": "El autor retira el trabajo."},
                format="json",
            ),
        )
        withdrawn, assigned = run_parallel([withdraw, assign(editor, manuscript, reviewer())])

        assert withdrawn.status_code == 200
        assert assigned.status_code in (201, 409)
        assert Manuscript.objects.get(pk=manuscript.pk).is_active is False
        assert not Assignment.objects.filter(manuscript=manuscript, status="ACTIVE").exists()
        if assigned.status_code == 201:
            assert manuscript.assignments.get().status == "REVOKED"
        else:
            assert error_code(assigned) == "STATE_CONFLICT"
            assert not manuscript.assignments.exists()
        assert_audit_chain_intact()
