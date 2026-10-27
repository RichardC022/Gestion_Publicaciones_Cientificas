"""The reviews factories build rows that satisfy every database constraint (TSK-53)."""

from __future__ import annotations

from datetime import timedelta

import pytest

from apps.publications.models import Verdict
from apps.reviews.models import Evaluation
from tests.factories import (
    AssignmentFactory,
    CatalogEntryFactory,
    EvaluationFactory,
    FinalEvaluationFactory,
    ReviewerProfileFactory,
    VerdictFactory,
)

pytestmark = pytest.mark.django_db


def test_an_assignment_has_the_exact_deadline_and_a_version_of_its_manuscript() -> None:
    assignment = AssignmentFactory()

    assert assignment.status == "ACTIVE"
    assert assignment.due_at - assignment.assigned_at == timedelta(days=20)
    assert assignment.version.manuscript_id == assignment.manuscript_id
    assert assignment.manuscript.status == "UNDER_REVIEW"


def test_a_draft_evaluation_follows_its_assignment() -> None:
    evaluation = EvaluationFactory()

    assert evaluation.status == Evaluation.Status.DRAFT
    assert evaluation.manuscript == evaluation.assignment.manuscript
    assert evaluation.version == evaluation.assignment.version
    assert evaluation.reviewer == evaluation.assignment.reviewer


def test_a_final_evaluation_is_complete() -> None:
    evaluation = FinalEvaluationFactory()

    assert evaluation.status == Evaluation.Status.FINAL
    assert evaluation.submitted_at is not None and evaluation.comments_for_author


def test_a_verdict_hangs_from_its_final_evaluation() -> None:
    verdict = VerdictFactory()

    assert verdict.decision == Verdict.Decision.ACCEPTED
    assert verdict.manuscript == verdict.evaluation.manuscript
    assert verdict.version == verdict.evaluation.version
    assert verdict.previous_verdict is None


def test_a_catalog_entry_is_active_and_relative_to_the_catalog() -> None:
    entry = CatalogEntryFactory()

    assert entry.is_active and entry.unpublished_at is None
    assert entry.public_file_path == f"{entry.manuscript_id}/{entry.version_id}.pdf"


def test_a_reviewer_profile_has_the_default_capacity() -> None:
    profile = ReviewerProfileFactory()

    assert profile.is_available and profile.max_active_assignments == 3
    assert profile.expertise_areas == ["Agronomía"]
