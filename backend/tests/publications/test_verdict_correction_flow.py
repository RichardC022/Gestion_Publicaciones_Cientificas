"""Tests for the editor's verdict that consumes a correction (TSK-78, CA-HU-13-12).

Acceptance criteria: without an active authorization a second verdict is a
``409`` even if the client sends ``previous_verdict_id``; the correction
keeps the original, does not change ``current_version`` and records
``VERDICT_CORRECTED`` with both identifiers; and if any step fails the
authorization is not consumed and the verdict is not created.
"""

from __future__ import annotations

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.audit.services import AuditService, AuditUnavailable
from apps.notifications.models import Notification
from apps.publications.models import (
    CatalogEntry,
    CorrectionRound,
    Manuscript,
    StatusEvent,
    Verdict,
    VerdictCorrection,
)
from apps.publications.services.corrections import authorize_correction
from apps.publications.services.pdf import PdfService
from apps.publications.services.storage import catalog_path, catalog_root
from apps.publications.services.verdicts import register_verdict
from tests.factories import ManuscriptVersionFactory
from tests.parallel import api_task, run_parallel, statuses
from tests.publications.test_lifecycle import assert_audit_chain_intact
from tests.publications.test_manuscript_api import actor, client_for, error_code
from tests.publications.test_verdicts import reviewed
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db

REASON = "El veredicto se registró sobre la evaluación equivocada."
JUSTIFICATION = "Justificación del veredicto original."
OBSERVATIONS = "Observaciones para el Autor."


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
def admin():
    return actor("ADMIN")


@pytest.fixture
def commits(django_capture_on_commit_callbacks):
    return django_capture_on_commit_callbacks


def decide(editor, manuscript, decision, commits, **texts):
    if decision == "REJECTED":
        texts.setdefault("justification", JUSTIFICATION)
    if decision == "REQUIRES_CORRECTIONS":
        texts.setdefault("observations", OBSERVATIONS)
        texts.setdefault("justification", JUSTIFICATION)
    with commits(execute=True):
        return register_verdict(
            manuscript_id=manuscript.pk, editor=editor, decision=decision, context={}, **texts
        )


def start(editor, decision, commits, **overrides) -> Verdict:
    """A manuscript decided once with ``decision``; its verdict is the latest."""
    manuscript = reviewed(editor, **overrides)
    return decide(editor, manuscript, decision, commits).verdict


def enable(admin, verdict, commits=None) -> VerdictCorrection:
    return authorize_correction(verdict_id=verdict.pk, admin=admin, reason=REASON, context={})


def post_verdict(user, manuscript, body, *, key="correccion-1", if_match=None):
    manuscript.refresh_from_db()
    return client_for(user).post(
        f"/api/editor/manuscripts/{manuscript.pk}/verdicts/",
        body,
        format="json",
        HTTP_IDEMPOTENCY_KEY=key,
        HTTP_IF_MATCH=if_match or f'"{manuscript.lock_version}"',
    )


def public_copy(manuscript) -> list:
    return sorted(catalog_root().rglob("*.pdf")) if catalog_root().exists() else []


class TestWithoutAuthorization:
    def test_a_second_verdict_is_a_409_even_with_previous_verdict_id(self, editor, commits) -> None:
        original = start(editor, "REJECTED", commits)

        response = post_verdict(
            editor,
            original.manuscript,
            {"decision": "ACCEPTED", "previous_verdict_id": str(original.pk)},
        )

        assert response.status_code == 409
        assert error_code(response) == "VERDICT_CONFLICT"
        assert Verdict.objects.count() == 1
        assert not CatalogEntry.objects.exists()

    def test_an_authorization_over_another_manuscript_does_not_help(self, editor, admin, commits) -> None:
        original = start(editor, "REJECTED", commits)
        other = start(editor, "REJECTED", commits)
        enable(admin, other)

        response = post_verdict(editor, original.manuscript, {"decision": "ACCEPTED"})

        assert response.status_code == 409 and Verdict.objects.filter(manuscript=original.manuscript).count() == 1

    def test_the_client_cannot_link_an_arbitrary_verdict(self, editor, admin, commits) -> None:
        original = start(editor, "REJECTED", commits)
        stranger = start(editor, "REJECTED", commits)
        enable(admin, original)

        response = post_verdict(
            editor, original.manuscript,
            {"decision": "ACCEPTED", "previous_verdict_id": str(stranger.pk)},
        )

        assert response.status_code == 201
        assert response.json()["verdict"]["previous_verdict"] == str(original.pk)


class TestConsumption:
    def test_rejected_becomes_accepted_and_is_published(self, editor, admin, commits) -> None:
        original = start(editor, "REJECTED", commits)
        manuscript = original.manuscript
        before = Verdict.objects.values().get(pk=original.pk)
        authorization = enable(admin, original)

        with commits(execute=True):
            response = post_verdict(editor, manuscript, {"decision": "ACCEPTED"})

        assert response.status_code == 201
        manuscript.refresh_from_db()
        new = Verdict.objects.get(previous_verdict=original)
        assert response.json()["verdict"]["id"] == str(new.pk)
        assert (manuscript.status, manuscript.current_version) == ("ACCEPTED", 1)
        assert manuscript.accepted_at is not None
        assert Verdict.objects.values().get(pk=original.pk) == before
        authorization.refresh_from_db()
        assert authorization.is_active is False and authorization.consumed_at is not None
        assert authorization.consumed_by_verdict_id == new.pk
        entry = CatalogEntry.objects.get(manuscript=manuscript, is_active=True)
        assert catalog_path(entry.public_file_path).is_file()
        assert APIClient().get(f"/api/catalog/{manuscript.code}/").status_code == 200

    def test_both_decisions_stay_in_the_history(self, editor, admin, commits) -> None:
        original = start(editor, "REJECTED", commits)
        enable(admin, original)
        with commits(execute=True):
            post_verdict(editor, original.manuscript, {"decision": "ACCEPTED"})

        listed = client_for(editor).get(f"/api/editor/manuscripts/{original.manuscript_id}/verdicts/").json()

        assert [row["decision"] for row in listed["results"]] == ["REJECTED", "ACCEPTED"]
        event = StatusEvent.objects.filter(manuscript=original.manuscript).latest("id")
        assert event.from_status == "REJECTED" and event.to_status == "ACCEPTED"
        assert event.metadata["previous_verdict_id"] == str(original.pk)

    def test_the_audit_event_names_both_verdicts(self, editor, admin, commits) -> None:
        original = start(editor, "REJECTED", commits)
        authorization = enable(admin, original)
        with commits(execute=True):
            post_verdict(editor, original.manuscript, {"decision": "ACCEPTED"})

        new = Verdict.objects.get(previous_verdict=original)
        event = AuditLog.objects.get(action="VERDICT_CORRECTED")
        assert event.actor_id == editor.pk and event.actor_role == "EDITOR" and event.result == "SUCCESS"
        assert event.details["verdict_id"] == str(new.pk)
        assert event.details["previous_verdict_id"] == str(original.pk)
        assert event.details["previous_decision"] == "REJECTED"
        assert event.details["correction_id"] == str(authorization.pk)
        assert AuditLog.objects.filter(action="VERDICT_REGISTERED").count() == 1
        assert_audit_chain_intact()

    def test_accepted_becomes_rejected_and_leaves_the_catalog(self, editor, admin, commits) -> None:
        original = start(editor, "ACCEPTED", commits)
        manuscript = original.manuscript
        entry = CatalogEntry.objects.get(manuscript=manuscript)
        copy = catalog_path(entry.public_file_path)
        assert copy.is_file()
        enable(admin, original)

        with commits(execute=True):
            response = post_verdict(
                editor, manuscript, {"decision": "REJECTED", "justification": "Se detectó un error grave."}
            )

        assert response.status_code == 201
        manuscript.refresh_from_db()
        entry.refresh_from_db()
        assert manuscript.status == "REJECTED" and manuscript.accepted_at is None
        assert entry.is_active is False and entry.unpublished_at is not None
        assert not copy.exists()
        client = APIClient()
        assert client.get(f"/api/catalog/{manuscript.code}/").status_code == 404
        # Ya no es un artículo aceptado: para el público no existe (el 410 es para los dados de baja).
        assert client.get(f"/api/catalog/{manuscript.code}/document/").status_code == 404

    def test_accepted_becomes_requires_corrections_and_opens_a_round(self, editor, admin, commits) -> None:
        original = start(editor, "ACCEPTED", commits)
        manuscript = original.manuscript
        enable(admin, original)

        with commits(execute=True):
            response = post_verdict(
                editor, manuscript, {"decision": "REQUIRES_CORRECTIONS", "observations": OBSERVATIONS,
                                     "justification": "Cambia la recomendación."},
            )

        assert response.status_code == 201
        manuscript.refresh_from_db()
        new = Verdict.objects.get(previous_verdict=original)
        assert (manuscript.status, manuscript.current_round, manuscript.current_version) == (
            "REQUIRES_CORRECTIONS", 1, 1,
        )
        assert response.json()["opened_round"] == 1
        assert CorrectionRound.objects.get(manuscript=manuscript, round_number=1).opened_by_verdict_id == new.pk
        assert not CatalogEntry.objects.filter(manuscript=manuscript, is_active=True).exists()
        assert public_copy(manuscript) == []

    def test_rejected_becomes_requires_corrections_and_opens_a_round(self, editor, admin, commits) -> None:
        original = start(editor, "REJECTED", commits)
        enable(admin, original)

        with commits(execute=True):
            response = post_verdict(
                editor, original.manuscript,
                {"decision": "REQUIRES_CORRECTIONS", "observations": OBSERVATIONS, "justification": "Se reconsidera."},
            )

        original.manuscript.refresh_from_db()
        assert response.status_code == 201 and original.manuscript.current_round == 1

    def test_correcting_a_pending_request_does_not_open_a_second_round(self, editor, admin, commits) -> None:
        original = start(editor, "REQUIRES_CORRECTIONS", commits, recommendation="REQUIRES_CORRECTIONS")
        manuscript = original.manuscript
        manuscript.refresh_from_db()
        assert manuscript.current_round == 1
        enable(admin, original)

        with commits(execute=True):
            response = post_verdict(
                editor, manuscript, {"decision": "REQUIRES_CORRECTIONS", "observations": "Observaciones corregidas."}
            )

        manuscript.refresh_from_db()
        assert response.status_code == 201 and response.json()["opened_round"] is None
        assert manuscript.current_round == 1
        assert list(CorrectionRound.objects.filter(manuscript=manuscript).values_list("round_number", flat=True)) == [1]

    def test_requires_corrections_becomes_accepted_without_a_new_round(self, editor, admin, commits) -> None:
        original = start(editor, "REQUIRES_CORRECTIONS", commits, recommendation="REQUIRES_CORRECTIONS")
        manuscript = original.manuscript
        enable(admin, original)

        with commits(execute=True):
            response = post_verdict(
                editor, manuscript, {"decision": "ACCEPTED", "justification": "La evaluación admite aceptación."}
            )

        manuscript.refresh_from_db()
        assert response.status_code == 201
        assert (manuscript.status, manuscript.current_round) == ("ACCEPTED", 1)
        assert CatalogEntry.objects.filter(manuscript=manuscript, is_active=True).exists()

    def test_reaccepting_after_a_retirement_restores_the_article(self, editor, admin, commits) -> None:
        original = start(editor, "ACCEPTED", commits)
        manuscript = original.manuscript
        enable(admin, original)
        with commits(execute=True):
            rejected = post_verdict(editor, manuscript, {"decision": "REJECTED", "justification": "Error grave."}, key="a")
        newest = Verdict.objects.get(pk=rejected.json()["verdict"]["id"])
        enable(admin, newest)

        with commits(execute=True):
            again = post_verdict(editor, manuscript, {"decision": "ACCEPTED", "justification": "Se revierte."}, key="b")

        assert again.status_code == 201
        entries = CatalogEntry.objects.filter(manuscript=manuscript)
        assert entries.count() == 2 and entries.filter(is_active=True).count() == 1
        assert catalog_path(entries.get(is_active=True).public_file_path).is_file()
        assert APIClient().get(f"/api/catalog/{manuscript.code}/").status_code == 200

    def test_a_leftover_public_file_does_not_block_a_new_acceptance(self, editor, admin, commits) -> None:
        original = start(editor, "ACCEPTED", commits)
        manuscript = original.manuscript
        entry = CatalogEntry.objects.get(manuscript=manuscript)
        enable(admin, original)
        with commits(execute=True):
            rejected = post_verdict(editor, manuscript, {"decision": "REJECTED", "justification": "Error grave."}, key="a")
        leftover = catalog_path(entry.public_file_path)
        leftover.parent.mkdir(parents=True, exist_ok=True)
        leftover.write_bytes(b"%PDF-1.7 sobrante")
        enable(admin, Verdict.objects.get(pk=rejected.json()["verdict"]["id"]))

        with commits(execute=True):
            again = post_verdict(editor, manuscript, {"decision": "ACCEPTED", "justification": "Se revierte."}, key="b")

        assert again.status_code == 201
        assert leftover.read_bytes() != b"%PDF-1.7 sobrante"

    def test_the_author_is_told_the_decision_was_corrected(self, editor, admin, commits) -> None:
        original = start(editor, "REJECTED", commits)
        enable(admin, original)
        with commits(execute=True):
            post_verdict(editor, original.manuscript, {"decision": "ACCEPTED"})

        notice = Notification.objects.get(
            recipient=original.manuscript.created_by, event_type="VERDICT_REGISTERED",
            payload__title__startswith="Decisión corregida", channel="PANEL",
        )
        assert JUSTIFICATION not in str(notice.payload) and REASON not in str(notice.payload)


class TestConsumedOnce:
    def test_a_second_correction_needs_a_new_authorization(self, editor, admin, commits) -> None:
        original = start(editor, "REJECTED", commits)
        enable(admin, original)
        with commits(execute=True):
            assert post_verdict(editor, original.manuscript, {"decision": "ACCEPTED"}, key="a").status_code == 201

        again = post_verdict(
            editor, original.manuscript, {"decision": "REJECTED", "justification": "Otra vez."}, key="b"
        )

        assert again.status_code == 409 and error_code(again) == "VERDICT_CONFLICT"
        assert Verdict.objects.count() == 2

    def test_the_same_key_replays_without_consuming_another(self, editor, admin, commits) -> None:
        original = start(editor, "REJECTED", commits)
        enable(admin, original)
        with commits(execute=True):
            first = post_verdict(editor, original.manuscript, {"decision": "ACCEPTED"}, key="igual")
        second = post_verdict(
            editor, original.manuscript, {"decision": "ACCEPTED"}, key="igual",
            if_match='"1"',
        )

        assert first.status_code == 201 and second.status_code == 201
        assert second["Idempotent-Replayed"] == "true"
        assert Verdict.objects.count() == 2

    def test_the_admin_can_authorize_again_over_the_new_verdict(self, editor, admin, commits) -> None:
        original = start(editor, "REJECTED", commits)
        enable(admin, original)
        with commits(execute=True):
            response = post_verdict(editor, original.manuscript, {"decision": "ACCEPTED"})
        newest = Verdict.objects.get(pk=response.json()["verdict"]["id"])

        assert enable(admin, newest).is_active


class TestAtomicity:
    def test_audit_failure_keeps_the_authorization_active(self, editor, admin, commits, monkeypatch) -> None:
        original = start(editor, "REJECTED", commits)
        authorization = enable(admin, original)
        before = (original.manuscript.status, Verdict.objects.count())

        def broken(**kwargs):
            raise AuditUnavailable("sin auditoría")

        monkeypatch.setattr(AuditService, "record", staticmethod(broken))
        response = post_verdict(editor, original.manuscript, {"decision": "ACCEPTED"})
        monkeypatch.undo()

        assert response.status_code == 503 and error_code(response) == "AUDIT_UNAVAILABLE"
        authorization.refresh_from_db()
        assert authorization.is_active and authorization.consumed_by_verdict_id is None
        assert (Manuscript.objects.get(pk=original.manuscript_id).status, Verdict.objects.count()) == before
        assert not CatalogEntry.objects.exists() and public_copy(original.manuscript) == []
        # El reintento con la auditoría restablecida sí consume la autorización.
        with commits(execute=True):
            assert post_verdict(editor, original.manuscript, {"decision": "ACCEPTED"}).status_code == 201

    def test_a_failing_public_copy_keeps_the_authorization_and_the_catalog(
        self, editor, admin, commits, monkeypatch
    ) -> None:
        original = start(editor, "REJECTED", commits)
        authorization = enable(admin, original)

        def broken(self, source, destination):
            raise OSError("disco lleno")

        monkeypatch.setattr(PdfService, "sanitize", broken)
        response = post_verdict(editor, original.manuscript, {"decision": "ACCEPTED"})
        monkeypatch.undo()

        assert response.status_code == 503 and error_code(response) == "STORAGE_UNAVAILABLE"
        authorization.refresh_from_db()
        assert authorization.is_active
        assert Verdict.objects.count() == 1 and not CatalogEntry.objects.exists()
        assert public_copy(original.manuscript) == []

    def test_a_later_version_invalidates_the_authorization(self, editor, admin, commits) -> None:
        original = start(editor, "REQUIRES_CORRECTIONS", commits, recommendation="REQUIRES_CORRECTIONS")
        authorization = enable(admin, original)
        ManuscriptVersionFactory(
            manuscript=original.manuscript, version_number=2, round_number=1,
            submitted_by=original.manuscript.created_by,
        )
        Manuscript.objects.filter(pk=original.manuscript_id).update(current_version=2)

        response = post_verdict(
            editor, original.manuscript, {"decision": "ACCEPTED", "justification": "Revierte la solicitud."}
        )

        assert response.status_code == 409 and error_code(response) == "CORRECTION_NOT_AUTHORIZED"
        authorization.refresh_from_db()
        assert authorization.is_active and Verdict.objects.count() == 1

    def test_a_withdrawn_manuscript_cannot_consume_it(self, editor, admin, commits) -> None:
        original = start(editor, "REJECTED", commits)
        authorization = enable(admin, original)
        Manuscript.objects.filter(pk=original.manuscript_id).update(
            is_active=False, withdrawn_at=timezone.now()
        )

        response = post_verdict(editor, original.manuscript, {"decision": "ACCEPTED"})

        assert response.status_code == 409
        authorization.refresh_from_db()
        assert authorization.is_active and Verdict.objects.count() == 1


class TestRules:
    def test_departing_from_the_recommendation_still_needs_a_justification(self, editor, admin, commits) -> None:
        original = start(editor, "REJECTED", commits)  # el Revisor recomendó aceptar
        authorization = enable(admin, original)
        # Misma regla que el veredicto normal: aceptar coincide con la recomendación; rechazar, no.
        response = post_verdict(editor, original.manuscript, {"decision": "REJECTED"})

        assert response.status_code == 400
        assert "justification" in response.json()["error"]["details"]
        authorization.refresh_from_db()
        assert authorization.is_active

    def test_requires_corrections_still_needs_observations(self, editor, admin, commits) -> None:
        original = start(editor, "REJECTED", commits)
        enable(admin, original)

        response = post_verdict(
            editor, original.manuscript, {"decision": "REQUIRES_CORRECTIONS", "justification": "Se reconsidera."}
        )

        assert response.status_code == 400 and "observations" in response.json()["error"]["details"]

    def test_an_editor_with_a_conflict_cannot_consume_it(self, admin, commits) -> None:
        from tests.factories import ManuscriptAuthorFactory

        editor = actor("EDITOR")
        original = start(editor, "REJECTED", commits)
        enable(admin, original)
        ManuscriptAuthorFactory(manuscript=original.manuscript, user=editor, author_order=9)

        response = post_verdict(editor, original.manuscript, {"decision": "ACCEPTED"})

        assert response.status_code == 403
        assert VerdictCorrection.objects.get().is_active

    def test_stale_if_match_is_still_a_409(self, editor, admin, commits) -> None:
        original = start(editor, "REJECTED", commits)
        authorization = enable(admin, original)

        response = post_verdict(editor, original.manuscript, {"decision": "ACCEPTED"}, if_match='"99"')

        assert response.status_code == 409 and error_code(response) == "VERSION_CONFLICT"
        authorization.refresh_from_db()
        assert authorization.is_active


class TestEditorSeesTheAuthorization:
    def test_submission_detail_shows_the_active_authorization(self, editor, admin, commits) -> None:
        original = start(editor, "REJECTED", commits)
        client = client_for(editor)
        url = f"/api/editor/submissions/{original.manuscript_id}/"
        assert client.get(url).json()["correction_authorization"] is None

        authorization = enable(admin, original)
        body = client.get(url).json()["correction_authorization"]

        assert body["id"] == str(authorization.pk) and body["verdict_id"] == str(original.pk)
        assert REASON not in client.get(url).content.decode()


@pytest.mark.django_db(transaction=True)
class TestSimultaneous:
    def test_two_editors_consume_the_authorization_once(self) -> None:
        first, second, admin = actor("EDITOR"), actor("EDITOR"), actor("ADMIN")
        manuscript = reviewed(first)
        original = register_verdict(
            manuscript_id=manuscript.pk, editor=first, decision="REJECTED",
            justification=JUSTIFICATION, context={},
        ).verdict
        authorize_correction(verdict_id=original.pk, admin=admin, reason=REASON, context={})

        def task(user, key):
            return api_task(
                user,
                lambda client: client.post(
                    f"/api/editor/manuscripts/{manuscript.pk}/verdicts/",
                    {"decision": "ACCEPTED"}, format="json",
                    HTTP_IDEMPOTENCY_KEY=key, HTTP_IF_MATCH='"1"',
                ),
            )

        responses = run_parallel([task(first, "a"), task(second, "b")])

        assert statuses(responses) == [201, 409]
        assert Verdict.objects.filter(manuscript=manuscript).count() == 2
        assert VerdictCorrection.objects.get().consumed_by_verdict_id is not None
        assert CatalogEntry.objects.filter(manuscript=manuscript, is_active=True).count() == 1
        assert AuditLog.objects.filter(action="VERDICT_CORRECTED").count() == 1
        assert_audit_chain_intact()
