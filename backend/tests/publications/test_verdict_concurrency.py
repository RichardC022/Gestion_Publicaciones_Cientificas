"""Real concurrency on the verdict flow (TSK-53).

Requests run in parallel threads, each with its own database connection,
released together by a barrier. They check the guarantees the manuscript
lock, the partial unique index of verdicts and the idempotency lock give:

* two simultaneous verdicts register only one and publish once;
* the same ``Idempotency-Key`` sent twice at once answers both, creates
  one verdict and marks the second as a replay;
* a withdrawal racing a verdict never leaves a partial result.
"""

from __future__ import annotations

import pytest
from django.core.management import call_command

from apps.audit.models import AuditLog
from apps.publications.models import CatalogEntry, Manuscript, Verdict
from apps.publications.services.storage import catalog_root
from tests.parallel import api_task, run_parallel, statuses
from tests.publications.test_lifecycle import assert_audit_chain_intact
from tests.publications.test_manuscript_api import actor, client_for, error_code
from tests.publications.test_verdicts import reviewed

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def seeded_roles(db) -> None:
    call_command("seed_roles", verbosity=0)


@pytest.fixture(autouse=True)
def media_root(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    return tmp_path


def verdict_task(user, manuscript, body, *, key, if_match='"0"'):
    return api_task(
        user,
        lambda client: client.post(
            f"/api/editor/manuscripts/{manuscript.pk}/verdicts/",
            body,
            format="json",
            HTTP_IDEMPOTENCY_KEY=key,
            HTTP_IF_MATCH=if_match,
        ),
    )


def public_files() -> list:
    return sorted(catalog_root().rglob("*.pdf")) if catalog_root().exists() else []


class TestSimultaneousVerdicts:
    def test_only_one_verdict_is_registered_and_published_once(self) -> None:
        editor = actor("EDITOR")
        manuscript = reviewed(editor)
        body = {"decision": "ACCEPTED"}

        responses = run_parallel(
            [
                verdict_task(editor, manuscript, body, key="carrera-1"),
                verdict_task(editor, manuscript, body, key="carrera-2"),
            ]
        )

        assert statuses(responses) == [201, 409]
        loser = next(r for r in responses if r.status_code == 409)
        assert error_code(loser) == "VERDICT_CONFLICT"
        assert Verdict.objects.filter(manuscript=manuscript).count() == 1
        assert CatalogEntry.objects.filter(manuscript=manuscript, is_active=True).count() == 1
        assert len(public_files()) == 1
        assert AuditLog.objects.filter(action="VERDICT_REGISTERED", result="SUCCESS").count() == 1
        assert Manuscript.objects.get(pk=manuscript.pk).lock_version == 1
        assert_audit_chain_intact()

    def test_two_editors_with_opposite_decisions_leave_one_decision(self) -> None:
        first, second = actor("EDITOR"), actor("EDITOR")
        manuscript = reviewed(first)

        responses = run_parallel(
            [
                verdict_task(first, manuscript, {"decision": "ACCEPTED"}, key="acepta"),
                verdict_task(
                    second,
                    manuscript,
                    {"decision": "REJECTED", "justification": "Se aparta del Revisor."},
                    key="rechaza",
                ),
            ]
        )

        assert statuses(responses) == [201, 409]
        verdict = Verdict.objects.get(manuscript=manuscript)
        manuscript.refresh_from_db()
        assert manuscript.status == {"ACCEPTED": "ACCEPTED", "REJECTED": "REJECTED"}[verdict.decision]
        # Publicado si y solo si fue aceptado.
        assert CatalogEntry.objects.filter(manuscript=manuscript).count() == (
            1 if verdict.decision == "ACCEPTED" else 0
        )
        assert len(public_files()) == CatalogEntry.objects.count()
        assert_audit_chain_intact()


class TestSameIdempotencyKey:
    def test_both_requests_are_answered_and_one_verdict_exists(self) -> None:
        editor = actor("EDITOR")
        manuscript = reviewed(editor)
        task = verdict_task(editor, manuscript, {"decision": "ACCEPTED"}, key="misma-clave")

        responses = run_parallel([task, task])

        assert statuses(responses) == [201, 201]
        assert sum("Idempotent-Replayed" in r for r in responses) == 1
        first, second = responses
        assert first.json() == second.json()
        assert Verdict.objects.count() == 1 and CatalogEntry.objects.count() == 1
        assert len(public_files()) == 1
        assert AuditLog.objects.filter(action="VERDICT_REGISTERED").count() == 1
        assert_audit_chain_intact()


class TestWithdrawalRacingAVerdict:
    def test_the_result_is_never_partial(self) -> None:
        owner, editor = actor("AUTHOR"), actor("EDITOR")
        manuscript = reviewed(editor, owner=owner)

        withdraw = api_task(
            owner,
            lambda client: client.post(
                f"/api/manuscripts/{manuscript.pk}/withdraw/",
                {"reason": "El autor retira el trabajo."},
                format="json",
            ),
        )
        withdrawn, judged = run_parallel(
            [withdraw, verdict_task(editor, manuscript, {"decision": "ACCEPTED"}, key="carrera")]
        )

        assert withdrawn.status_code == 200
        assert Manuscript.objects.get(pk=manuscript.pk).is_active is False
        if judged.status_code == 201:
            assert Verdict.objects.filter(manuscript=manuscript).count() == 1
            assert CatalogEntry.objects.filter(manuscript=manuscript).count() == 1
        else:
            assert judged.status_code == 409 and error_code(judged) == "STATE_CONFLICT"
            assert not Verdict.objects.exists() and not CatalogEntry.objects.exists()
            assert public_files() == []
            attempt = AuditLog.objects.get(action="VERDICT_REGISTERED")
            assert attempt.result == "FAILURE"
        assert_audit_chain_intact()

    def test_withdrawing_an_accepted_manuscript_retires_it_from_the_catalog(self) -> None:
        owner, editor = actor("AUTHOR"), actor("EDITOR")
        manuscript = reviewed(editor, owner=owner)
        assert verdict_task(editor, manuscript, {"decision": "ACCEPTED"}, key="acepta")().status_code == 201

        response = client_for(owner).post(
            f"/api/manuscripts/{manuscript.pk}/withdraw/",
            {"reason": "Retiro tras la aceptación."},
            format="json",
        )

        assert response.status_code == 200
        entry = CatalogEntry.objects.get(manuscript=manuscript)
        assert entry.is_active is False and entry.unpublished_at is not None
        assert public_files() == []
