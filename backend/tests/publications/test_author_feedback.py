"""The author reads the outcome of the evaluation (D-19, CA-HU-13-04).

After the editor registers a verdict, the author's manuscript carries
``feedback``: the comments the reviewer wrote for them, the decision and
the editor's observations. It is an allowlist of three fields, so none of
the following ever reaches the author: the reviewer's identity, the
confidential comments, the scores and the editor's internal
justification. Before a verdict there is no feedback, even if the
reviewer's final evaluation already exists.
"""

from __future__ import annotations

import json

import pytest
from django.core.management import call_command

from apps.publications.services.verdicts import register_verdict
from tests.publications.test_manuscript_api import actor, client_for
from tests.publications.test_verdicts import reviewed

pytestmark = pytest.mark.django_db

SECRET_COMMENT = "Solo para el Editor: sospecho autocitas."
INTERNAL_JUSTIFICATION = "Justificación interna del Editor."
FOR_AUTHOR = "Comentario del Revisor para el Autor."
REVIEWER_NAME = "Revisora Secreta Anónima"


@pytest.fixture(autouse=True)
def seeded_roles(db) -> None:
    call_command("seed_roles", verbosity=0)


@pytest.fixture(autouse=True)
def media_root(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    return tmp_path


@pytest.fixture
def editor():
    return actor("EDITOR")


@pytest.fixture
def owner():
    return actor("AUTHOR")


def judged_case(editor, owner, **evaluation):
    """A manuscript under review whose final evaluation carries secrets."""
    from apps.reviews.models import Evaluation

    manuscript = reviewed(
        editor,
        owner=owner,
        evaluation={
            "comments_for_author": FOR_AUTHOR,
            "confidential_comments": SECRET_COMMENT,
            **evaluation,
        },
    )
    reviewer = Evaluation.objects.get(manuscript=manuscript).reviewer
    reviewer.first_name, reviewer.last_name = "Revisora", "Secreta Anónima"
    reviewer.save(update_fields=("first_name", "last_name"))
    return manuscript, reviewer


def judge(editor, manuscript, decision, **texts):
    return register_verdict(
        manuscript_id=manuscript.pk, editor=editor, decision=decision, context={}, **texts
    )


def detail(owner, manuscript):
    return client_for(owner).get(f"/api/manuscripts/{manuscript.pk}/")


class TestBeforeTheVerdict:
    def test_a_final_evaluation_alone_is_not_shown(self, editor, owner) -> None:
        manuscript, _ = judged_case(editor, owner)

        body = detail(owner, manuscript).json()

        assert body["feedback"] is None
        assert FOR_AUTHOR not in json.dumps(body)

    def test_a_new_draft_has_no_feedback(self, owner) -> None:
        from tests.publications.test_manuscript_api import post_draft

        response = post_draft(owner)

        assert response.status_code == 201 and response.json()["feedback"] is None


class TestAfterTheVerdict:
    def test_corrections_give_the_author_the_observations_and_the_reviewer_comments(
        self, editor, owner
    ) -> None:
        manuscript, _ = judged_case(editor, owner, recommendation="REQUIRES_CORRECTIONS")
        judge(editor, manuscript, "REQUIRES_CORRECTIONS", observations="Ampliar la sección 3.")

        response = detail(owner, manuscript)

        assert response.status_code == 200
        assert response.json()["feedback"] == {
            "comments_for_author": FOR_AUTHOR,
            "decision": "REQUIRES_CORRECTIONS",
            "observations": "Ampliar la sección 3.",
        }

    def test_an_acceptance_has_no_observations(self, editor, owner) -> None:
        manuscript, _ = judged_case(editor, owner)
        judge(editor, manuscript, "ACCEPTED")

        feedback = detail(owner, manuscript).json()["feedback"]

        assert feedback == {
            "comments_for_author": FOR_AUTHOR,
            "decision": "ACCEPTED",
            "observations": None,
        }

    def test_a_rejection_never_shows_the_internal_justification(self, editor, owner) -> None:
        manuscript, _ = judged_case(editor, owner, recommendation="REJECT")
        judge(editor, manuscript, "REJECTED", justification=INTERNAL_JUSTIFICATION)

        body = detail(owner, manuscript).json()

        assert body["feedback"]["decision"] == "REJECTED"
        assert INTERNAL_JUSTIFICATION not in json.dumps(body)

    def test_the_feedback_is_exactly_the_three_allowed_fields(self, editor, owner) -> None:
        manuscript, _ = judged_case(editor, owner)
        judge(editor, manuscript, "ACCEPTED")

        feedback = detail(owner, manuscript).json()["feedback"]

        assert sorted(feedback) == ["comments_for_author", "decision", "observations"]

    def test_nothing_that_identifies_the_reviewer_or_scores_reaches_the_author(
        self, editor, owner
    ) -> None:
        manuscript, reviewer = judged_case(editor, owner, recommendation="REQUIRES_CORRECTIONS")
        judge(
            editor,
            manuscript,
            "REQUIRES_CORRECTIONS",
            observations="Corregir.",
            justification=INTERNAL_JUSTIFICATION,
        )

        for response in (
            detail(owner, manuscript),
            client_for(owner).get("/api/manuscripts/"),
        ):
            text = response.content.decode()
            assert response.status_code == 200
            assert SECRET_COMMENT not in text
            assert INTERNAL_JUSTIFICATION not in text
            assert REVIEWER_NAME not in text
            assert reviewer.email not in text and reviewer.institutional_id not in text
            assert str(reviewer.pk) not in text
            for forbidden in ("confidential_comments", "originality_score", "reviewer", "editor"):
                assert forbidden not in text, forbidden

    def test_the_latest_verdict_is_the_one_shown(self, editor, owner) -> None:
        manuscript, _ = judged_case(editor, owner, recommendation="REQUIRES_CORRECTIONS")
        judge(editor, manuscript, "REQUIRES_CORRECTIONS", observations="Primera ronda.")
        # Un veredicto posterior (otra versión) sustituye al anterior en la vista.
        from apps.publications.models import Manuscript, Verdict
        from tests.factories import ManuscriptVersionFactory

        second_version = ManuscriptVersionFactory(
            manuscript=manuscript, submitted_by=owner, version_number=2, round_number=1
        )
        first = Verdict.objects.get(manuscript=manuscript)
        Verdict.objects.create(
            manuscript=manuscript,
            version=second_version,
            evaluation=first.evaluation,
            editor=editor,
            decision="ACCEPTED",
        )
        Manuscript.objects.filter(pk=manuscript.pk).update(current_version=2)

        feedback = detail(owner, manuscript).json()["feedback"]

        assert feedback["decision"] == "ACCEPTED"
        assert feedback["observations"] is None

    def test_a_withdrawn_manuscript_keeps_its_feedback(self, editor, owner) -> None:
        from django.utils import timezone

        from apps.publications.models import Manuscript

        manuscript, _ = judged_case(editor, owner)
        judge(editor, manuscript, "ACCEPTED")
        Manuscript.objects.filter(pk=manuscript.pk).update(
            is_active=False, withdrawn_at=timezone.now()
        )

        response = client_for(owner).get(f"/api/manuscripts/{manuscript.pk}/")

        assert response.status_code == 200
        assert response.json()["feedback"]["decision"] == "ACCEPTED"


class TestWhoCanRead:
    def test_another_author_gets_404(self, editor, owner) -> None:
        manuscript, _ = judged_case(editor, owner)
        judge(editor, manuscript, "ACCEPTED")

        assert detail(actor("AUTHOR"), manuscript).status_code == 404

    def test_the_editor_view_has_no_author_feedback_field(self, editor, owner) -> None:
        manuscript, _ = judged_case(editor, owner)
        judge(editor, manuscript, "ACCEPTED")

        body = detail(editor, manuscript).json()

        assert "feedback" not in body

    def test_a_list_carries_each_feedback_without_a_query_per_manuscript(
        self, editor, owner, django_assert_max_num_queries
    ) -> None:
        for _ in range(5):
            manuscript, _ = judged_case(editor, owner)
            judge(editor, manuscript, "ACCEPTED")
        client = client_for(owner)

        with django_assert_max_num_queries(14):
            response = client.get("/api/manuscripts/")

        rows = response.json()["results"]
        assert len(rows) == 5
        assert all(row["feedback"]["decision"] == "ACCEPTED" for row in rows)
