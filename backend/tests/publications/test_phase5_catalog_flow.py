"""Catalog and correction over a whole editorial cycle (TSK-79, HU-18, HU-19, CA-HU-13-12).

Acceptance criteria: the catalog returns only accepted, active articles and
retires one right after its withdrawal; and the correction authorization is
consumed once, with both decisions kept in the history and in the audit.
The cycle runs through the real endpoints of every role.
"""

from __future__ import annotations

import pytest

from apps.audit.models import AuditLog
from apps.publications.models import CatalogEntry, StatusEvent, Verdict, VerdictCorrection
from apps.publications.services.storage import catalog_path
from tests.phase5 import (
    AUTHOR_TOKENS,
    EVALUATION,
    REVIEWER_TOKENS,
    TITLE,
    Lifecycle,
    anonymous,
)
from tests.publications.test_lifecycle import assert_audit_chain_intact
from tests.publications.test_manuscript_api import client_for
from tests.publications.test_submission import media_root, seeded_roles, submit  # noqa: F401

pytestmark = pytest.mark.django_db

CATALOG = "/api/catalog/"


@pytest.fixture
def flow(django_capture_on_commit_callbacks, submit) -> Lifecycle:  # noqa: F811
    return Lifecycle.create(django_capture_on_commit_callbacks, submit)


def listed_codes(**params) -> list[str]:
    return [row["code"] for row in anonymous().get(CATALOG, params).json()["results"]]


class TestOnlyAcceptedAndActive:
    def test_the_article_appears_exactly_when_it_is_accepted(self, flow) -> None:
        manuscript = flow.submit_manuscript()
        assert listed_codes() == []

        flow.start_review()
        assert listed_codes() == []

        flow.evaluate()
        assert listed_codes() == []

        assert flow.judge({"decision": "ACCEPTED"}, "acepta-1").status_code == 201
        assert listed_codes() == [manuscript.code]

    def test_a_rejected_manuscript_never_appears(self, flow) -> None:
        manuscript = flow.submit_manuscript()
        flow.start_review()
        flow.evaluate()

        assert flow.judge({"decision": "REJECTED", "justification": "No cumple el alcance."}, "r-1").status_code == 201

        assert listed_codes() == []
        assert anonymous().get(f"{CATALOG}{manuscript.code}/").status_code == 404
        assert anonymous().get(f"{CATALOG}{manuscript.code}/document/").status_code == 404

    def test_a_manuscript_that_requires_corrections_does_not_appear(self, flow) -> None:
        manuscript = flow.submit_manuscript()
        flow.start_review()
        flow.evaluate()

        flow.judge({"decision": "REQUIRES_CORRECTIONS", "observations": "Ampliar la metodología.",
                    "justification": "Se aparta de la recomendación."}, "c-1")

        assert listed_codes() == [] and anonymous().get(f"{CATALOG}{manuscript.code}/").status_code == 404

    def test_the_search_finds_the_article_by_title_and_author(self, flow) -> None:
        manuscript = flow.accepted()

        assert listed_codes(search="glaciares") == [manuscript.code]
        assert listed_codes(search="Quizhpe") == [manuscript.code]
        assert listed_codes(search="area inexistente xyz") == []
        assert listed_codes(area="Agronomía") == [manuscript.code]

    def test_the_public_page_shows_authors_but_never_the_review(self, flow) -> None:
        manuscript = flow.accepted()

        response = anonymous().get(f"{CATALOG}{manuscript.code}/")
        text = response.content.decode() + anonymous().get(CATALOG).content.decode()

        assert response.status_code == 200 and response.json()["title"] == TITLE
        assert "Quizhpe" in text
        for secret in (*REVIEWER_TOKENS, EVALUATION["confidential_comments"],
                       EVALUATION["comments_for_author"], "recommendation", "assignment", "AUDIT"):
            assert secret not in text
        assert "marcela.autora" not in text


class TestWithdrawalRetiresImmediately:
    def test_everything_public_disappears_with_the_withdrawal(self, flow) -> None:
        manuscript = flow.accepted()
        entry = CatalogEntry.objects.get(manuscript=manuscript)
        copy = catalog_path(entry.public_file_path)
        assert copy.is_file() and listed_codes() == [manuscript.code]

        assert flow.withdraw().status_code == 200

        assert listed_codes() == [] and listed_codes(search="glaciares") == []
        assert anonymous().get(f"{CATALOG}{manuscript.code}/").status_code == 404
        assert anonymous().get(f"{CATALOG}{manuscript.code}/document/").status_code == 410
        entry.refresh_from_db()
        assert entry.is_active is False and entry.unpublished_at is not None
        assert not copy.exists()

    def test_the_withdrawal_keeps_the_history_and_the_original(self, flow, media_root) -> None:  # noqa: F811
        manuscript = flow.accepted()
        flow.withdraw()

        manuscript.refresh_from_db()
        assert manuscript.is_active is False and manuscript.status == "ACCEPTED"
        assert Verdict.objects.filter(manuscript=manuscript).count() == 1
        assert (media_root / "private").exists()
        assert manuscript.versions.count() == 1
        assert AuditLog.objects.filter(action="MANUSCRIPT_WITHDRAWN").count() == 1
        assert_audit_chain_intact()

    def test_every_public_download_is_audited(self, flow) -> None:
        manuscript = flow.accepted()
        url = f"{CATALOG}{manuscript.code}/document/"

        first, second = anonymous().get(url), anonymous().get(url)

        assert first.status_code == second.status_code == 200
        assert first["X-Accel-Redirect"].startswith("/_catalog/")
        assert AuditLog.objects.filter(action="CATALOG_DOCUMENT_DOWNLOADED").count() == 2


class TestCorrectionCycle:
    def test_rejected_then_accepted_through_every_role(self, flow) -> None:
        manuscript = flow.submit_manuscript()
        flow.start_review()
        flow.evaluate()
        assert flow.judge({"decision": "REJECTED", "justification": "Primera lectura: no cumple."}, "r-1").status_code == 201
        original = manuscript.verdicts.get()
        assert listed_codes() == []

        # El Administrador habilita la corrección; el Editor la ve y la consume.
        assert flow.authorize_correction(original.pk).status_code == 201
        detail = client_for(flow.editor).get(f"/api/editor/submissions/{manuscript.pk}/").json()
        assert detail["correction_authorization"]["verdict_id"] == str(original.pk)
        corrected = flow.judge({"decision": "ACCEPTED"}, "r-2")

        assert corrected.status_code == 201, corrected.content
        assert corrected.json()["verdict"]["previous_verdict"] == str(original.pk)
        assert listed_codes() == [manuscript.code]
        assert anonymous().get(f"{CATALOG}{manuscript.code}/document/").status_code == 200

    def test_the_authorization_is_consumed_only_once(self, flow) -> None:
        manuscript = flow.submit_manuscript()
        flow.start_review()
        flow.evaluate()
        flow.judge({"decision": "REJECTED", "justification": "Primera lectura: no cumple."}, "r-1")
        original = manuscript.verdicts.get()
        flow.authorize_correction(original.pk)
        assert flow.judge({"decision": "ACCEPTED"}, "r-2").status_code == 201

        again = flow.judge({"decision": "REJECTED", "justification": "Otra vez."}, "r-3")

        assert again.status_code == 409
        authorization = VerdictCorrection.objects.get()
        assert authorization.is_active is False and authorization.consumed_by_verdict_id is not None
        assert Verdict.objects.filter(manuscript=manuscript).count() == 2
        assert flow.authorize_correction(original.pk, key="otra").status_code == 409

    def test_both_decisions_stay_in_the_history_and_in_the_audit(self, flow) -> None:
        manuscript = flow.submit_manuscript()
        flow.start_review()
        flow.evaluate()
        flow.judge({"decision": "REJECTED", "justification": "Primera lectura: no cumple."}, "r-1")
        original = manuscript.verdicts.get()
        flow.authorize_correction(original.pk)
        flow.judge({"decision": "ACCEPTED"}, "r-2")

        history = client_for(flow.editor).get(f"/api/editor/manuscripts/{manuscript.pk}/verdicts/").json()["results"]
        newest = manuscript.verdicts.latest("created_at")
        assert [row["decision"] for row in history] == ["REJECTED", "ACCEPTED"]
        assert history[0]["justification"] == "Primera lectura: no cumple."  # el original, intacto
        status_path = [e.to_status for e in StatusEvent.objects.filter(manuscript=manuscript).order_by("id")]
        assert status_path[-2:] == ["REJECTED", "ACCEPTED"]
        corrected = AuditLog.objects.get(action="VERDICT_CORRECTED")
        assert corrected.details["previous_verdict_id"] == str(original.pk)
        assert corrected.details["verdict_id"] == str(newest.pk)
        assert [a.action for a in AuditLog.objects.filter(action__startswith="VERDICT_").order_by("id")] == [
            "VERDICT_REGISTERED", "VERDICT_CORRECTION_AUTHORIZED", "VERDICT_CORRECTED",
        ]
        assert_audit_chain_intact()

    def test_the_administrator_never_reaches_the_manuscript_in_the_cycle(self, flow) -> None:
        manuscript = flow.accepted()
        flow.authorize_correction(manuscript.verdicts.get().pk)
        client = client_for(flow.admin)

        assert client.get(f"/api/manuscripts/{manuscript.pk}/").status_code in (403, 404)
        assert client.get(f"/api/editor/manuscripts/{manuscript.pk}/evaluations/").status_code == 403
        assert client.get(f"/api/manuscripts/{manuscript.pk}/versions/").status_code in (403, 404)
        body = client.post(
            f"/api/admin/verdicts/{manuscript.verdicts.get().pk}/authorize-correction/",
            {"reason": "Un motivo suficientemente largo."}, format="json", HTTP_IDEMPOTENCY_KEY="otra-clave",
        )
        assert body.status_code == 409
        for token in (*AUTHOR_TOKENS, *REVIEWER_TOKENS):
            assert token not in body.content.decode()
