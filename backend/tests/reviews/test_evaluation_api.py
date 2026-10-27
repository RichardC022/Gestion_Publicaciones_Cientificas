"""Tests for the reviewer's draft and final evaluation endpoints (TSK-62).

Covers the acceptance criteria: the draft is private and only the owner
of an ``ACTIVE`` assignment edits it; at ``now() == due_at`` or later the
submission answers ``410`` and keeps the draft without making it final;
and a ``FINAL`` evaluation admits no later ``PUT``.

Plus the contracts of the plan: ``If-Match``/``ETag`` over ``lock_version``,
scores 1 to 5, the exact cut by the database clock, the completion of the
assignment, the audit (``503`` when unavailable) and the event for the
editor. The exact cut is tested with the service clock frozen at the
boundary, because the database clock keeps moving inside a test.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.core.management import call_command
from django.db.models import DateTimeField, Value
from django.utils import timezone
from rest_framework.test import APIClient

from apps.audit.models import AuditLog
from apps.audit.services import AuditService, AuditUnavailable
from apps.publications.models import Manuscript, Verdict
from apps.reviews.models import Assignment, Evaluation
from apps.reviews.services import evaluations
from apps.reviews.signals import evaluation_submitted
from tests.factories import (
    AssignmentFactory,
    EvaluationFactory,
    ManuscriptAuthorFactory,
    UserFactory,
)
from tests.publications.test_manuscript_api import actor, client_for, error_code

pytestmark = pytest.mark.django_db

BASE = "/api/reviewer/assignments/"
FULL = {
    "originality_score": 4,
    "methodology_score": 3,
    "clarity_score": 5,
    "relevance_score": 4,
    "ethics_score": 5,
    "recommendation": "ACCEPT",
    "comments_for_author": "Buen trabajo, con matices menores.",
    "confidential_comments": "Nota solo para el editor.",
}


@pytest.fixture(autouse=True)
def seeded_roles(db) -> None:
    call_command("seed_roles", verbosity=0)


@pytest.fixture
def reviewer():
    return actor("REVIEWER")


@pytest.fixture
def assignment(reviewer) -> Assignment:
    return AssignmentFactory(reviewer=reviewer)


def url(assignment, suffix: str = "") -> str:
    return f"{BASE}{assignment.pk}/evaluation/{suffix}"


def put(user, assignment, body: dict, *, lock: int | str | None = 0):
    headers = {} if lock is None else {"HTTP_IF_MATCH": f'"{lock}"'}
    return client_for(user).put(url(assignment), body, format="json", **headers)


def submit(user, assignment, *, lock: int | str | None, capture=None):
    headers = {} if lock is None else {"HTTP_IF_MATCH": f'"{lock}"'}
    if capture is None:
        return client_for(user).post(url(assignment, "submit/"), **headers)
    with capture(execute=True):
        return client_for(user).post(url(assignment, "submit/"), **headers)


def draft_of(assignment) -> Evaluation:
    return Evaluation.objects.get(assignment=assignment)


def complete_draft(assignment, **overrides) -> Evaluation:
    """A complete ``DRAFT`` at ``lock_version`` 1, as a first ``PUT`` leaves it."""
    return EvaluationFactory(assignment=assignment, lock_version=1, **{**FULL, **overrides})


def set_deadline(assignment, offset: timedelta):
    """Put ``due_at`` at now plus ``offset`` (keeping the 20-day rule) and return it."""
    due_at = timezone.now() + offset
    Assignment.objects.filter(pk=assignment.pk).update(
        due_at=due_at, assigned_at=due_at - timedelta(days=20)
    )
    return due_at


def freeze_clock(monkeypatch, instant) -> None:
    """Make the service's database clock read ``instant``."""
    monkeypatch.setattr(
        evaluations, "Now", lambda: Value(instant, output_field=DateTimeField())
    )


def set_status(assignment, status: str) -> None:
    Assignment.objects.filter(pk=assignment.pk).update(status=status)


class TestAccess:
    @pytest.mark.parametrize("method", ["get", "put", "post"])
    def test_anonymous_requests_answer_401(self, assignment, method) -> None:
        suffix = "submit/" if method == "post" else ""

        response = getattr(APIClient(), method)(url(assignment, suffix))

        assert response.status_code == 401

    @pytest.mark.parametrize("role", ["AUTHOR", "EDITOR", "ADMIN"])
    @pytest.mark.parametrize("method", ["get", "put", "post"])
    def test_other_roles_answer_403(self, assignment, role, method) -> None:
        suffix = "submit/" if method == "post" else ""

        response = getattr(client_for(actor(role)), method)(url(assignment, suffix))

        assert response.status_code == 403

    @pytest.mark.parametrize("method", ["get", "put", "post"])
    def test_a_foreign_assignment_answers_404_even_without_a_header(
        self, assignment, method
    ) -> None:
        other = actor("REVIEWER")
        suffix = "submit/" if method == "post" else ""

        response = getattr(client_for(other), method)(url(assignment, suffix))

        assert response.status_code == 404 and error_code(response) == "NOT_FOUND"

    @pytest.mark.parametrize("method", ["get", "put", "post"])
    def test_a_coauthored_manuscript_cannot_be_evaluated(
        self, reviewer, assignment, method
    ) -> None:
        ManuscriptAuthorFactory(manuscript=assignment.manuscript, user=reviewer, author_order=2)
        suffix = "submit/" if method == "post" else ""

        response = getattr(client_for(reviewer), method)(
            url(assignment, suffix), HTTP_IF_MATCH='"0"'
        )

        assert response.status_code == 404
        assert not Evaluation.objects.filter(assignment=assignment).exists()

    def test_the_methods_are_restricted(self, reviewer, assignment) -> None:
        client = client_for(reviewer)

        assert client.post(url(assignment), {}, format="json").status_code == 405
        assert client.delete(url(assignment)).status_code == 405
        assert client.get(url(assignment, "submit/")).status_code == 405
        assert client.put(url(assignment, "submit/"), {}, format="json").status_code == 405


class TestRead:
    def test_before_the_first_save_it_is_an_empty_draft_with_etag_zero(
        self, reviewer, assignment
    ) -> None:
        response = client_for(reviewer).get(url(assignment))

        assert response.status_code == 200
        body = response.json()
        assert response["ETag"] == '"0"'
        assert body["id"] is None and body["status"] == "DRAFT"
        assert body["recommendation"] is None and body["originality_score"] is None
        assert body["conflict_declared"] is False
        assert not Evaluation.objects.filter(assignment=assignment).exists()

    def test_returns_the_saved_draft_with_its_lock(self, reviewer, assignment) -> None:
        complete_draft(assignment)

        response = client_for(reviewer).get(url(assignment))

        assert response["ETag"] == '"1"'
        assert response.json()["comments_for_author"] == FULL["comments_for_author"]
        assert response.json()["confidential_comments"] == FULL["confidential_comments"]

    def test_the_body_is_an_allowlist_without_identity(self, reviewer, assignment) -> None:
        complete_draft(assignment)

        body = client_for(reviewer).get(url(assignment)).json()

        assert set(body) == {
            "id", "status", "originality_score", "methodology_score", "clarity_score",
            "relevance_score", "ethics_score", "recommendation", "comments_for_author",
            "confidential_comments", "conflict_declared", "submitted_at",
        }

    def test_a_completed_assignment_shows_the_final_evaluation(self, reviewer, assignment) -> None:
        complete_draft(assignment)
        assert submit(reviewer, assignment, lock=1).status_code == 200

        body = client_for(reviewer).get(url(assignment)).json()

        assert body["status"] == "FINAL" and body["submitted_at"]

    @pytest.mark.parametrize("status", ["REVOKED", "EXPIRED"])
    def test_a_closed_assignment_answers_404(self, reviewer, assignment, status) -> None:
        set_status(assignment, status)

        assert client_for(reviewer).get(url(assignment)).status_code == 404

    def test_the_draft_is_private_to_the_reviewer(self, reviewer, assignment) -> None:
        complete_draft(assignment)
        editor = actor("EDITOR")

        listed = client_for(editor).get(
            f"/api/editor/manuscripts/{assignment.manuscript_id}/evaluations/"
        )

        assert listed.status_code == 200 and listed.json()["count"] == 0


class TestSaveDraft:
    def test_the_first_put_creates_the_draft(self, reviewer, assignment) -> None:
        response = put(reviewer, assignment, {"clarity_score": 4})

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "DRAFT" and body["clarity_score"] == 4
        assert body["id"] == str(draft_of(assignment).pk)
        assert response["ETag"] == '"1"'
        assert draft_of(assignment).reviewer_id == reviewer.pk
        assert draft_of(assignment).version_id == assignment.version_id

    def test_a_draft_may_have_gaps(self, reviewer, assignment) -> None:
        response = put(reviewer, assignment, {})

        assert response.status_code == 200
        assert response.json()["recommendation"] is None

    def test_each_put_bumps_the_lock_and_changes_only_the_fields_sent(
        self, reviewer, assignment
    ) -> None:
        put(reviewer, assignment, FULL)

        response = put(reviewer, assignment, {"clarity_score": 2}, lock=1)

        assert response.status_code == 200 and response["ETag"] == '"2"'
        draft = draft_of(assignment)
        assert draft.clarity_score == 2
        assert draft.originality_score == FULL["originality_score"]
        assert draft.comments_for_author == FULL["comments_for_author"]

    def test_null_clears_a_field_and_blank_text_is_no_text(self, reviewer, assignment) -> None:
        put(reviewer, assignment, FULL)

        put(
            reviewer,
            assignment,
            {"clarity_score": None, "comments_for_author": "   ", "confidential_comments": ""},
            lock=1,
        )

        draft = draft_of(assignment)
        assert draft.clarity_score is None
        assert draft.comments_for_author is None and draft.confidential_comments is None

    @pytest.mark.parametrize("score", [1, 5])
    def test_scores_at_the_bounds_are_accepted(self, reviewer, assignment, score) -> None:
        assert put(reviewer, assignment, {"ethics_score": score}).status_code == 200

    @pytest.mark.parametrize("field", ["originality_score", "ethics_score"])
    @pytest.mark.parametrize("score", [0, 6, -1, "alto", 2.5])
    def test_a_score_outside_one_to_five_answers_400(self, reviewer, assignment, field, score) -> None:
        response = put(reviewer, assignment, {field: score})

        assert response.status_code == 400 and error_code(response) == "VALIDATION_ERROR"
        assert field in response.json()["error"]["details"]
        assert not Evaluation.objects.filter(assignment=assignment).exists()

    def test_an_unknown_recommendation_answers_400(self, reviewer, assignment) -> None:
        response = put(reviewer, assignment, {"recommendation": "MAYBE"})

        assert response.status_code == 400 and error_code(response) == "VALIDATION_ERROR"

    def test_a_put_can_never_finalize_or_flag_the_evaluation(self, reviewer, assignment) -> None:
        response = put(
            reviewer,
            assignment,
            {"status": "FINAL", "conflict_declared": True, "submitted_at": "2026-01-01T00:00:00Z"},
        )

        assert response.status_code == 200
        draft = draft_of(assignment)
        assert draft.status == "DRAFT" and draft.conflict_declared is False
        assert draft.submitted_at is None

    def test_the_header_is_mandatory(self, reviewer, assignment) -> None:
        response = put(reviewer, assignment, {}, lock=None)

        assert response.status_code == 400 and error_code(response) == "VALIDATION_ERROR"
        assert "evaluación" in response.json()["error"]["message"]

    def test_a_stale_lock_answers_409_and_keeps_the_winning_edit(
        self, reviewer, assignment
    ) -> None:
        put(reviewer, assignment, {"clarity_score": 3})
        put(reviewer, assignment, {"clarity_score": 4}, lock=1)

        stale = put(reviewer, assignment, {"clarity_score": 1}, lock=1)

        assert stale.status_code == 409 and error_code(stale) == "VERSION_CONFLICT"
        assert stale.json()["error"]["details"] == {"lock_version": 2}
        assert draft_of(assignment).clarity_score == 4

    def test_two_tabs_starting_from_the_empty_draft_do_not_overwrite_each_other(
        self, reviewer, assignment
    ) -> None:
        assert put(reviewer, assignment, {"clarity_score": 3}, lock=0).status_code == 200

        second = put(reviewer, assignment, {"clarity_score": 1}, lock=0)

        assert second.status_code == 409
        assert draft_of(assignment).clarity_score == 3

    def test_a_put_with_a_nonzero_lock_before_any_draft_answers_409(
        self, reviewer, assignment
    ) -> None:
        assert put(reviewer, assignment, {}, lock=5).status_code == 409

    def test_a_declared_conflict_blocks_the_draft(self, reviewer, assignment) -> None:
        complete_draft(assignment)
        Evaluation.objects.filter(assignment=assignment).update(conflict_declared=True)

        response = put(reviewer, assignment, {"clarity_score": 1}, lock=1)

        assert response.status_code == 409 and error_code(response) == "STATE_CONFLICT"
        assert draft_of(assignment).clarity_score == FULL["clarity_score"]


class TestDeadline:
    def test_a_draft_cannot_be_saved_after_the_deadline(self, reviewer, assignment) -> None:
        set_deadline(assignment, timedelta(days=-1))

        response = put(reviewer, assignment, {"clarity_score": 3})

        assert response.status_code == 410
        assert not Evaluation.objects.filter(assignment=assignment).exists()

    def test_at_exactly_due_at_the_submission_answers_410_and_keeps_the_draft(
        self, reviewer, assignment, monkeypatch
    ) -> None:
        complete_draft(assignment)
        due_at = set_deadline(assignment, timedelta(days=3))
        freeze_clock(monkeypatch, due_at)

        response = submit(reviewer, assignment, lock=1)

        assert response.status_code == 410
        draft = draft_of(assignment)
        assert draft.status == "DRAFT" and draft.submitted_at is None
        assert draft.comments_for_author == FULL["comments_for_author"]
        assignment.refresh_from_db()
        assert assignment.status == "ACTIVE" and assignment.completed_at is None
        assert not AuditLog.objects.filter(action="EVALUATION_SUBMITTED").exists()

    def test_a_microsecond_before_due_at_the_submission_is_accepted(
        self, reviewer, assignment, monkeypatch
    ) -> None:
        complete_draft(assignment)
        due_at = set_deadline(assignment, timedelta(days=3))
        freeze_clock(monkeypatch, due_at - timedelta(microseconds=1))

        assert submit(reviewer, assignment, lock=1).status_code == 200

    def test_after_due_at_the_submission_answers_410(self, reviewer, assignment) -> None:
        complete_draft(assignment)
        set_deadline(assignment, timedelta(hours=-1))

        assert submit(reviewer, assignment, lock=1).status_code == 410
        assert draft_of(assignment).status == "DRAFT"

    def test_an_expired_assignment_answers_410(self, reviewer, assignment) -> None:
        complete_draft(assignment)
        set_deadline(assignment, timedelta(days=-2))
        set_status(assignment, "EXPIRED")

        assert put(reviewer, assignment, {}, lock=1).status_code == 410
        assert submit(reviewer, assignment, lock=1).status_code == 410
        assert draft_of(assignment).status == "DRAFT"

    def test_a_revoked_assignment_answers_409(self, reviewer, assignment) -> None:
        complete_draft(assignment)
        set_status(assignment, "REVOKED")

        for response in (put(reviewer, assignment, {}, lock=1), submit(reviewer, assignment, lock=1)):
            assert response.status_code == 409 and error_code(response) == "STATE_CONFLICT"
        assert draft_of(assignment).status == "DRAFT"


class TestSubmit:
    def test_turns_the_draft_into_the_final_and_completes_the_assignment(
        self, reviewer, assignment
    ) -> None:
        complete_draft(assignment)

        response = submit(reviewer, assignment, lock=1)

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "FINAL" and body["submitted_at"]
        assert body["recommendation"] == "ACCEPT"
        assert response["ETag"] == '"2"'
        evaluation = draft_of(assignment)
        assert evaluation.status == "FINAL" and evaluation.lock_version == 2
        assignment.refresh_from_db()
        assert assignment.status == "COMPLETED" and assignment.completed_at is not None
        assert assignment.lock_version == 1

    def test_the_whole_flow_through_the_api(self, reviewer, assignment) -> None:
        assert put(reviewer, assignment, {"clarity_score": 2}).status_code == 200
        assert put(reviewer, assignment, FULL, lock=1).status_code == 200

        response = submit(reviewer, assignment, lock=2)

        assert response.status_code == 200 and response.json()["clarity_score"] == 5

    def test_confidential_comments_are_optional(self, reviewer, assignment) -> None:
        complete_draft(assignment, confidential_comments=None)

        assert submit(reviewer, assignment, lock=1).status_code == 200

    def test_it_does_not_touch_the_manuscript_or_create_a_verdict(self, reviewer, assignment) -> None:
        complete_draft(assignment)
        before = Manuscript.objects.get(pk=assignment.manuscript_id)

        submit(reviewer, assignment, lock=1)

        after = Manuscript.objects.get(pk=assignment.manuscript_id)
        assert (after.status, after.lock_version) == (before.status, before.lock_version)
        assert not Verdict.objects.exists()

    def test_the_editor_reads_it_once_final(self, reviewer, assignment) -> None:
        complete_draft(assignment)
        submit(reviewer, assignment, lock=1)

        listed = client_for(actor("EDITOR")).get(
            f"/api/editor/manuscripts/{assignment.manuscript_id}/evaluations/"
        )

        assert listed.json()["count"] == 1

    @pytest.mark.parametrize(
        "missing",
        [
            "originality_score", "methodology_score", "clarity_score", "relevance_score",
            "ethics_score", "recommendation", "comments_for_author",
        ],
    )
    def test_an_incomplete_draft_answers_400_and_stays_a_draft(
        self, reviewer, assignment, missing
    ) -> None:
        complete_draft(assignment, **{missing: None})

        response = submit(reviewer, assignment, lock=1)

        assert response.status_code == 400 and error_code(response) == "VALIDATION_ERROR"
        assert set(response.json()["error"]["details"]) == {missing}
        assert draft_of(assignment).status == "DRAFT"
        assignment.refresh_from_db()
        assert assignment.status == "ACTIVE"
        assert not AuditLog.objects.filter(action="EVALUATION_SUBMITTED").exists()

    def test_blank_comments_for_the_author_do_not_count(self, reviewer, assignment) -> None:
        put(reviewer, assignment, {**FULL, "comments_for_author": "   "})

        response = submit(reviewer, assignment, lock=1)

        assert response.status_code == 400
        assert "comments_for_author" in response.json()["error"]["details"]

    def test_submitting_without_any_draft_lists_every_required_field(
        self, reviewer, assignment
    ) -> None:
        response = submit(reviewer, assignment, lock=0)

        assert response.status_code == 400
        assert set(response.json()["error"]["details"]) == {
            "originality_score", "methodology_score", "clarity_score", "relevance_score",
            "ethics_score", "recommendation", "comments_for_author",
        }

    def test_the_header_is_mandatory(self, reviewer, assignment) -> None:
        complete_draft(assignment)

        response = submit(reviewer, assignment, lock=None)

        assert response.status_code == 400 and error_code(response) == "VALIDATION_ERROR"
        assert draft_of(assignment).status == "DRAFT"

    def test_a_stale_lock_answers_409_and_does_not_submit(self, reviewer, assignment) -> None:
        complete_draft(assignment)

        response = submit(reviewer, assignment, lock=0)

        assert response.status_code == 409 and error_code(response) == "VERSION_CONFLICT"
        assert draft_of(assignment).status == "DRAFT"

    def test_a_declared_conflict_blocks_the_submission(self, reviewer, assignment) -> None:
        complete_draft(assignment)
        Evaluation.objects.filter(assignment=assignment).update(conflict_declared=True)

        response = submit(reviewer, assignment, lock=1)

        assert response.status_code == 409 and error_code(response) == "STATE_CONFLICT"
        assert draft_of(assignment).status == "DRAFT"

    def test_the_submission_is_audited_without_content(self, reviewer, assignment) -> None:
        complete_draft(assignment)

        submit(reviewer, assignment, lock=1)

        row = AuditLog.objects.get(action="EVALUATION_SUBMITTED")
        assert row.actor_id == reviewer.pk and row.actor_role == "REVIEWER"
        assert row.entity_type == "EVALUATION" and row.entity_id == draft_of(assignment).pk
        assert row.request_id
        assert row.details == {
            "manuscript_id": str(assignment.manuscript_id),
            "assignment_id": str(assignment.pk),
            "version_number": 1,
        }
        assert FULL["comments_for_author"] not in str(row.details)

    def test_an_unavailable_audit_answers_503_and_reverts_everything(
        self, reviewer, assignment, monkeypatch
    ) -> None:
        complete_draft(assignment)

        def fail(**kwargs):
            raise AuditUnavailable("sin auditoría")

        monkeypatch.setattr(AuditService, "record", staticmethod(fail))

        response = submit(reviewer, assignment, lock=1)

        assert response.status_code == 503 and error_code(response) == "AUDIT_UNAVAILABLE"
        evaluation = draft_of(assignment)
        assert evaluation.status == "DRAFT" and evaluation.submitted_at is None
        assert evaluation.lock_version == 1
        assignment.refresh_from_db()
        assert assignment.status == "ACTIVE" and assignment.completed_at is None

    def test_the_editor_event_is_sent_after_the_commit_with_identifiers_only(
        self, reviewer, assignment, django_capture_on_commit_callbacks
    ) -> None:
        complete_draft(assignment)
        received: list[dict] = []

        def listener(sender, **kwargs) -> None:
            kwargs.pop("signal", None)
            received.append(kwargs)

        evaluation_submitted.connect(listener, weak=False)
        try:
            response = submit(
                reviewer, assignment, lock=1, capture=django_capture_on_commit_callbacks
            )
        finally:
            evaluation_submitted.disconnect(listener)

        assert response.status_code == 200
        assert received == [
            {
                "evaluation_id": draft_of(assignment).pk,
                "assignment_id": assignment.pk,
                "manuscript_id": assignment.manuscript_id,
                "reviewer_id": reviewer.pk,
            }
        ]

    def test_no_event_is_sent_when_the_submission_fails(
        self, reviewer, assignment, django_capture_on_commit_callbacks
    ) -> None:
        complete_draft(assignment, recommendation=None)
        received: list[dict] = []
        listener = lambda sender, **kwargs: received.append(kwargs)  # noqa: E731

        evaluation_submitted.connect(listener, weak=False)
        try:
            submit(reviewer, assignment, lock=1, capture=django_capture_on_commit_callbacks)
        finally:
            evaluation_submitted.disconnect(listener)

        assert received == []


class TestFinalIsImmutable:
    @pytest.fixture
    def finished(self, reviewer, assignment) -> Assignment:
        complete_draft(assignment)
        assert submit(reviewer, assignment, lock=1).status_code == 200
        return assignment

    def test_a_put_after_the_submission_answers_409(self, reviewer, finished) -> None:
        response = put(reviewer, finished, {"clarity_score": 1}, lock=2)

        assert response.status_code == 409 and error_code(response) == "STATE_CONFLICT"
        assert draft_of(finished).clarity_score == FULL["clarity_score"]

    def test_a_second_submission_answers_409_and_is_not_audited_twice(
        self, reviewer, finished
    ) -> None:
        response = submit(reviewer, finished, lock=2)

        assert response.status_code == 409
        assert AuditLog.objects.filter(action="EVALUATION_SUBMITTED").count() == 1

    def test_the_final_cannot_be_deleted(self, finished) -> None:
        from django.db.utils import DatabaseError

        with pytest.raises(DatabaseError, match="evaluación final es inmutable"):
            Evaluation.objects.filter(assignment=finished).delete()
