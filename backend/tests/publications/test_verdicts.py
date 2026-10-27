"""Tests for the normal verdict flow (TSK-51).

Covers the acceptance criteria: ``ACCEPTED`` publishes in the catalog
synchronously, ``REJECTED`` publishes nothing and ``REQUIRES_CORRECTIONS``
opens the next round; a second normal verdict for the same version
answers ``409``; and if the public copy or the audit fail the verdict is
not committed.

Plus the contracts of the plan: the public copy is a new sanitized file
and never a link to the original, the round keeps the verdict that
opened it, the preconditions (final evaluation, no withdrawal, no
conflict of interest) are enforced, and refused attempts are audited.
"""

from __future__ import annotations

import os

import pikepdf
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.audit.services import AuditService, AuditUnavailable
from apps.publications.models import CatalogEntry, CorrectionRound, Manuscript, Verdict
from apps.publications.services.pdf import PdfInvalid, PdfService, sha256_of_file
from apps.publications.services.storage import catalog_path, catalog_root, private_path
from apps.publications.services.verdicts import register_verdict
from apps.publications.signals import verdict_registered
from apps.reviews.models import Evaluation
from config.exceptions import DomainError
from tests.factories import ManuscriptAuthorFactory
from tests.publications.pdf_factory import clean_pdf
from tests.publications.test_manuscript_api import actor, client_for
from tests.reviews.test_editor_api import make_assignment, make_reviewer, submitted

pytestmark = pytest.mark.django_db


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
def events():
    received: list[dict] = []

    def on_registered(sender, **kwargs):
        received.append(kwargs)

    verdict_registered.connect(on_registered, dispatch_uid="test-verdict")
    yield received
    verdict_registered.disconnect(dispatch_uid="test-verdict")


def reviewed(editor, *, recommendation="ACCEPT", final=True, owner=None, **overrides) -> Manuscript:
    """A manuscript under review with a real original PDF and a final evaluation."""
    manuscript = submitted(owner, status="UNDER_REVIEW", **overrides)
    version = manuscript.versions.get(version_number=1)
    original = private_path(version.original_file_path)
    original.parent.mkdir(parents=True)
    original.write_bytes(clean_pdf())
    assignment = make_assignment(manuscript, make_reviewer(), editor)
    values = {"status": "DRAFT"}
    if final:
        values = {
            "status": "FINAL",
            "recommendation": recommendation,
            "comments_for_author": "Comentarios para el autor.",
            "originality_score": 4,
            "methodology_score": 4,
            "clarity_score": 4,
            "relevance_score": 4,
            "ethics_score": 5,
            "submitted_at": timezone.now(),
        }
    Evaluation.objects.create(
        assignment=assignment,
        manuscript=manuscript,
        version=version,
        reviewer=assignment.reviewer,
        **values,
    )
    return manuscript


def register(editor, manuscript, decision, callbacks, **kwargs):
    with callbacks(execute=True):
        return register_verdict(
            manuscript_id=manuscript.pk, editor=editor, decision=decision, context={}, **kwargs
        )


def refused(editor, manuscript, decision, callbacks, **kwargs) -> DomainError:
    with pytest.raises(DomainError) as excinfo:
        register(editor, manuscript, decision, callbacks, **kwargs)
    return excinfo.value


def nothing_was_written(manuscript) -> None:
    manuscript.refresh_from_db()
    assert manuscript.status == "UNDER_REVIEW" and manuscript.lock_version == 0
    assert not Verdict.objects.exists() and not CatalogEntry.objects.exists()
    assert CorrectionRound.objects.filter(round_number__gt=0).count() == 0
    assert not catalog_root().exists() or not list(catalog_root().rglob("*.pdf"))


class TestAccepted:
    def test_publishes_in_the_catalog_synchronously(
        self, editor, django_capture_on_commit_callbacks
    ) -> None:
        manuscript = reviewed(editor)

        result = register(editor, manuscript, "ACCEPTED", django_capture_on_commit_callbacks)

        manuscript.refresh_from_db()
        assert manuscript.status == "ACCEPTED" and manuscript.accepted_at is not None
        assert manuscript.lock_version == 1 and manuscript.current_round == 0
        entry = CatalogEntry.objects.get(manuscript=manuscript)
        version = manuscript.versions.get()
        assert entry.is_active and entry.unpublished_at is None and entry.version == version
        assert entry.public_file_path == f"{manuscript.pk}/{version.pk}.pdf"
        assert result.catalog_entry == entry and result.opened_round is None
        assert catalog_path(entry.public_file_path).is_file()

    def test_the_public_copy_is_a_new_sanitized_file_not_a_link(
        self, editor, django_capture_on_commit_callbacks
    ) -> None:
        manuscript = reviewed(editor)
        original = private_path(manuscript.versions.get().original_file_path)
        original_hash = sha256_of_file(original)

        register(editor, manuscript, "ACCEPTED", django_capture_on_commit_callbacks)

        public = catalog_path(CatalogEntry.objects.get().public_file_path)
        assert public.stat().st_ino != original.stat().st_ino
        assert public.stat().st_nlink == 1 and original.stat().st_nlink == 1
        assert not public.is_symlink()
        assert sha256_of_file(original) == original_hash
        with pikepdf.open(public) as produced:
            assert "/Info" not in produced.trailer or not dict(produced.trailer["/Info"])

    def test_records_the_verdict_event_and_audit(
        self, editor, events, django_capture_on_commit_callbacks
    ) -> None:
        manuscript = reviewed(editor)

        result = register(editor, manuscript, "ACCEPTED", django_capture_on_commit_callbacks)

        verdict = result.verdict
        assert (verdict.editor, verdict.decision, verdict.previous_verdict) == (
            editor, "ACCEPTED", None,
        )
        assert verdict.evaluation == Evaluation.objects.get(manuscript=manuscript)
        event = manuscript.status_events.get(to_status="ACCEPTED")
        assert event.from_status == "UNDER_REVIEW" and event.actor == editor
        assert event.metadata["verdict_id"] == str(verdict.pk)
        audit = AuditLog.objects.get(action="VERDICT_REGISTERED")
        assert audit.result == "SUCCESS" and audit.actor_role == "EDITOR"
        assert audit.details["decision"] == "ACCEPTED"
        assert audit.details["catalog_entry_id"] == str(result.catalog_entry.pk)
        assert events == [
            {
                "signal": verdict_registered,
                "manuscript_id": manuscript.pk,
                "verdict_id": verdict.pk,
                "decision": "ACCEPTED",
                "editor_id": editor.pk,
            }
        ]


class TestRejected:
    def test_requires_a_justification_and_publishes_nothing(
        self, editor, django_capture_on_commit_callbacks
    ) -> None:
        manuscript = reviewed(editor, recommendation="REJECT")

        for blank in (None, "", "   "):
            error = refused(editor, manuscript, "REJECTED", django_capture_on_commit_callbacks,
                            justification=blank)
            assert error.error_code == "VALIDATION_ERROR"
            assert "justification" in error.error_details
        nothing_was_written(manuscript)

        result = register(editor, manuscript, "REJECTED", django_capture_on_commit_callbacks,
                          justification="  Metodología inválida.  ")

        manuscript.refresh_from_db()
        assert manuscript.status == "REJECTED" and manuscript.accepted_at is None
        assert result.verdict.justification == "Metodología inválida."
        assert not CatalogEntry.objects.exists() and result.catalog_entry is None
        assert manuscript.current_round == 0 and result.opened_round is None


class TestRequiresCorrections:
    def test_requires_observations(self, editor, django_capture_on_commit_callbacks) -> None:
        manuscript = reviewed(editor, recommendation="REQUIRES_CORRECTIONS")

        error = refused(editor, manuscript, "REQUIRES_CORRECTIONS",
                        django_capture_on_commit_callbacks, observations=" ")

        assert error.error_code == "VALIDATION_ERROR" and "observations" in error.error_details
        nothing_was_written(manuscript)

    def test_opens_the_next_round_and_keeps_the_verdict(
        self, editor, django_capture_on_commit_callbacks
    ) -> None:
        manuscript = reviewed(editor, recommendation="REQUIRES_CORRECTIONS")
        CorrectionRound.objects.create(manuscript=manuscript, round_number=0)

        result = register(editor, manuscript, "REQUIRES_CORRECTIONS",
                          django_capture_on_commit_callbacks, observations="Ampliar la sección 3.")

        manuscript.refresh_from_db()
        assert manuscript.status == "REQUIRES_CORRECTIONS" and manuscript.current_round == 1
        opened = CorrectionRound.objects.get(manuscript=manuscript, round_number=1)
        assert opened == result.opened_round
        assert opened.opened_by_verdict == result.verdict
        assert opened.closed_by_version is None and opened.closed_at is None
        assert not CatalogEntry.objects.exists()
        assert manuscript.status_events.get(to_status="REQUIRES_CORRECTIONS").metadata[
            "round_number"
        ] == 1

    def test_the_author_answers_with_a_new_version_that_closes_the_round(
        self, editor, django_capture_on_commit_callbacks
    ) -> None:
        owner = actor("AUTHOR")
        manuscript = reviewed(editor, owner=owner, recommendation="REQUIRES_CORRECTIONS")
        CorrectionRound.objects.create(manuscript=manuscript, round_number=0)
        register(editor, manuscript, "REQUIRES_CORRECTIONS",
                 django_capture_on_commit_callbacks, observations="Corregir.")

        response = client_for(owner).post(
            f"/api/manuscripts/{manuscript.pk}/versions/",
            {"file": SimpleUploadedFile("v2.pdf", clean_pdf(pages=2), "application/pdf")},
            format="multipart",
            HTTP_IDEMPOTENCY_KEY="nueva-version-1",
        )

        assert response.status_code == 201, response.content
        manuscript.refresh_from_db()
        round_one = CorrectionRound.objects.get(manuscript=manuscript, round_number=1)
        assert manuscript.status == "SUBMITTED" and manuscript.current_version == 2
        assert round_one.closed_by_version.version_number == 2
        assert round_one.opened_by_verdict is not None


class TestRecommendation:
    def test_departing_from_the_recommendation_requires_a_justification(
        self, editor, django_capture_on_commit_callbacks
    ) -> None:
        manuscript = reviewed(editor, recommendation="REJECT")

        error = refused(editor, manuscript, "ACCEPTED", django_capture_on_commit_callbacks)

        assert error.error_code == "VALIDATION_ERROR" and "justification" in error.error_details
        nothing_was_written(manuscript)

        result = register(editor, manuscript, "ACCEPTED", django_capture_on_commit_callbacks,
                          justification="El Revisor omitió el anexo.")

        assert result.verdict.justification == "El Revisor omitió el anexo."
        assert AuditLog.objects.get(action="VERDICT_REGISTERED").details[
            "departs_from_recommendation"
        ] is True

    def test_following_the_recommendation_needs_no_justification(
        self, editor, django_capture_on_commit_callbacks
    ) -> None:
        manuscript = reviewed(editor, recommendation="ACCEPT")

        result = register(editor, manuscript, "ACCEPTED", django_capture_on_commit_callbacks)

        assert result.verdict.justification is None
        assert AuditLog.objects.get(action="VERDICT_REGISTERED").details[
            "departs_from_recommendation"
        ] is False


class TestPreconditions:
    def test_a_second_normal_verdict_for_the_version_answers_409(
        self, editor, django_capture_on_commit_callbacks
    ) -> None:
        manuscript = reviewed(editor)
        register(editor, manuscript, "ACCEPTED", django_capture_on_commit_callbacks)

        error = refused(editor, manuscript, "REJECTED", django_capture_on_commit_callbacks,
                        justification="Otra decisión.")

        assert error.error_code == "VERDICT_CONFLICT" and error.status_code == 409
        assert Verdict.objects.count() == 1 and CatalogEntry.objects.count() == 1
        manuscript.refresh_from_db()
        assert manuscript.status == "ACCEPTED"

    def test_with_only_a_draft_evaluation_it_is_blocked(
        self, editor, django_capture_on_commit_callbacks
    ) -> None:
        manuscript = reviewed(editor, final=False)

        error = refused(editor, manuscript, "ACCEPTED", django_capture_on_commit_callbacks)

        assert error.error_code == "STATE_CONFLICT" and "evaluación" in str(error.detail)
        nothing_was_written(manuscript)

    def test_without_any_evaluation_it_is_blocked(
        self, editor, django_capture_on_commit_callbacks
    ) -> None:
        manuscript = submitted(status="UNDER_REVIEW")

        error = refused(editor, manuscript, "ACCEPTED", django_capture_on_commit_callbacks)

        assert error.error_code == "STATE_CONFLICT"

    @pytest.mark.parametrize("status", ["SUBMITTED", "REQUIRES_CORRECTIONS", "ACCEPTED", "REJECTED"])
    def test_only_a_manuscript_under_review_admits_a_verdict(
        self, editor, status, django_capture_on_commit_callbacks
    ) -> None:
        manuscript = reviewed(editor)
        Manuscript.objects.filter(pk=manuscript.pk).update(status=status)

        error = refused(editor, manuscript, "ACCEPTED", django_capture_on_commit_callbacks)

        assert error.error_code == "STATE_CONFLICT"
        assert not Verdict.objects.exists()

    def test_a_withdrawn_manuscript_answers_409_and_the_attempt_is_audited(
        self, editor, django_capture_on_commit_callbacks
    ) -> None:
        manuscript = reviewed(editor)
        Manuscript.objects.filter(pk=manuscript.pk).update(
            is_active=False, withdrawn_at=timezone.now()
        )

        error = refused(editor, manuscript, "ACCEPTED", django_capture_on_commit_callbacks)

        assert error.error_code == "STATE_CONFLICT" and error.status_code == 409
        assert not Verdict.objects.exists() and not CatalogEntry.objects.exists()
        attempt = AuditLog.objects.get(action="VERDICT_REGISTERED")
        assert attempt.result == "FAILURE" and attempt.actor_role == "EDITOR"
        assert attempt.entity_id == manuscript.pk

    @pytest.mark.parametrize("kind", ["registrant", "coauthor_account", "coauthor_email"])
    def test_an_editor_with_conflict_of_interest_is_blocked_and_audited(
        self, kind, django_capture_on_commit_callbacks
    ) -> None:
        both = actor("AUTHOR", "EDITOR")
        if kind == "registrant":
            manuscript = reviewed(both, owner=both)
        else:
            manuscript = reviewed(both)
            ManuscriptAuthorFactory(
                manuscript=manuscript,
                user=both if kind == "coauthor_account" else None,
                email=both.email.upper() if kind == "coauthor_email" else "otro@x.edu",
                author_order=2,
            )

        error = refused(both, manuscript, "ACCEPTED", django_capture_on_commit_callbacks)

        assert error.error_code == "FORBIDDEN" and error.status_code == 403
        nothing_was_written(manuscript)
        denied = AuditLog.objects.get(action="VERDICT_REGISTERED")
        assert denied.result == "DENIED" and denied.actor_id == both.pk

    def test_a_stale_lock_version_answers_409(
        self, editor, django_capture_on_commit_callbacks
    ) -> None:
        manuscript = reviewed(editor)

        error = refused(editor, manuscript, "ACCEPTED", django_capture_on_commit_callbacks,
                        expected_lock_version=7)

        assert error.error_code == "VERSION_CONFLICT"
        assert error.error_details == {"lock_version": 0}
        nothing_was_written(manuscript)

        register(editor, manuscript, "ACCEPTED", django_capture_on_commit_callbacks,
                 expected_lock_version=0)
        assert Verdict.objects.count() == 1

    def test_an_unknown_decision_is_rejected(
        self, editor, django_capture_on_commit_callbacks
    ) -> None:
        manuscript = reviewed(editor)

        error = refused(editor, manuscript, "MAYBE", django_capture_on_commit_callbacks)

        assert error.error_code == "VALIDATION_ERROR" and "decision" in error.error_details
        nothing_was_written(manuscript)


class TestAtomicity:
    def test_a_failing_public_copy_leaves_no_verdict(
        self, editor, monkeypatch, events, django_capture_on_commit_callbacks
    ) -> None:
        manuscript = reviewed(editor)

        def broken(self, source, destination):
            raise OSError("disco lleno")

        monkeypatch.setattr(PdfService, "sanitize", broken)
        error = refused(editor, manuscript, "ACCEPTED", django_capture_on_commit_callbacks)

        assert error.error_code == "STORAGE_UNAVAILABLE" and error.status_code == 503
        nothing_was_written(manuscript)
        failure = AuditLog.objects.get(action="VERDICT_REGISTERED")
        assert failure.result == "FAILURE" and failure.actor_role == "EDITOR"
        assert events == []

    def test_a_copy_that_cannot_be_sanitized_leaves_no_verdict(
        self, editor, monkeypatch, django_capture_on_commit_callbacks
    ) -> None:
        manuscript = reviewed(editor)

        def invalid(self, source, destination):
            raise PdfInvalid("No se pudo generar la copia sanitizada del PDF.")

        monkeypatch.setattr(PdfService, "sanitize", invalid)
        error = refused(editor, manuscript, "ACCEPTED", django_capture_on_commit_callbacks)

        assert error.error_code == "PDF_INVALID"
        nothing_was_written(manuscript)

    def test_a_failing_audit_leaves_no_verdict_and_removes_the_public_copy(
        self, editor, monkeypatch, events, django_capture_on_commit_callbacks
    ) -> None:
        manuscript = reviewed(editor)

        def fail(**kwargs):
            raise AuditUnavailable("sin auditoría")

        monkeypatch.setattr(AuditService, "record", staticmethod(fail))
        error = refused(editor, manuscript, "ACCEPTED", django_capture_on_commit_callbacks)

        assert error.error_code == "AUDIT_UNAVAILABLE" and error.status_code == 503
        nothing_was_written(manuscript)
        public = catalog_path(f"{manuscript.pk}/{manuscript.versions.get().pk}.pdf")
        assert not public.exists()
        assert events == []

    def test_a_failing_audit_also_reverts_a_correction_request(
        self, editor, monkeypatch, django_capture_on_commit_callbacks
    ) -> None:
        manuscript = reviewed(editor, recommendation="REQUIRES_CORRECTIONS")

        def fail(**kwargs):
            raise AuditUnavailable("sin auditoría")

        monkeypatch.setattr(AuditService, "record", staticmethod(fail))
        refused(editor, manuscript, "REQUIRES_CORRECTIONS",
                django_capture_on_commit_callbacks, observations="Corregir.")

        nothing_was_written(manuscript)
        manuscript.refresh_from_db()
        assert manuscript.current_round == 0

    def test_a_preexisting_file_is_never_overwritten_or_deleted(
        self, editor, django_capture_on_commit_callbacks
    ) -> None:
        manuscript = reviewed(editor)
        existing = catalog_path(f"{manuscript.pk}/{manuscript.versions.get().pk}.pdf")
        existing.parent.mkdir(parents=True)
        existing.write_bytes(b"contenido previo")

        error = refused(editor, manuscript, "ACCEPTED", django_capture_on_commit_callbacks)

        assert error.error_code == "STORAGE_UNAVAILABLE"
        assert existing.read_bytes() == b"contenido previo"
        manuscript.refresh_from_db()
        assert manuscript.status == "UNDER_REVIEW" and not Verdict.objects.exists()

    def test_no_notice_is_sent_for_a_refused_verdict(
        self, editor, events, django_capture_on_commit_callbacks
    ) -> None:
        manuscript = reviewed(editor, final=False)

        refused(editor, manuscript, "ACCEPTED", django_capture_on_commit_callbacks)

        assert events == []
