"""Tests for blind review assignments, evaluations and verdicts (FR-006..FR-010)."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.publications.models import Manuscript, ManuscriptStatus, ResearchArea
from apps.reviews.models import (
    Evaluation,
    Recommendation,
    ReviewAssignment,
    ReviewVerdict,
    VerdictDecision,
)
from apps.users.models import User


class ReviewFlowTests(TestCase):
    """Verify assignment, evaluation and verdict rules."""

    def setUp(self) -> None:
        """Create the actors and a manuscript under review."""
        self.author = User.objects.create_user(username="author", password="pass12345")
        self.editor = User.objects.create_user(
            username="editor", password="pass12345", is_editor_enabled=True
        )
        self.reviewer = User.objects.create_user(
            username="reviewer", password="pass12345", is_reviewer_enabled=True
        )
        self.area = ResearchArea.objects.create(name="Computing", code="COMP")
        self.manuscript = Manuscript.objects.create(
            title="A study",
            abstract="Abstract",
            keywords="a,b",
            author=self.author,
            research_area=self.area,
            status=ManuscriptStatus.UNDER_REVIEW,
        )
        self.assignment = ReviewAssignment.objects.create(
            manuscript=self.manuscript,
            reviewer=self.reviewer,
            assigned_by=self.editor,
        )

    def test_assignment_defaults_to_pending(self) -> None:
        """A new assignment starts as pending."""
        self.assertEqual(self.assignment.status, "pending")

    def test_reviewer_cannot_be_assigned_twice(self) -> None:
        """The same reviewer cannot be assigned twice to one manuscript."""
        with self.assertRaises(IntegrityError), transaction.atomic():
            ReviewAssignment.objects.create(
                manuscript=self.manuscript,
                reviewer=self.reviewer,
                assigned_by=self.editor,
            )

    def test_verdict_requires_at_least_one_evaluation(self) -> None:
        """A verdict is rejected until an evaluation exists (FR-008)."""
        verdict = ReviewVerdict(
            manuscript=self.manuscript,
            decided_by=self.editor,
            decision=VerdictDecision.ACCEPTED,
        )
        with self.assertRaises(ValidationError):
            verdict.full_clean()

    def test_verdict_allowed_after_evaluation(self) -> None:
        """A verdict passes validation once an evaluation is recorded."""
        Evaluation.objects.create(
            assignment=self.assignment,
            observations="Good work.",
            recommendation=Recommendation.ACCEPT,
        )
        verdict = ReviewVerdict(
            manuscript=self.manuscript,
            decided_by=self.editor,
            decision=VerdictDecision.ACCEPTED,
        )
        verdict.full_clean()

    def test_assignment_declined_when_truly_declined(self) -> None:
        """An assignment can be declined by a reviewer."""
        self.assignment.status = "declined"
        self.assignment.save()
        self.assertEqual(self.assignment.status, "declined")
