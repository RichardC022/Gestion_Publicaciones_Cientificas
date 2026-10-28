"""A final evaluation cannot be modified by any path (TSK-65).

The API refuses with ``409``, the model refuses at the database through
the trigger of migration ``0002``, and neither an incident resolution nor
a later conflict declaration reaches it. The final evaluation reads
exactly the same after every attempt.
"""

from __future__ import annotations

import pytest
from django.core.management import call_command
from django.db import connection, transaction
from django.db.utils import DatabaseError

from apps.reviews.models import SCORE_FIELDS, Assignment, Evaluation, IncidentReport
from tests.factories import EvaluationFactory
from tests.publications.test_manuscript_api import actor, client_for
from tests.reviews.test_editor_api import make_assignment, make_reviewer, submitted

pytestmark = pytest.mark.django_db

REVIEWER = "/api/reviewer/assignments/"
EDITOR = "/api/editor/"
FULL = {
    "originality_score": 4,
    "methodology_score": 3,
    "clarity_score": 5,
    "relevance_score": 4,
    "ethics_score": 5,
    "recommendation": "ACCEPT",
    "comments_for_author": "Buen trabajo.",
    "confidential_comments": "Nota privada.",
}
IMMUTABLE_MESSAGE = "evaluación final es inmutable"


@pytest.fixture(autouse=True)
def seeded_roles(db) -> None:
    call_command("seed_roles", verbosity=0)


@pytest.fixture
def case():
    """A final evaluation submitted through the API, plus the people around it."""

    class Scenario:
        editor = actor("EDITOR")
        reviewer = make_reviewer()
        manuscript = submitted(status="UNDER_REVIEW")

    scenario = Scenario()
    scenario.assignment = make_assignment(scenario.manuscript, scenario.reviewer, scenario.editor)
    scenario.base = f"{REVIEWER}{scenario.assignment.pk}/"
    EvaluationFactory(assignment=scenario.assignment, lock_version=1, **FULL)
    scenario.client = client_for(scenario.reviewer)
    return scenario


def snapshot(assignment: Assignment) -> dict:
    row = Evaluation.objects.filter(assignment=assignment).values().get()
    return dict(row)


def finish(case) -> dict:
    response = case.client.post(f"{case.base}evaluation/submit/", HTTP_IF_MATCH='"1"')
    assert response.status_code == 200, response.content
    return snapshot(case.assignment)


class TestApiRefusals:
    def test_no_endpoint_changes_a_final_evaluation(self, case) -> None:
        final = finish(case)

        attempts = [
            case.client.put(f"{case.base}evaluation/", {"clarity_score": 1}, format="json", HTTP_IF_MATCH='"2"'),
            case.client.put(f"{case.base}evaluation/", {}, format="json", HTTP_IF_MATCH='"0"'),
            case.client.post(f"{case.base}evaluation/submit/", HTTP_IF_MATCH='"2"'),
            case.client.post(f"{case.base}conflict/", {}, format="json"),
        ]

        assert [r.status_code for r in attempts] == [409, 409, 409, 409]
        assert snapshot(case.assignment) == final

    def test_the_final_reads_the_same_after_every_attempt(self, case) -> None:
        finish(case)
        before = case.client.get(f"{case.base}evaluation/")
        case.client.put(f"{case.base}evaluation/", {"ethics_score": 1}, format="json", HTTP_IF_MATCH='"2"')
        case.client.post(f"{case.base}evaluation/submit/", HTTP_IF_MATCH='"2"')

        after = case.client.get(f"{case.base}evaluation/")

        assert after.json() == before.json() and after["ETag"] == before["ETag"]
        assert after.json()["status"] == "FINAL"

    def test_a_completed_assignment_accepts_no_new_report(self, case) -> None:
        final = finish(case)

        response = case.client.post(
            f"{case.base}identity-leak/",
            {"report_type": "OTHER", "description": "Tarde."},
            format="json",
        )

        assert response.status_code == 409
        assert snapshot(case.assignment) == final


class TestDatabaseRefusals:
    def test_every_column_is_protected_from_update(self, case) -> None:
        final = finish(case)
        columns = {
            "comments_for_author": "otro",
            "confidential_comments": "otro",
            "recommendation": "REJECT",
            "conflict_declared": True,
            "lock_version": 99,
            **{field: 1 for field in SCORE_FIELDS},
        }

        for column, value in columns.items():
            with pytest.raises(DatabaseError, match=IMMUTABLE_MESSAGE):
                with transaction.atomic():
                    Evaluation.objects.filter(assignment=case.assignment).update(**{column: value})

        assert snapshot(case.assignment) == final

    def test_save_on_a_loaded_final_fails(self, case) -> None:
        finish(case)
        evaluation = Evaluation.objects.get(assignment=case.assignment)
        evaluation.clarity_score = 1

        with pytest.raises(DatabaseError, match=IMMUTABLE_MESSAGE):
            with transaction.atomic():
                evaluation.save()

    def test_raw_sql_update_and_delete_fail(self, case) -> None:
        final = finish(case)

        for sql in (
            "UPDATE reviews_evaluation SET status = 'DRAFT' WHERE assignment_id = %s",
            "DELETE FROM reviews_evaluation WHERE assignment_id = %s",
        ):
            with pytest.raises(DatabaseError, match=IMMUTABLE_MESSAGE):
                with transaction.atomic(), connection.cursor() as cursor:
                    cursor.execute(sql, [case.assignment.pk])

        assert snapshot(case.assignment) == final


class TestOtherFlowsLeaveItAlone:
    def test_resolving_an_incident_reported_before_the_submission_does_not_touch_the_final(
        self, case
    ) -> None:
        reported = case.client.post(
            f"{case.base}identity-leak/",
            {"report_type": "IDENTITY_LEAK", "description": "Texto."},
            format="json",
        )
        assert reported.status_code == 201
        final = finish(case)
        incident = IncidentReport.objects.get()

        response = client_for(case.editor).post(
            f"{EDITOR}incidents/{incident.pk}/resolve/",
            {"resolution": "REQUEST_ANONYMIZED_VERSION"},
            format="json",
        )
        assert response.status_code == 200, response.content

        assert snapshot(case.assignment) == final
        case.assignment.refresh_from_db()
        # Ya completada: no hay nada que revocar y la evaluación sigue intacta.
        assert case.assignment.status == "COMPLETED" and case.assignment.revoked_at is None
        assert Evaluation.objects.get(assignment=case.assignment).status == "FINAL"

    def test_a_revocation_after_the_submission_is_refused_and_leaves_the_final(self, case) -> None:
        final = finish(case)

        response = client_for(case.editor).post(
            f"{EDITOR}assignments/{case.assignment.pk}/revoke/",
            {"cause": "ASSIGNMENT_ERROR", "reason": "Tarde."},
            format="json",
        )

        assert response.status_code == 409
        assert snapshot(case.assignment) == final
