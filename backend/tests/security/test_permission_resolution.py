"""``IsAssignedReviewer`` over real evaluations (TSK-89, closes D-20).

An evaluation carries its own ``reviewer_id`` and a ``DRAFT``/``FINAL`` status.
The permission must judge the *assignment* behind it, not read those two fields
as if they were the assignment's.
"""

from __future__ import annotations

import pytest

from apps.reviews.permissions import IsAssignedReviewer, resolve_assignment
from tests.factories import AssignmentFactory, EvaluationFactory
from tests.users.test_permissions import assign_roles, call, make_user, object_view
from rest_framework.permissions import IsAuthenticated

from apps.users.permissions import IsReviewer

pytestmark = pytest.mark.django_db


def probe(evaluation, user):
    view = object_view(IsAuthenticated, IsReviewer, IsAssignedReviewer)
    return call(view(evaluation), user=user).status_code


class TestEvaluationsAreJudgedByTheirAssignment:
    def test_the_assignment_is_found_through_the_evaluation(self) -> None:
        evaluation = EvaluationFactory()

        assert resolve_assignment(evaluation) == evaluation.assignment
        assert resolve_assignment(evaluation.assignment) == evaluation.assignment

    def test_the_reviewer_of_an_active_assignment_reaches_their_draft(self) -> None:
        reviewer = assign_roles(make_user(), "REVIEWER")
        evaluation = EvaluationFactory(assignment=AssignmentFactory(reviewer=reviewer))

        assert probe(evaluation, reviewer) == 200

    @pytest.mark.parametrize("status", ["REVOKED", "EXPIRED"])
    def test_a_closed_assignment_hides_the_evaluation(self, status) -> None:
        reviewer = assign_roles(make_user(), "REVIEWER")
        evaluation = EvaluationFactory(assignment=AssignmentFactory(reviewer=reviewer, status=status))

        assert probe(evaluation, reviewer) == 404

    def test_another_reviewer_gets_a_404(self) -> None:
        reviewer = assign_roles(make_user(), "REVIEWER")
        other = assign_roles(
            make_user(username="b.otro", institutional_id="INST-1002", email="b.otro@unl.edu.ec"), "REVIEWER"
        )
        evaluation = EvaluationFactory(assignment=AssignmentFactory(reviewer=reviewer))

        assert probe(evaluation, other) == 404

    def test_an_object_that_is_neither_is_not_an_assignment(self) -> None:
        assert resolve_assignment(object()) is None
        assert resolve_assignment(None) is None
