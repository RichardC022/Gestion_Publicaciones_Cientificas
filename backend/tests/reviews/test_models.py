"""Tests for the assignment and evaluation models (TSK-46).

Covers the acceptance criteria: only one ``ACTIVE`` assignment per
manuscript; ``due_at`` is exactly 20 days after ``assigned_at``, checked
by the database; a ``FINAL`` evaluation requires every score, the
recommendation, the comments and ``submitted_at``; and a trigger rejects
any change to a ``FINAL`` evaluation.

The constraints and the trigger are exercised with queryset operations
and raw SQL, so the database answers and not a guard of the models.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.db import IntegrityError, connection, transaction
from django.db.models import ProtectedError
from django.db.utils import DatabaseError
from django.utils import timezone

from apps.reviews.models import ASSIGNMENT_DAYS, SCORE_FIELDS, Assignment, Evaluation
from tests.factories import ManuscriptFactory, ManuscriptVersionFactory, UserFactory

COMPLETE_FINAL = {
    "status": Evaluation.Status.FINAL,
    "recommendation": Evaluation.Recommendation.ACCEPT,
    "comments_for_author": "Observaciones para el autor.",
    "originality_score": 4,
    "methodology_score": 4,
    "clarity_score": 3,
    "relevance_score": 5,
    "ethics_score": 5,
}


class Scenario:
    """A manuscript with one version, an editor and a reviewer."""

    def __init__(self) -> None:
        self.author = UserFactory()
        self.editor = UserFactory()
        self.reviewer = UserFactory()
        self.manuscript = ManuscriptFactory(created_by=self.author)
        self.version = ManuscriptVersionFactory(
            manuscript=self.manuscript, submitted_by=self.author
        )

    def assignment(self, **overrides) -> Assignment:
        """Create an assignment with a valid ``due_at`` unless overridden."""
        values = {
            "manuscript": self.manuscript,
            "version": self.version,
            "reviewer": self.reviewer,
            "assigned_by": self.editor,
            "assigned_at": timezone.now(),
        }
        values.update(overrides)
        values.setdefault("due_at", values["assigned_at"] + timedelta(days=ASSIGNMENT_DAYS))
        return Assignment.objects.create(**values)

    def evaluation(self, assignment: Assignment, **overrides) -> Evaluation:
        """Create an evaluation of the assignment (a ``DRAFT`` by default)."""
        values = {
            "assignment": assignment,
            "manuscript": assignment.manuscript,
            "version": assignment.version,
            "reviewer": assignment.reviewer,
        }
        values.update(overrides)
        return Evaluation.objects.create(**values)

    def final_evaluation(self, assignment: Assignment, **overrides) -> Evaluation:
        values = {**COMPLETE_FINAL, "submitted_at": timezone.now(), **overrides}
        return self.evaluation(assignment, **values)


@pytest.fixture
def scenario(db) -> Scenario:
    return Scenario()


@pytest.mark.django_db
class TestAssignmentDeadline:
    def test_due_at_exactly_twenty_days_after_assigned_at_is_accepted(self, scenario) -> None:
        assignment = scenario.assignment()

        assignment.refresh_from_db()
        assert assignment.due_at - assignment.assigned_at == timedelta(days=20)
        assert assignment.status == Assignment.Status.ACTIVE

    @pytest.mark.parametrize(
        "offset",
        [timedelta(seconds=1), timedelta(microseconds=1), timedelta(days=-1), timedelta(days=1)],
    )
    def test_any_other_deadline_is_rejected_by_the_database(self, scenario, offset) -> None:
        assigned_at = timezone.now()

        with pytest.raises(IntegrityError, match="ck_assignment_due_at"):
            with transaction.atomic():
                scenario.assignment(
                    assigned_at=assigned_at,
                    due_at=assigned_at + timedelta(days=20) + offset,
                )

    def test_postgresql_computes_the_same_deadline(self, scenario) -> None:
        """The service of TSK-48 calculates it in the database."""
        assigned_at = timezone.now()
        assignment = scenario.assignment(assigned_at=assigned_at)

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT assigned_at + interval '20 days' = due_at "
                "FROM reviews_assignment WHERE id = %s",
                [assignment.pk],
            )
            assert cursor.fetchone() == (True,)


@pytest.mark.django_db
class TestAssignmentStatus:
    def test_an_unknown_status_is_rejected(self, scenario) -> None:
        with pytest.raises(IntegrityError, match="ck_assignment_status"):
            with transaction.atomic():
                scenario.assignment(status="PENDING")

    def test_a_second_active_assignment_for_a_manuscript_is_rejected(self, scenario) -> None:
        scenario.assignment()

        with pytest.raises(IntegrityError, match="uq_assignment_active"):
            with transaction.atomic():
                scenario.assignment(reviewer=UserFactory())

    @pytest.mark.parametrize(
        "closed",
        [
            Assignment.Status.EXPIRED,
            Assignment.Status.REVOKED,
            Assignment.Status.COMPLETED,
        ],
    )
    def test_a_new_active_assignment_is_allowed_after_a_closed_one(self, scenario, closed) -> None:
        scenario.assignment(status=closed)

        replacement = scenario.assignment(reviewer=UserFactory())

        assert replacement.status == Assignment.Status.ACTIVE

    def test_several_closed_assignments_can_coexist(self, scenario) -> None:
        scenario.assignment(status=Assignment.Status.EXPIRED)
        scenario.assignment(status=Assignment.Status.REVOKED)

        assert scenario.manuscript.assignments.count() == 2

    def test_two_manuscripts_can_each_have_an_active_assignment(self, scenario) -> None:
        other = Scenario()
        scenario.assignment()

        other.assignment(reviewer=scenario.reviewer)

        assert Assignment.objects.filter(status=Assignment.Status.ACTIVE).count() == 2

    def test_revocation_data_is_optional_and_lock_version_starts_at_zero(self, scenario) -> None:
        assignment = scenario.assignment()

        assert assignment.revoked_at is None
        assert assignment.revoked_by is None
        assert assignment.revocation_reason is None
        assert assignment.lock_version == 0


@pytest.mark.django_db
class TestEvaluationScores:
    def test_a_draft_may_be_incomplete(self, scenario) -> None:
        evaluation = scenario.evaluation(scenario.assignment())

        assert evaluation.status == Evaluation.Status.DRAFT
        assert evaluation.originality_score is None
        assert evaluation.submitted_at is None
        assert evaluation.conflict_declared is False
        assert evaluation.lock_version == 0

    @pytest.mark.parametrize("score", [1, 5])
    def test_scores_at_the_bounds_are_accepted(self, scenario, score) -> None:
        evaluation = scenario.evaluation(
            scenario.assignment(), **{field: score for field in SCORE_FIELDS}
        )

        assert evaluation.clarity_score == score

    @pytest.mark.parametrize("field", SCORE_FIELDS)
    @pytest.mark.parametrize("score", [0, 6, -1])
    def test_scores_outside_one_to_five_are_rejected(self, scenario, field, score) -> None:
        assignment = scenario.assignment()

        with pytest.raises(IntegrityError, match=f"ck_evaluation_{field}"):
            with transaction.atomic():
                scenario.evaluation(assignment, **{field: score})

    def test_an_unknown_recommendation_is_rejected(self, scenario) -> None:
        with pytest.raises(IntegrityError, match="ck_evaluation_recommendation"):
            with transaction.atomic():
                scenario.evaluation(scenario.assignment(), recommendation="MAYBE")

    def test_an_unknown_status_is_rejected(self, scenario) -> None:
        # Con datos completos, solo `ck_evaluation_status` puede fallar.
        with pytest.raises(IntegrityError, match="ck_evaluation_status"):
            with transaction.atomic():
                scenario.final_evaluation(scenario.assignment(), status="SENT")


@pytest.mark.django_db
class TestFinalEvaluationRequirements:
    def test_a_complete_final_evaluation_is_accepted(self, scenario) -> None:
        evaluation = scenario.final_evaluation(scenario.assignment())

        assert evaluation.status == Evaluation.Status.FINAL
        assert evaluation.submitted_at is not None

    @pytest.mark.parametrize(
        "missing",
        [*SCORE_FIELDS, "recommendation", "comments_for_author", "submitted_at"],
    )
    def test_a_final_evaluation_without_a_required_field_is_rejected(
        self, scenario, missing
    ) -> None:
        assignment = scenario.assignment()

        with pytest.raises(IntegrityError, match="ck_evaluation_final_complete"):
            with transaction.atomic():
                scenario.final_evaluation(assignment, **{missing: None})

    def test_confidential_comments_are_not_required(self, scenario) -> None:
        evaluation = scenario.final_evaluation(
            scenario.assignment(), confidential_comments=None
        )

        assert evaluation.confidential_comments is None

    def test_a_draft_cannot_become_final_while_incomplete(self, scenario) -> None:
        evaluation = scenario.evaluation(scenario.assignment(), clarity_score=3)

        with pytest.raises(IntegrityError, match="ck_evaluation_final_complete"):
            with transaction.atomic():
                Evaluation.objects.filter(pk=evaluation.pk).update(status="FINAL")


@pytest.mark.django_db
class TestEvaluationUniqueness:
    def test_an_assignment_produces_a_single_evaluation(self, scenario) -> None:
        assignment = scenario.assignment()
        scenario.evaluation(assignment)

        with pytest.raises(IntegrityError, match="assignment_id"):
            with transaction.atomic():
                scenario.evaluation(assignment)

    def test_a_reviewer_has_one_evaluation_per_version(self, scenario) -> None:
        expired = scenario.assignment(status=Assignment.Status.EXPIRED)
        scenario.evaluation(expired)
        again = scenario.assignment()

        with pytest.raises(IntegrityError, match="uq_evaluation_version_reviewer"):
            with transaction.atomic():
                scenario.evaluation(again)

    def test_the_same_reviewer_may_evaluate_another_version(self, scenario) -> None:
        scenario.evaluation(scenario.assignment(status=Assignment.Status.COMPLETED))
        next_version = ManuscriptVersionFactory(
            manuscript=scenario.manuscript,
            submitted_by=scenario.author,
            version_number=2,
            round_number=1,
        )

        second = scenario.evaluation(scenario.assignment(version=next_version))

        assert second.version_id == next_version.pk


@pytest.mark.django_db
class TestFinalEvaluationImmutability:
    def test_update_over_a_final_evaluation_fails_in_the_database(self, scenario) -> None:
        evaluation = scenario.final_evaluation(scenario.assignment())

        with pytest.raises(DatabaseError, match="evaluación final es inmutable"):
            with transaction.atomic():
                Evaluation.objects.filter(pk=evaluation.pk).update(clarity_score=1)

        evaluation.refresh_from_db()
        assert evaluation.clarity_score == 3

    def test_raw_update_over_a_final_evaluation_also_fails(self, scenario) -> None:
        evaluation = scenario.final_evaluation(scenario.assignment())

        with pytest.raises(DatabaseError, match="evaluación final es inmutable"):
            with transaction.atomic(), connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE reviews_evaluation SET comments_for_author = 'x' WHERE id = %s",
                    [evaluation.pk],
                )

    def test_a_final_evaluation_cannot_go_back_to_draft(self, scenario) -> None:
        evaluation = scenario.final_evaluation(scenario.assignment())

        with pytest.raises(DatabaseError, match="evaluación final es inmutable"):
            with transaction.atomic():
                Evaluation.objects.filter(pk=evaluation.pk).update(status="DRAFT")

    def test_delete_over_a_final_evaluation_fails_in_the_database(self, scenario) -> None:
        evaluation = scenario.final_evaluation(scenario.assignment())

        with pytest.raises(DatabaseError, match="evaluación final es inmutable"):
            with transaction.atomic():
                Evaluation.objects.filter(pk=evaluation.pk).delete()

        assert Evaluation.objects.filter(pk=evaluation.pk).exists()

    def test_a_draft_can_be_edited_and_become_final(self, scenario) -> None:
        evaluation = scenario.evaluation(scenario.assignment())

        Evaluation.objects.filter(pk=evaluation.pk).update(clarity_score=2)
        Evaluation.objects.filter(pk=evaluation.pk).update(
            **{**COMPLETE_FINAL, "submitted_at": timezone.now()}
        )

        evaluation.refresh_from_db()
        assert evaluation.status == Evaluation.Status.FINAL
        assert evaluation.clarity_score == 3

    def test_a_draft_can_be_deleted_and_the_row_really_disappears(self, scenario) -> None:
        evaluation = scenario.evaluation(scenario.assignment())

        deleted, _ = Evaluation.objects.filter(pk=evaluation.pk).delete()

        assert deleted == 1
        assert not Evaluation.objects.filter(pk=evaluation.pk).exists()


@pytest.mark.django_db
class TestReferentialProtection:
    def test_an_assignment_with_an_evaluation_cannot_be_deleted(self, scenario) -> None:
        assignment = scenario.assignment()
        scenario.evaluation(assignment)

        with pytest.raises(ProtectedError):
            assignment.delete()

    def test_a_reviewer_with_assignments_cannot_be_deleted(self, scenario) -> None:
        scenario.assignment()

        with pytest.raises(ProtectedError):
            scenario.reviewer.delete()

    def test_the_evaluation_is_reachable_from_its_assignment(self, scenario) -> None:
        assignment = scenario.assignment()
        evaluation = scenario.evaluation(assignment)

        assert assignment.evaluation == evaluation
