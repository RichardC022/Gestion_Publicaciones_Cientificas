"""Tests for the verdict and evaluation endpoints of the editor (TSK-52).

Covers the acceptance criteria: no verdict without a ``FINAL`` evaluation
or on a withdrawn manuscript; the answer carries the verdict history but
a verdict can never be edited; and if the audit fails the answer is
``503`` and nothing is published in the catalog.

Plus the contracts of the plan: ``If-Match`` and a mandatory
``Idempotency-Key`` (the same key repeats the stored answer), the editor
with a conflict of interest is blocked and audited, and the reviewer's
identity and confidential comments reach only the editor.
"""

from __future__ import annotations

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.audit.services import AuditService, AuditUnavailable
from apps.publications.models import CatalogEntry, Manuscript, Verdict
from apps.publications.services.storage import catalog_path
from apps.reviews.models import Evaluation
from tests.factories import ManuscriptAuthorFactory, ManuscriptVersionFactory
from tests.publications.test_manuscript_api import actor, client_for, error_code
from tests.publications.test_verdicts import reviewed
from tests.reviews.test_editor_api import make_assignment, make_reviewer, results, submitted

pytestmark = pytest.mark.django_db

BASE = "/api/editor/manuscripts/"


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


def verdicts_url(manuscript) -> str:
    return f"{BASE}{manuscript.pk}/verdicts/"


def evaluations_url(manuscript) -> str:
    return f"{BASE}{manuscript.pk}/evaluations/"


def post_verdict(user, manuscript, body, *, key="clave-1", if_match='"0"', callbacks=None):
    headers = {}
    if key is not None:
        headers["HTTP_IDEMPOTENCY_KEY"] = key
    if if_match is not None:
        headers["HTTP_IF_MATCH"] = if_match
    client = client_for(user)
    if callbacks is None:
        return client.post(verdicts_url(manuscript), body, format="json", **headers)
    with callbacks(execute=True):
        return client.post(verdicts_url(manuscript), body, format="json", **headers)


class TestAccess:
    @pytest.mark.parametrize("role", ["AUTHOR", "REVIEWER"])
    def test_other_roles_get_403(self, role, editor) -> None:
        manuscript = reviewed(editor)
        client = client_for(actor(role))

        assert client.get(verdicts_url(manuscript)).status_code == 403
        assert client.get(evaluations_url(manuscript)).status_code == 403
        assert client.post(verdicts_url(manuscript), {"decision": "ACCEPTED"}, format="json").status_code == 403

    def test_anonymous_gets_401(self, editor) -> None:
        from rest_framework.test import APIClient

        manuscript = reviewed(editor)

        assert APIClient().get(verdicts_url(manuscript)).status_code == 401
        assert APIClient().get(evaluations_url(manuscript)).status_code == 401

    def test_an_unknown_or_draft_manuscript_answers_404(self, editor) -> None:
        import uuid

        from tests.factories import ManuscriptFactory

        draft = ManuscriptFactory(created_by=actor("AUTHOR"), status="DRAFT")

        for target in (uuid.uuid4(), draft.pk):
            assert client_for(editor).get(f"{BASE}{target}/verdicts/").status_code == 404
            assert client_for(editor).get(f"{BASE}{target}/evaluations/").status_code == 404
            assert post_verdict(editor, type("M", (), {"pk": target})(), {"decision": "ACCEPTED"}).status_code == 404


class TestRegisterVerdict:
    def test_accepting_answers_201_with_history_and_publishes(
        self, editor, django_capture_on_commit_callbacks
    ) -> None:
        manuscript = reviewed(editor)

        response = post_verdict(
            editor, manuscript, {"decision": "ACCEPTED"}, callbacks=django_capture_on_commit_callbacks
        )

        assert response.status_code == 201, response.content
        body = response.json()
        assert body["verdict"]["decision"] == "ACCEPTED"
        assert body["verdict"]["editor"]["id"] == str(editor.pk)
        assert body["verdict"]["previous_verdict"] is None
        assert body["manuscript"]["status"] == "ACCEPTED"
        assert body["opened_round"] is None
        assert [row["id"] for row in body["history"]] == [body["verdict"]["id"]]
        entry = CatalogEntry.objects.get(manuscript=manuscript)
        assert body["catalog_entry"]["id"] == str(entry.pk)
        assert catalog_path(entry.public_file_path).is_file()
        assert response["ETag"] == '"1"'
        assert "Idempotent-Replayed" not in response

    def test_requesting_corrections_opens_the_next_round(
        self, editor, django_capture_on_commit_callbacks
    ) -> None:
        manuscript = reviewed(editor, recommendation="REQUIRES_CORRECTIONS")

        response = post_verdict(
            editor,
            manuscript,
            {"decision": "REQUIRES_CORRECTIONS", "observations": "Ampliar la sección 3."},
            callbacks=django_capture_on_commit_callbacks,
        )

        assert response.status_code == 201
        body = response.json()
        assert body["opened_round"] == 1 and body["catalog_entry"] is None
        assert body["manuscript"]["status"] == "REQUIRES_CORRECTIONS"
        assert body["manuscript"]["current_round"] == 1

    def test_rejecting_publishes_nothing(
        self, editor, django_capture_on_commit_callbacks
    ) -> None:
        manuscript = reviewed(editor, recommendation="REJECT")

        response = post_verdict(
            editor,
            manuscript,
            {"decision": "REJECTED", "justification": "Metodología inválida."},
            callbacks=django_capture_on_commit_callbacks,
        )

        assert response.status_code == 201
        assert response.json()["catalog_entry"] is None
        assert not CatalogEntry.objects.exists()

    @pytest.mark.parametrize(
        ("body", "field"),
        [
            ({}, "decision"),
            ({"decision": "MAYBE"}, "decision"),
            ({"decision": "REJECTED"}, "justification"),
            ({"decision": "REJECTED", "justification": "  "}, "justification"),
            ({"decision": "REQUIRES_CORRECTIONS"}, "observations"),
            ({"decision": "ACCEPTED"}, "justification"),
        ],
    )
    def test_invalid_bodies_answer_400_and_write_nothing(self, editor, body, field) -> None:
        # La evaluación recomienda rechazar: aceptar sin justificar se aparta de ella.
        manuscript = reviewed(editor, recommendation="REJECT")

        response = post_verdict(editor, manuscript, body)

        assert response.status_code == 400 and error_code(response) == "VALIDATION_ERROR"
        assert field in response.json()["error"]["details"]
        assert not Verdict.objects.exists()
        assert Manuscript.objects.get(pk=manuscript.pk).status == "UNDER_REVIEW"

    def test_the_idempotency_key_and_if_match_are_mandatory(self, editor) -> None:
        manuscript = reviewed(editor)
        body = {"decision": "ACCEPTED"}

        no_key = post_verdict(editor, manuscript, body, key=None)
        bad_key = post_verdict(editor, manuscript, body, key="clave con espacios")
        no_if_match = post_verdict(editor, manuscript, body, if_match=None)

        for response in (no_key, bad_key, no_if_match):
            assert response.status_code == 400 and error_code(response) == "VALIDATION_ERROR"
        assert not Verdict.objects.exists()

    def test_a_stale_etag_answers_409(self, editor) -> None:
        manuscript = reviewed(editor)

        response = post_verdict(editor, manuscript, {"decision": "ACCEPTED"}, if_match='"5"')

        assert response.status_code == 409 and error_code(response) == "VERSION_CONFLICT"
        assert response.json()["error"]["details"] == {"lock_version": 0}
        assert not Verdict.objects.exists()


class TestIdempotency:
    def test_the_same_key_repeats_the_stored_answer_without_duplicating(
        self, editor, django_capture_on_commit_callbacks
    ) -> None:
        manuscript = reviewed(editor)
        body = {"decision": "ACCEPTED"}
        first = post_verdict(editor, manuscript, body, callbacks=django_capture_on_commit_callbacks)

        # El reintento llega con el ETag viejo: la clave manda.
        second = post_verdict(editor, manuscript, body, callbacks=django_capture_on_commit_callbacks)

        assert first.status_code == 201 and second.status_code == 201
        assert second["Idempotent-Replayed"] == "true"
        assert second.json() == first.json()
        assert Verdict.objects.count() == 1 and CatalogEntry.objects.count() == 1
        assert AuditLog.objects.filter(action="VERDICT_REGISTERED").count() == 1

    def test_the_same_key_with_another_decision_answers_409(self, editor) -> None:
        manuscript = reviewed(editor, recommendation="REJECT")
        post_verdict(editor, manuscript, {"decision": "ACCEPTED", "justification": "Revisado."})

        response = post_verdict(
            editor, manuscript, {"decision": "REJECTED", "justification": "Otra."}
        )

        assert response.status_code == 409 and error_code(response) == "STATE_CONFLICT"
        assert response.json()["error"]["details"] == {
            "idempotency": "KEY_REUSED_WITH_DIFFERENT_REQUEST"
        }
        assert Verdict.objects.count() == 1

    def test_a_new_key_after_a_registered_verdict_answers_409(self, editor) -> None:
        manuscript = reviewed(editor)
        post_verdict(editor, manuscript, {"decision": "ACCEPTED"}, key="primera")

        response = post_verdict(
            editor, manuscript, {"decision": "ACCEPTED"}, key="segunda", if_match='"1"'
        )

        assert response.status_code == 409 and error_code(response) == "VERDICT_CONFLICT"
        assert Verdict.objects.count() == 1

    def test_keys_do_not_cross_manuscripts(self, editor) -> None:
        first, second = reviewed(editor), reviewed(editor)

        one = post_verdict(editor, first, {"decision": "ACCEPTED"}, key="compartida")
        two = post_verdict(editor, second, {"decision": "ACCEPTED"}, key="compartida")

        assert one.status_code == two.status_code == 201
        assert Verdict.objects.count() == 2


class TestPreconditions:
    def test_without_a_final_evaluation_it_is_blocked(self, editor) -> None:
        manuscript = reviewed(editor, final=False)

        response = post_verdict(editor, manuscript, {"decision": "ACCEPTED"})

        assert response.status_code == 409 and error_code(response) == "STATE_CONFLICT"
        assert not Verdict.objects.exists()

    def test_a_withdrawn_manuscript_answers_409_and_is_audited(self, editor) -> None:
        manuscript = reviewed(editor)
        Manuscript.objects.filter(pk=manuscript.pk).update(
            is_active=False, withdrawn_at=timezone.now()
        )

        response = post_verdict(editor, manuscript, {"decision": "ACCEPTED"})

        assert response.status_code == 409 and error_code(response) == "STATE_CONFLICT"
        assert not Verdict.objects.exists() and not CatalogEntry.objects.exists()
        assert AuditLog.objects.get(action="VERDICT_REGISTERED").result == "FAILURE"

    def test_an_editor_with_conflict_is_blocked_with_403_and_audited(self) -> None:
        both = actor("AUTHOR", "EDITOR")
        manuscript = reviewed(both, owner=both)

        response = post_verdict(both, manuscript, {"decision": "ACCEPTED"})

        assert response.status_code == 403 and error_code(response) == "FORBIDDEN"
        assert not Verdict.objects.exists()
        denied = AuditLog.objects.get(action="VERDICT_REGISTERED")
        assert denied.result == "DENIED" and denied.actor_id == both.pk

    def test_a_coauthor_editor_is_blocked_too(self, editor) -> None:
        both = actor("AUTHOR", "EDITOR")
        manuscript = reviewed(editor)
        ManuscriptAuthorFactory(manuscript=manuscript, user=both, author_order=2)

        response = post_verdict(both, manuscript, {"decision": "ACCEPTED"})

        assert response.status_code == 403
        assert not Verdict.objects.exists()

    def test_the_conflicted_editor_cannot_read_the_history_or_evaluations(self) -> None:
        both = actor("AUTHOR", "EDITOR")
        manuscript = reviewed(both, owner=both)

        assert client_for(both).get(verdicts_url(manuscript)).status_code == 404
        assert client_for(both).get(evaluations_url(manuscript)).status_code == 404


class TestAtomicity:
    def test_a_failing_audit_answers_503_and_publishes_nothing(
        self, editor, monkeypatch
    ) -> None:
        manuscript = reviewed(editor)

        def fail(**kwargs):
            raise AuditUnavailable("sin auditoría")

        monkeypatch.setattr(AuditService, "record", staticmethod(fail))
        response = post_verdict(editor, manuscript, {"decision": "ACCEPTED"})

        assert response.status_code == 503 and error_code(response) == "AUDIT_UNAVAILABLE"
        assert not Verdict.objects.exists() and not CatalogEntry.objects.exists()
        version = manuscript.versions.get()
        assert not catalog_path(f"{manuscript.pk}/{version.pk}.pdf").exists()
        assert Manuscript.objects.get(pk=manuscript.pk).status == "UNDER_REVIEW"

    def test_a_failed_attempt_does_not_consume_the_key(self, editor, monkeypatch) -> None:
        manuscript = reviewed(editor)
        original = AuditService.record

        def fail(**kwargs):
            raise AuditUnavailable("sin auditoría")

        monkeypatch.setattr(AuditService, "record", staticmethod(fail))
        assert post_verdict(editor, manuscript, {"decision": "ACCEPTED"}).status_code == 503
        monkeypatch.setattr(AuditService, "record", staticmethod(original))

        retry = post_verdict(editor, manuscript, {"decision": "ACCEPTED"})

        assert retry.status_code == 201 and "Idempotent-Replayed" not in retry
        assert Verdict.objects.count() == 1


class TestVerdictHistory:
    def test_lists_the_registered_verdicts(
        self, editor, django_capture_on_commit_callbacks
    ) -> None:
        manuscript = reviewed(editor, recommendation="REQUIRES_CORRECTIONS")
        post_verdict(
            editor,
            manuscript,
            {"decision": "REQUIRES_CORRECTIONS", "observations": "Corregir."},
            callbacks=django_capture_on_commit_callbacks,
        )

        response = client_for(editor).get(verdicts_url(manuscript))

        rows = results(response)
        assert response.status_code == 200 and len(rows) == 1
        assert rows[0]["decision"] == "REQUIRES_CORRECTIONS"
        assert rows[0]["observations"] == "Corregir."
        assert rows[0]["version_number"] == 1 and rows[0]["editor"]["id"] == str(editor.pk)

    def test_is_empty_before_any_verdict(self, editor) -> None:
        manuscript = reviewed(editor)

        assert results(client_for(editor).get(verdicts_url(manuscript))) == []

    @pytest.mark.parametrize("method", ["put", "patch", "delete"])
    def test_a_verdict_can_never_be_edited_or_deleted(self, editor, method) -> None:
        manuscript = reviewed(editor)
        post_verdict(editor, manuscript, {"decision": "ACCEPTED"})
        verdict = Verdict.objects.get()

        for url in (verdicts_url(manuscript), f"{verdicts_url(manuscript)}{verdict.pk}/"):
            response = getattr(client_for(editor), method)(
                url, {"decision": "REJECTED", "justification": "x"}, format="json"
            )
            assert response.status_code in (404, 405)

        verdict.refresh_from_db()
        assert verdict.decision == "ACCEPTED"

    def test_evaluations_cannot_be_written_here(self, editor) -> None:
        manuscript = reviewed(editor)

        for method in ("post", "put", "patch", "delete"):
            response = getattr(client_for(editor), method)(
                evaluations_url(manuscript), {}, format="json"
            )
            assert response.status_code == 405


class TestEvaluations:
    def test_lists_the_final_evaluation_with_reviewer_identity_and_confidential_notes(
        self, editor
    ) -> None:
        manuscript = reviewed(
            editor,
            evaluation={"confidential_comments": "Solo para el Editor.", "conflict_declared": True},
        )
        reviewer = Evaluation.objects.get(manuscript=manuscript).reviewer

        response = client_for(editor).get(evaluations_url(manuscript))

        (row,) = results(response)
        assert response.status_code == 200
        assert row["reviewer"]["email"] == reviewer.email
        assert row["reviewer"]["full_name"] == reviewer.get_full_name()
        assert row["confidential_comments"] == "Solo para el Editor."
        assert row["comments_for_author"] == "Comentarios para el autor."
        assert row["recommendation"] == "ACCEPT" and row["status"] == "FINAL"
        assert [row[f"{name}_score"] for name in
                ("originality", "methodology", "clarity", "relevance", "ethics")] == [4, 4, 4, 4, 5]
        assert row["version_number"] == 1 and row["conflict_declared"] is True

    def test_drafts_are_private_and_never_listed(self, editor) -> None:
        manuscript = reviewed(editor, final=False)

        assert results(client_for(editor).get(evaluations_url(manuscript))) == []

    def test_lists_the_evaluations_of_every_version(self, editor) -> None:
        manuscript = reviewed(editor)
        second_version = ManuscriptVersionFactory(
            manuscript=manuscript,
            submitted_by=manuscript.created_by,
            version_number=2,
            round_number=1,
        )
        from apps.reviews.models import Assignment

        Assignment.objects.filter(manuscript=manuscript).update(status="COMPLETED")
        second_assignment = make_assignment(manuscript, make_reviewer(), editor, version=second_version)
        Evaluation.objects.create(
            assignment=second_assignment,
            manuscript=manuscript,
            version=second_version,
            reviewer=second_assignment.reviewer,
            status="FINAL",
            recommendation="ACCEPT",
            comments_for_author="Segunda ronda.",
            originality_score=5,
            methodology_score=5,
            clarity_score=5,
            relevance_score=5,
            ethics_score=5,
            submitted_at=timezone.now(),
        )

        rows = results(client_for(editor).get(evaluations_url(manuscript)))

        assert [row["version_number"] for row in rows] == [1, 2]

    def test_the_author_never_receives_the_reviewer_or_confidential_notes(self, editor) -> None:
        owner = actor("AUTHOR")
        manuscript = reviewed(
            editor, owner=owner, evaluation={"confidential_comments": "Solo para el Editor."}
        )

        for path in (
            evaluations_url(manuscript),
            verdicts_url(manuscript),
            f"/api/manuscripts/{manuscript.pk}/",
        ):
            response = client_for(owner).get(path)
            assert "Solo para el Editor." not in response.content.decode()
        assert client_for(owner).get(evaluations_url(manuscript)).status_code == 403
        assert client_for(owner).get(verdicts_url(manuscript)).status_code == 403
