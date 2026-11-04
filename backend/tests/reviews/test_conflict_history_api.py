"""Tests for the conflict of interest and the history of the reviewer (TSK-63).

Covers the acceptance criteria: declaring a conflict blocks saving and
submitting the evaluation without revealing the author; the history only
holds the reviewer's own final evaluations, read-only, with the editorial
result once the editor registered it; and neither the history nor the
event for the editor carries author identity or confidential comments.

The no-leak checks look at the serialized JSON text, so a value under
any key would fail too.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIClient

from apps.audit.models import AuditLog
from apps.audit.services import AuditService, AuditUnavailable
from apps.publications.models import Manuscript
from apps.reviews.models import Assignment, Evaluation
from apps.reviews.signals import reviewer_conflict_declared
from tests.factories import (
    AssignmentFactory,
    EvaluationFactory,
    FinalEvaluationFactory,
    ManuscriptAuthorFactory,
    ManuscriptFactory,
    VerdictFactory,
)
from tests.publications.test_manuscript_api import actor, client_for, error_code

pytestmark = pytest.mark.django_db

BASE = "/api/reviewer/"
AUTHOR_NAME = "Ana Autora Reservada"
SECRET = "nota-confidencial-solo-editor"
FULL = {
    "originality_score": 4,
    "methodology_score": 3,
    "clarity_score": 5,
    "relevance_score": 4,
    "ethics_score": 5,
    "recommendation": "ACCEPT",
    "comments_for_author": "Buen trabajo.",
}


@pytest.fixture(autouse=True)
def seeded_roles(db) -> None:
    call_command("seed_roles", verbosity=0)


@pytest.fixture
def reviewer():
    return actor("REVIEWER")


def with_known_author(assignment: Assignment) -> Assignment:
    ManuscriptAuthorFactory(
        manuscript=assignment.manuscript,
        full_name=AUTHOR_NAME,
        email="ana.reservada@otra.edu",
        author_order=1,
    )
    return assignment


@pytest.fixture
def assignment(reviewer) -> Assignment:
    return with_known_author(AssignmentFactory(reviewer=reviewer))


def conflict_url(assignment) -> str:
    return f"{BASE}assignments/{assignment.pk}/conflict/"


def evaluation_url(assignment, suffix: str = "") -> str:
    return f"{BASE}assignments/{assignment.pk}/evaluation/{suffix}"


def declare(user, assignment, body=None, **extra):
    return client_for(user).post(conflict_url(assignment), body or {}, format="json", **extra)


def set_status(assignment, status: str) -> None:
    Assignment.objects.filter(pk=assignment.pk).update(status=status)


def evaluation_of(assignment) -> Evaluation:
    return Evaluation.objects.get(assignment=assignment)


class TestConflictAccess:
    def test_anonymous_requests_answer_401(self, assignment) -> None:
        assert APIClient().post(conflict_url(assignment)).status_code == 401

    @pytest.mark.parametrize("role", ["AUTHOR", "EDITOR", "ADMIN"])
    def test_other_roles_answer_403(self, assignment, role) -> None:
        assert declare(actor(role), assignment).status_code == 403

    def test_a_foreign_assignment_answers_404(self, assignment) -> None:
        response = declare(actor("REVIEWER"), assignment)

        assert response.status_code == 404 and error_code(response) == "NOT_FOUND"
        assert not Evaluation.objects.filter(assignment=assignment).exists()

    def test_a_coauthor_reviewer_gets_404(self, reviewer, assignment) -> None:
        ManuscriptAuthorFactory(manuscript=assignment.manuscript, user=reviewer, author_order=2)

        assert declare(reviewer, assignment).status_code == 404

    def test_only_post_is_allowed(self, reviewer, assignment) -> None:
        client = client_for(reviewer)

        assert client.get(conflict_url(assignment)).status_code == 405
        assert client.put(conflict_url(assignment), {}, format="json").status_code == 405
        assert client.delete(conflict_url(assignment)).status_code == 405


class TestDeclareConflict:
    def test_without_a_draft_it_creates_an_empty_blocked_one(self, reviewer, assignment) -> None:
        response = declare(reviewer, assignment)

        assert response.status_code == 200
        body = response.json()
        assert body["conflict_declared"] is True and body["status"] == "DRAFT"
        assert body["recommendation"] is None
        assert response["ETag"] == '"1"'
        assert evaluation_of(assignment).conflict_declared is True

    def test_an_existing_draft_keeps_its_content(self, reviewer, assignment) -> None:
        EvaluationFactory(assignment=assignment, lock_version=3, **FULL)

        response = declare(reviewer, assignment)

        assert response.status_code == 200 and response["ETag"] == '"4"'
        draft = evaluation_of(assignment)
        assert draft.conflict_declared is True
        assert draft.comments_for_author == FULL["comments_for_author"]
        assert draft.status == "DRAFT"

    def test_it_blocks_saving_the_draft(self, reviewer, assignment) -> None:
        declare(reviewer, assignment)

        response = client_for(reviewer).put(
            evaluation_url(assignment), {"clarity_score": 2}, format="json", HTTP_IF_MATCH='"1"'
        )

        assert response.status_code == 409 and error_code(response) == "STATE_CONFLICT"
        assert evaluation_of(assignment).clarity_score is None

    def test_it_blocks_the_submission_even_with_a_complete_draft(self, reviewer, assignment) -> None:
        EvaluationFactory(assignment=assignment, lock_version=1, **FULL)
        declare(reviewer, assignment)

        response = client_for(reviewer).post(
            evaluation_url(assignment, "submit/"), HTTP_IF_MATCH='"2"'
        )

        assert response.status_code == 409 and error_code(response) == "STATE_CONFLICT"
        assert evaluation_of(assignment).status == "DRAFT"
        assignment.refresh_from_db()
        assert assignment.status == "ACTIVE"

    def test_the_flag_shows_in_the_evaluation_read(self, reviewer, assignment) -> None:
        declare(reviewer, assignment)

        body = client_for(reviewer).get(evaluation_url(assignment)).json()

        assert body["conflict_declared"] is True

    def test_declaring_twice_answers_409(self, reviewer, assignment) -> None:
        declare(reviewer, assignment)

        response = declare(reviewer, assignment)

        assert response.status_code == 409 and error_code(response) == "STATE_CONFLICT"
        assert AuditLog.objects.filter(action="CONFLICT_OF_INTEREST_DECLARED").count() == 1

    @pytest.mark.parametrize("status", ["COMPLETED", "REVOKED", "EXPIRED"])
    def test_a_non_active_assignment_answers_409(self, reviewer, assignment, status) -> None:
        set_status(assignment, status)

        response = declare(reviewer, assignment)

        assert response.status_code == 409 and error_code(response) == "STATE_CONFLICT"
        assert not Evaluation.objects.filter(assignment=assignment).exists()

    def test_an_active_assignment_past_its_deadline_can_still_declare(
        self, reviewer, assignment
    ) -> None:
        due_at = timezone.now() - timedelta(days=1)
        Assignment.objects.filter(pk=assignment.pk).update(
            due_at=due_at, assigned_at=due_at - timedelta(days=20)
        )

        assert declare(reviewer, assignment).status_code == 200

    def test_it_does_not_revoke_nor_move_the_manuscript(self, reviewer, assignment) -> None:
        before = Manuscript.objects.get(pk=assignment.manuscript_id)

        declare(reviewer, assignment)

        assignment.refresh_from_db()
        after = Manuscript.objects.get(pk=assignment.manuscript_id)
        assert assignment.status == "ACTIVE" and assignment.revoked_at is None
        assert (after.status, after.lock_version) == (before.status, before.lock_version)

    def test_a_reason_longer_than_the_limit_answers_400(self, reviewer, assignment) -> None:
        response = declare(reviewer, assignment, {"reason": "x" * 2001})

        assert response.status_code == 400 and error_code(response) == "VALIDATION_ERROR"
        assert not Evaluation.objects.filter(assignment=assignment).exists()

    def test_the_declaration_is_audited_with_the_reason_and_no_author_data(
        self, reviewer, assignment
    ) -> None:
        declare(reviewer, assignment, {"reason": "  Conozco el grupo de investigación.  "})

        row = AuditLog.objects.get(action="CONFLICT_OF_INTEREST_DECLARED")
        assert row.actor_id == reviewer.pk and row.actor_role == "REVIEWER"
        assert row.entity_type == "ASSIGNMENT" and row.entity_id == assignment.pk
        assert row.reason == "Conozco el grupo de investigación." and row.request_id
        assert row.details == {"manuscript_id": str(assignment.manuscript_id)}
        assert AUTHOR_NAME not in str(row.details)

    def test_the_answer_does_not_reveal_the_author(self, reviewer, assignment) -> None:
        response = declare(reviewer, assignment)

        text = response.content.decode() + str(response.headers)
        assert AUTHOR_NAME not in text and "ana.reservada" not in text

    def test_an_unavailable_audit_answers_503_and_reverts_everything(
        self, reviewer, assignment, monkeypatch
    ) -> None:
        def fail(**kwargs):
            raise AuditUnavailable("sin auditoría")

        monkeypatch.setattr(AuditService, "record", staticmethod(fail))

        response = declare(reviewer, assignment)

        assert response.status_code == 503 and error_code(response) == "AUDIT_UNAVAILABLE"
        assert not Evaluation.objects.filter(assignment=assignment).exists()

    def test_the_editor_event_is_sent_after_the_commit_with_identifiers_only(
        self, reviewer, assignment, django_capture_on_commit_callbacks
    ) -> None:
        received: list[dict] = []

        def listener(sender, **kwargs) -> None:
            kwargs.pop("signal", None)
            received.append(kwargs)

        reviewer_conflict_declared.connect(listener, weak=False)
        try:
            with django_capture_on_commit_callbacks(execute=True):
                response = declare(reviewer, assignment, {"reason": "Texto libre."})
        finally:
            reviewer_conflict_declared.disconnect(listener)

        assert response.status_code == 200
        assert received == [
            {
                "assignment_id": assignment.pk,
                "manuscript_id": assignment.manuscript_id,
                "reviewer_id": reviewer.pk,
            }
        ]

    def test_no_event_is_sent_when_the_declaration_fails(
        self, reviewer, assignment, django_capture_on_commit_callbacks
    ) -> None:
        set_status(assignment, "REVOKED")
        received: list[dict] = []
        listener = lambda sender, **kwargs: received.append(kwargs)  # noqa: E731

        reviewer_conflict_declared.connect(listener, weak=False)
        try:
            with django_capture_on_commit_callbacks(execute=True):
                declare(reviewer, assignment)
        finally:
            reviewer_conflict_declared.disconnect(listener)

        assert received == []


def final_for(reviewer, **overrides) -> Evaluation:
    """A completed assignment of the reviewer with its final evaluation."""
    assignment = with_known_author(AssignmentFactory(reviewer=reviewer))
    Assignment.objects.filter(pk=assignment.pk).update(status="COMPLETED")
    return FinalEvaluationFactory(
        assignment=assignment, confidential_comments=SECRET, **overrides
    )


LIST_URL = f"{BASE}evaluations/"
LIST_FIELDS = {
    "id", "assignment", "manuscript_code", "manuscript_title", "area", "version_number",
    "round_number", "recommendation", "submitted_at", "editorial_result",
}
DETAIL_FIELDS = LIST_FIELDS | {
    "originality_score", "methodology_score", "clarity_score", "relevance_score",
    "ethics_score", "comments_for_author",
}


def detail_url(evaluation) -> str:
    return f"{LIST_URL}{evaluation.pk}/"


class TestHistoryAccess:
    @pytest.mark.parametrize("suffix", ["", "{id}/"])
    def test_anonymous_requests_answer_401(self, reviewer, suffix) -> None:
        evaluation = final_for(reviewer)

        assert APIClient().get(LIST_URL + suffix.format(id=evaluation.pk)).status_code == 401

    @pytest.mark.parametrize("role", ["AUTHOR", "EDITOR", "ADMIN"])
    @pytest.mark.parametrize("suffix", ["", "{id}/"])
    def test_other_roles_answer_403(self, reviewer, role, suffix) -> None:
        evaluation = final_for(reviewer)

        response = client_for(actor(role)).get(LIST_URL + suffix.format(id=evaluation.pk))

        assert response.status_code == 403

    def test_the_history_is_read_only(self, reviewer) -> None:
        evaluation = final_for(reviewer)
        client = client_for(reviewer)

        for url in (LIST_URL, detail_url(evaluation)):
            assert client.post(url, {}, format="json").status_code == 405
            assert client.put(url, {}, format="json").status_code == 405
            assert client.delete(url).status_code == 405


class TestHistoryScope:
    def test_lists_only_the_reviewers_own_final_evaluations(self, reviewer) -> None:
        own = final_for(reviewer)
        final_for(actor("REVIEWER"))

        body = client_for(reviewer).get(LIST_URL).json()

        assert body["count"] == 1 and body["results"][0]["id"] == str(own.pk)

    def test_an_empty_history_is_a_valid_answer(self, reviewer) -> None:
        body = client_for(reviewer).get(LIST_URL).json()

        assert body["count"] == 0 and body["results"] == []

    def test_drafts_and_blocked_evaluations_are_not_listed(self, reviewer) -> None:
        draft_assignment = AssignmentFactory(reviewer=reviewer)
        EvaluationFactory(assignment=draft_assignment, **FULL)
        blocked_assignment = AssignmentFactory(reviewer=reviewer)
        EvaluationFactory(assignment=blocked_assignment, conflict_declared=True)
        final = final_for(reviewer)

        ids = [row["id"] for row in client_for(reviewer).get(LIST_URL).json()["results"]]

        assert ids == [str(final.pk)]

    def test_a_withdrawn_manuscript_is_not_listed(self, reviewer) -> None:
        evaluation = final_for(reviewer)
        Manuscript.objects.filter(pk=evaluation.manuscript_id).update(
            is_active=False, withdrawn_at=timezone.now()
        )

        assert client_for(reviewer).get(LIST_URL).json()["count"] == 0
        assert client_for(reviewer).get(detail_url(evaluation)).status_code == 404

    def test_a_manuscript_the_reviewer_later_coauthored_is_not_listed(self, reviewer) -> None:
        evaluation = final_for(reviewer)
        ManuscriptAuthorFactory(manuscript=evaluation.manuscript, user=reviewer, author_order=2)

        assert client_for(reviewer).get(LIST_URL).json()["count"] == 0
        assert client_for(reviewer).get(detail_url(evaluation)).status_code == 404

    def test_the_newest_is_first_and_the_list_is_paginated(self, reviewer) -> None:
        final_for(reviewer, submitted_at=timezone.now() - timedelta(days=2))
        newer = final_for(reviewer, submitted_at=timezone.now() - timedelta(days=1))

        body = client_for(reviewer).get(LIST_URL, {"page_size": 1}).json()

        assert body["count"] == 2 and body["next"]
        assert [row["id"] for row in body["results"]] == [str(newer.pk)]

    def test_the_list_does_not_query_per_row(self, reviewer, django_assert_max_num_queries) -> None:
        for _ in range(4):
            VerdictFactory(evaluation=final_for(reviewer))

        with django_assert_max_num_queries(6):
            assert client_for(reviewer).get(LIST_URL).status_code == 200


class TestHistoryContent:
    def test_the_list_row_is_an_allowlist(self, reviewer) -> None:
        final_for(reviewer)

        row = client_for(reviewer).get(LIST_URL).json()["results"][0]

        assert set(row) == LIST_FIELDS

    def test_the_detail_is_an_allowlist_in_read_mode(self, reviewer) -> None:
        evaluation = final_for(reviewer)

        response = client_for(reviewer).get(detail_url(evaluation))

        assert response.status_code == 200
        body = response.json()
        assert set(body) == DETAIL_FIELDS
        assert body["comments_for_author"] == "Comentarios para el autor."
        assert body["clarity_score"] == 4 and body["recommendation"] == "ACCEPT"

    def test_no_author_identity_nor_confidential_comments_under_any_key(self, reviewer) -> None:
        evaluation = final_for(reviewer)
        VerdictFactory(evaluation=evaluation, observations="Observaciones privadas.")
        author = evaluation.manuscript.created_by

        texts = [
            client_for(reviewer).get(LIST_URL).content.decode(),
            client_for(reviewer).get(detail_url(evaluation)).content.decode(),
        ]

        for text in texts:
            for secret in (
                AUTHOR_NAME,
                "ana.reservada",
                author.email,
                author.institutional_id,
                SECRET,
                "confidential_comments",
                "Observaciones privadas.",
                "created_by",
                "authors",
            ):
                assert secret not in text

    def test_the_editorial_result_is_empty_until_the_editor_registers_it(self, reviewer) -> None:
        evaluation = final_for(reviewer)

        assert client_for(reviewer).get(detail_url(evaluation)).json()["editorial_result"] is None
        assert client_for(reviewer).get(LIST_URL).json()["results"][0]["editorial_result"] is None

    def test_the_editorial_result_shows_the_decision_and_date_only(self, reviewer) -> None:
        evaluation = final_for(reviewer)
        verdict = VerdictFactory(
            evaluation=evaluation,
            decision="REJECTED",
            justification="Justificación escrita para el autor.",
        )

        for body in (
            client_for(reviewer).get(LIST_URL).json()["results"][0],
            client_for(reviewer).get(detail_url(evaluation)).json(),
        ):
            result = body["editorial_result"]
            assert set(result) == {"decision", "decided_at"}
            assert result["decision"] == "REJECTED" and result["decided_at"]
            assert "Justificación" not in str(body)
        assert verdict.editor.get_full_name() not in client_for(reviewer).get(LIST_URL).content.decode()

    def test_a_corrected_verdict_replaces_the_previous_one(self, reviewer) -> None:
        evaluation = final_for(reviewer)
        first = VerdictFactory(evaluation=evaluation, decision="ACCEPTED")
        VerdictFactory(
            evaluation=evaluation,
            decision="REQUIRES_CORRECTIONS",
            observations="Hay que corregir.",
            previous_verdict=first,
        )

        body = client_for(reviewer).get(detail_url(evaluation)).json()

        assert body["editorial_result"]["decision"] == "REQUIRES_CORRECTIONS"

    def test_the_row_identifies_the_manuscript_by_code_title_and_area(self, reviewer) -> None:
        evaluation = final_for(reviewer)

        row = client_for(reviewer).get(LIST_URL).json()["results"][0]

        assert row["manuscript_code"] == evaluation.manuscript.code
        assert row["manuscript_title"] == evaluation.manuscript.title
        assert row["area"] == evaluation.manuscript.area
        assert row["version_number"] == 1 and row["round_number"] == 0
        assert row["assignment"] == str(evaluation.assignment_id)


class TestHistoryDetailScope:
    def test_a_foreign_evaluation_answers_404_not_403(self, reviewer) -> None:
        foreign = final_for(actor("REVIEWER"))

        response = client_for(reviewer).get(detail_url(foreign))

        assert response.status_code == 404 and error_code(response) == "NOT_FOUND"

    def test_an_own_draft_answers_404(self, reviewer) -> None:
        draft = EvaluationFactory(assignment=AssignmentFactory(reviewer=reviewer), **FULL)

        assert client_for(reviewer).get(detail_url(draft)).status_code == 404

    def test_an_unknown_id_answers_404(self, reviewer) -> None:
        assert client_for(reviewer).get(f"{LIST_URL}{ManuscriptFactory().pk}/").status_code == 404

    def test_a_final_evaluation_is_seen_even_after_the_assignment_was_completed(
        self, reviewer
    ) -> None:
        evaluation = final_for(reviewer)

        assert client_for(reviewer).get(detail_url(evaluation)).status_code == 200
