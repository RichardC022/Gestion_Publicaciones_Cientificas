"""Tests for the formal submission and the creation of v1 / round 0 (TSK-35).

Covers the acceptance criteria:

1. The submission creates exactly ``v1`` and round 0, updates
   ``current_version`` and ``status=SUBMITTED`` and answers ``201``.
2. If the write, the sanitization or the audit fails, the transaction
   rolls back and the files this call created are removed.
3. ``metadata_sha256`` is computed over the canonical JSON — sorted
   keys, complete authors.

Plus the contracts of the plan: exact original, sanitized copy,
``metadata.json``, the domain signal sent only after the commit, the
consumed draft deleted then, and ``409`` for a repeated submission.
"""

from __future__ import annotations

import hashlib
import json
import stat
from uuid import uuid4

import pikepdf
import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.audit.services import AuditService, AuditUnavailable
from apps.publications.models import (
    CorrectionRound,
    Manuscript,
    ManuscriptAuthor,
    ManuscriptVersion,
    StatusEvent,
)
from apps.publications.services import versions as versions_module
from apps.publications.services.pdf import PdfInvalid, PdfService
from apps.publications.services.snapshot import canonical_json, metadata_sha256
from apps.publications.signals import manuscript_submitted
from tests.publications import pdf_factory as factory
from tests.publications.test_draft_file import draft_url, pdf_file
from tests.publications.test_manuscript_api import (
    URL,
    actor,
    client_for,
    create_payload,
    detail_url,
    error_code,
    owned_manuscript,
)

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def seeded_roles(db) -> None:
    call_command("seed_roles", verbosity=0)


@pytest.fixture(autouse=True)
def media_root(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    return tmp_path


@pytest.fixture
def submit(django_capture_on_commit_callbacks):
    """Submit through the API, running the after-commit callbacks."""

    def run(user, manuscript, key: str | None = None):
        # Cada intento usa una clave nueva salvo que la prueba fije una.
        with django_capture_on_commit_callbacks(execute=True):
            return client_for(user).post(
                submit_url(manuscript),
                format="json",
                HTTP_IDEMPOTENCY_KEY=key or uuid4().hex,
            )

    return run


def submit_url(manuscript) -> str:
    return f"{detail_url(manuscript)}submit/"


def ready_draft(owner, *, pdf: bytes | None = None, name: str = "Ana Lopez - articulo.pdf", **payload):
    """A draft created and uploaded through the API, ready to submit."""
    client = client_for(owner)
    created = client.post(URL, create_payload(owner, **payload), format="json")
    assert created.status_code == 201, created.content
    manuscript = Manuscript.objects.get(pk=created.json()["id"])
    uploaded = client.post(
        draft_url(manuscript),
        {"file": pdf_file(pdf, name=name)},
        format="multipart",
    )
    assert uploaded.status_code == 201, uploaded.content
    manuscript.refresh_from_db()
    return manuscript


def version_dir_of(media_root, manuscript, number: int = 1):
    return media_root / "private" / "manuscripts" / str(manuscript.pk) / f"v{number:04d}"


@pytest.fixture
def owner():
    return actor("AUTHOR")


class TestSubmission:
    def test_creates_exactly_v1_and_round_zero_and_answers_201(self, owner, submit) -> None:
        manuscript = ready_draft(owner)

        response = submit(owner, manuscript)

        assert response.status_code == 201
        body = response.json()
        assert body["code"] == manuscript.code and body["status"] == "SUBMITTED"
        assert (body["version_number"], body["round_number"]) == (1, 0)
        assert body["submitted_at"]
        assert ManuscriptVersion.objects.filter(manuscript=manuscript).count() == 1
        assert CorrectionRound.objects.filter(manuscript=manuscript).count() == 1

    def test_the_manuscript_moves_to_submitted_with_v1_and_a_new_etag(self, owner, submit) -> None:
        manuscript = ready_draft(owner)

        response = submit(owner, manuscript)

        manuscript.refresh_from_db()
        assert manuscript.status == "SUBMITTED"
        assert (manuscript.current_version, manuscript.current_round) == (1, 0)
        assert manuscript.lock_version == 1 and response["ETag"] == '"1"'

    def test_round_zero_is_closed_by_v1(self, owner, submit) -> None:
        manuscript = ready_draft(owner)

        submit(owner, manuscript)

        version = ManuscriptVersion.objects.get(manuscript=manuscript)
        round_zero = CorrectionRound.objects.get(manuscript=manuscript)
        assert round_zero.round_number == 0
        assert round_zero.closed_by_version == version and round_zero.closed_at
        assert version.round_number == 0 and version.submitted_by == owner

    def test_status_history_records_the_transition(self, owner, submit) -> None:
        manuscript = ready_draft(owner)

        submit(owner, manuscript)

        transitions = list(
            StatusEvent.objects.filter(manuscript=manuscript).values_list("from_status", "to_status")
        )
        assert transitions == [(None, "DRAFT"), ("DRAFT", "SUBMITTED")]
        event = StatusEvent.objects.filter(manuscript=manuscript).last()
        assert event.actor == owner and event.metadata == {"version_number": 1, "round_number": 0}

    def test_response_carries_the_integrity_seal_of_the_original(self, owner, submit) -> None:
        data = factory.clean_pdf(pages=2)
        manuscript = ready_draft(owner, pdf=data)

        body = submit(owner, manuscript).json()

        assert body["integrity_seal"] == f"sha256:{hashlib.sha256(data).hexdigest()}"


class TestStoredFiles:
    def test_original_is_the_exact_file_received(self, owner, submit, media_root) -> None:
        data = factory.pdf_with_identity()
        manuscript = ready_draft(owner, pdf=data, name="Ana Lopez.pdf")

        submit(owner, manuscript)

        version = ManuscriptVersion.objects.get(manuscript=manuscript)
        original = media_root / "private" / version.original_file_path
        assert original.read_bytes() == data
        assert version.original_sha256 == hashlib.sha256(data).hexdigest()
        assert version.original_size_bytes == len(data)
        assert version.original_filename == "Ana Lopez.pdf"

    def test_paths_are_relative_to_the_private_volume_and_use_only_ids(self, owner, submit) -> None:
        manuscript = ready_draft(owner, name="Ana Lopez - tesis.pdf")

        submit(owner, manuscript)

        version = ManuscriptVersion.objects.get(manuscript=manuscript)
        base = f"manuscripts/{manuscript.pk}/v0001"
        assert version.original_file_path == f"{base}/original.pdf"
        assert version.sanitized_file_path == f"{base}/sanitized.pdf"
        for leaked in ("Ana", "tesis", owner.email, manuscript.title):
            assert leaked not in version.original_file_path + version.sanitized_file_path

    def test_sanitized_copy_has_no_identity_and_matches_its_hash(self, owner, submit, media_root) -> None:
        manuscript = ready_draft(owner, pdf=factory.pdf_with_identity())

        submit(owner, manuscript)

        version = ManuscriptVersion.objects.get(manuscript=manuscript)
        sanitized = media_root / "private" / version.sanitized_file_path
        assert version.sanitized_sha256 == hashlib.sha256(sanitized.read_bytes()).hexdigest()
        assert version.sanitized_sha256 != version.original_sha256
        with pikepdf.open(sanitized) as pdf:
            assert "/Info" not in pdf.trailer and "/Annots" not in pdf.pages[0]
        assert b"Ana" not in sanitized.read_bytes()

    def test_directory_and_files_have_the_planned_permissions(self, owner, submit, media_root) -> None:
        manuscript = ready_draft(owner)

        submit(owner, manuscript)

        directory = version_dir_of(media_root, manuscript)
        assert stat.S_IMODE(directory.stat().st_mode) == 0o750
        assert sorted(p.name for p in directory.iterdir()) == [
            "metadata.json",
            "original.pdf",
            "sanitized.pdf",
        ]
        for child in directory.iterdir():
            assert stat.S_IMODE(child.stat().st_mode) == 0o640

    def test_original_is_an_independent_copy_of_the_draft(
        self, owner, django_capture_on_commit_callbacks, media_root
    ) -> None:
        manuscript = ready_draft(owner)
        draft_path = media_root / "private" / manuscript.draft_file_path

        with django_capture_on_commit_callbacks(execute=False):
            client_for(owner).post(
                submit_url(manuscript), format="json", HTTP_IDEMPOTENCY_KEY="clave-copia"
            )

        original = version_dir_of(media_root, manuscript) / "original.pdf"
        assert original.stat().st_ino != draft_path.stat().st_ino
        assert original.stat().st_nlink == 1 and draft_path.stat().st_nlink == 1


class TestMetadataSeal:
    def test_metadata_json_is_the_canonical_json_and_its_hash_is_sealed(self, owner, submit, media_root) -> None:
        manuscript = ready_draft(owner)

        submit(owner, manuscript)

        expected = (
            '{"abstract":"Resumen del estudio de campo.","area":"Agronomía",'
            '"authors":[{"affiliation":"Universidad Nacional de Loja",'
            f'"email":"{owner.email}","full_name":"{owner.get_full_name()}",'
            '"is_corresponding":true,"order":1}],'
            '"keywords":["clima","cultivos"],"language":"es",'
            '"title":"Efecto del clima en cultivos andinos"}'
        )
        version = ManuscriptVersion.objects.get(manuscript=manuscript)
        stored = (version_dir_of(media_root, manuscript) / "metadata.json").read_bytes()
        assert stored == expected.encode("utf-8")
        assert version.metadata_sha256 == hashlib.sha256(expected.encode("utf-8")).hexdigest()

    def test_snapshot_keeps_every_author_with_contact_and_order(self, owner, submit) -> None:
        coauthors = [
            {"full_name": "Luis Pérez", "email": "luis@otra.edu", "affiliation": "Otra U", "is_corresponding": False},
            {"full_name": "Eva Ríos", "email": "eva@otra.edu", "affiliation": "Otra U", "is_corresponding": False},
        ]
        authors = create_payload(owner)["authors"] + coauthors
        manuscript = ready_draft(owner, authors=authors)

        submit(owner, manuscript)

        snapshot = ManuscriptVersion.objects.get(manuscript=manuscript).metadata_snapshot
        assert [a["order"] for a in snapshot["authors"]] == [1, 2, 3]
        assert [a["email"] for a in snapshot["authors"]] == [owner.email, "luis@otra.edu", "eva@otra.edu"]
        assert {a["affiliation"] for a in snapshot["authors"]} == {"Universidad Nacional de Loja", "Otra U"}
        assert [a["is_corresponding"] for a in snapshot["authors"]] == [True, False, False]

    def test_snapshot_is_frozen_when_the_metadata_changes_later(self, owner, submit) -> None:
        manuscript = ready_draft(owner)
        submit(owner, manuscript)
        version = ManuscriptVersion.objects.get(manuscript=manuscript)

        Manuscript.objects.filter(pk=manuscript.pk).update(title="Cambiado después")

        version.refresh_from_db()
        assert version.metadata_snapshot["title"] == "Efecto del clima en cultivos andinos"
        assert version.metadata_sha256 == metadata_sha256(canonical_json(version.metadata_snapshot))

    def test_canonical_json_ignores_key_order_and_keeps_utf8(self) -> None:
        first = {"b": 1, "a": {"y": "López", "x": [1, 2]}}
        second = {"a": {"x": [1, 2], "y": "López"}, "b": 1}

        assert canonical_json(first) == canonical_json(second)
        assert canonical_json(first) == '{"a":{"x":[1,2],"y":"López"},"b":1}'
        assert metadata_sha256(canonical_json(first)) == metadata_sha256(canonical_json(second))


class TestAudit:
    def test_submission_is_audited_with_hashes_and_no_file_name(self, owner, submit) -> None:
        manuscript = ready_draft(owner, name="Ana Lopez - confidencial.pdf")

        submit(owner, manuscript, key="clave-auditada")

        audit = AuditLog.objects.get(action="MANUSCRIPT_SUBMITTED")
        version = ManuscriptVersion.objects.get(manuscript=manuscript)
        assert audit.result == "SUCCESS" and audit.entity_id == manuscript.pk
        assert audit.actor_id == owner.pk and audit.actor_role == "AUTHOR" and audit.request_id
        assert audit.details == {
            "code": manuscript.code,
            "version_number": 1,
            "round_number": 0,
            "original_sha256": version.original_sha256,
            "sanitized_sha256": version.sanitized_sha256,
            "metadata_sha256": version.metadata_sha256,
            "idempotency_key": "clave-auditada",
        }
        assert "Ana" not in str(audit.details) and "confidencial" not in str(audit.details)


class TestAfterCommit:
    def test_signal_is_sent_once_after_the_commit_with_ids_only(self, owner, submit) -> None:
        manuscript = ready_draft(owner)
        received = []

        def receiver(sender, **kwargs):
            received.append(kwargs)

        manuscript_submitted.connect(receiver, dispatch_uid="test-submitted")
        try:
            submit(owner, manuscript)
        finally:
            manuscript_submitted.disconnect(dispatch_uid="test-submitted")

        version = ManuscriptVersion.objects.get(manuscript=manuscript)
        assert len(received) == 1
        assert received[0]["manuscript_id"] == manuscript.pk
        assert received[0]["version_id"] == version.pk
        assert received[0]["submitted_by_id"] == owner.pk
        assert "signal" in received[0] and "title" not in received[0]

    def test_nothing_is_sent_or_deleted_before_the_commit(
        self, owner, django_capture_on_commit_callbacks, media_root
    ) -> None:
        manuscript = ready_draft(owner)
        draft_path = media_root / "private" / manuscript.draft_file_path
        received = []

        def listener(sender, **kwargs):
            received.append(kwargs)

        manuscript_submitted.connect(listener, dispatch_uid="early")
        try:
            with django_capture_on_commit_callbacks(execute=False) as callbacks:
                response = client_for(owner).post(
                    submit_url(manuscript), format="json", HTTP_IDEMPOTENCY_KEY="clave-commit"
                )
                assert response.status_code == 201

            assert len(callbacks) == 1 and received == [] and draft_path.exists()
            callbacks[0]()
        finally:
            manuscript_submitted.disconnect(dispatch_uid="early")

        assert len(received) == 1 and not draft_path.exists()

    def test_the_consumed_draft_is_cleared_from_the_manuscript(self, owner, submit) -> None:
        manuscript = ready_draft(owner)

        submit(owner, manuscript)

        manuscript.refresh_from_db()
        assert manuscript.draft_file_path is None and manuscript.draft_size_bytes is None
        assert client_for(owner).get(detail_url(manuscript)).json()["draft_file"] is None

    def test_a_failing_receiver_never_breaks_the_submission(self, owner, submit) -> None:
        manuscript = ready_draft(owner)

        def broken(sender, **kwargs):
            raise RuntimeError("listener roto")

        manuscript_submitted.connect(broken, dispatch_uid="broken")
        try:
            response = submit(owner, manuscript)
        finally:
            manuscript_submitted.disconnect(dispatch_uid="broken")

        assert response.status_code == 201
        manuscript.refresh_from_db()
        assert manuscript.status == "SUBMITTED"


def assert_untouched(manuscript, media_root) -> None:
    """Nothing of the submission survived; the draft is intact."""
    manuscript.refresh_from_db()
    assert manuscript.status == "DRAFT"
    assert (manuscript.current_version, manuscript.lock_version) == (0, 0)
    assert not ManuscriptVersion.objects.filter(manuscript=manuscript).exists()
    assert not CorrectionRound.objects.filter(manuscript=manuscript).exists()
    assert StatusEvent.objects.filter(manuscript=manuscript).count() == 1
    assert not version_dir_of(media_root, manuscript).exists()
    assert manuscript.draft_file_path
    assert (media_root / "private" / manuscript.draft_file_path).is_file()


class TestRollback:
    def test_audit_failure_reverts_everything_and_answers_503(
        self, owner, submit, media_root, monkeypatch
    ) -> None:
        manuscript = ready_draft(owner)
        received = []

        def listener(sender, **kwargs):
            received.append(kwargs)

        manuscript_submitted.connect(listener, dispatch_uid="audit-fail")

        def fail(**kwargs):
            raise AuditUnavailable("sin auditoría")

        monkeypatch.setattr(AuditService, "record", staticmethod(fail))
        try:
            response = submit(owner, manuscript)
        finally:
            manuscript_submitted.disconnect(dispatch_uid="audit-fail")

        assert response.status_code == 503
        assert error_code(response) == "AUDIT_UNAVAILABLE"
        assert_untouched(manuscript, media_root)
        assert received == []

    def test_sanitization_failure_reverts_and_removes_the_files(
        self, owner, submit, media_root, monkeypatch
    ) -> None:
        manuscript = ready_draft(owner)

        def broken(self, source, destination):
            raise PdfInvalid("No se pudo generar la copia sanitizada del PDF.")

        monkeypatch.setattr(PdfService, "sanitize", broken)

        response = submit(owner, manuscript)

        assert response.status_code == 400 and error_code(response) == "PDF_INVALID"
        assert_untouched(manuscript, media_root)

    def test_storage_failure_reverts_removes_files_and_audits_the_failure(
        self, owner, submit, media_root, monkeypatch
    ) -> None:
        manuscript = ready_draft(owner)

        def disk_full(source, destination):
            destination.write_bytes(b"parcial")  # el directorio ya contiene un archivo
            raise OSError("No space left on device")

        monkeypatch.setattr(versions_module, "copy_exclusive", disk_full)

        response = submit(owner, manuscript)

        assert response.status_code == 503 and error_code(response) == "STORAGE_UNAVAILABLE"
        assert "No space" not in response.content.decode()
        assert_untouched(manuscript, media_root)
        failure = AuditLog.objects.get(action="MANUSCRIPT_SUBMITTED")
        assert failure.result == "FAILURE" and failure.entity_id == manuscript.pk
        assert "OSError" in failure.reason

    def test_a_retry_after_a_storage_failure_succeeds(self, owner, submit, media_root, monkeypatch) -> None:
        manuscript = ready_draft(owner)
        real_copy = versions_module.copy_exclusive

        def disk_full(source, destination):
            raise OSError("No space left on device")

        monkeypatch.setattr(versions_module, "copy_exclusive", disk_full)
        assert submit(owner, manuscript).status_code == 503
        monkeypatch.setattr(versions_module, "copy_exclusive", real_copy)

        assert submit(owner, manuscript).status_code == 201

    def test_an_existing_version_directory_aborts_without_touching_it(
        self, owner, submit, media_root
    ) -> None:
        manuscript = ready_draft(owner)
        occupied = version_dir_of(media_root, manuscript)
        occupied.mkdir(parents=True)
        (occupied / "original.pdf").write_bytes(b"version previa")

        response = submit(owner, manuscript)

        assert response.status_code == 503 and error_code(response) == "STORAGE_UNAVAILABLE"
        assert (occupied / "original.pdf").read_bytes() == b"version previa"
        assert sorted(p.name for p in occupied.iterdir()) == ["original.pdf"]
        manuscript.refresh_from_db()
        assert manuscript.status == "DRAFT"
        assert not ManuscriptVersion.objects.exists()
        assert AuditLog.objects.get(action="MANUSCRIPT_SUBMITTED").result == "FAILURE"


class TestValidation:
    def test_incomplete_metadata_answers_400_listing_every_missing_field(self, owner, submit, media_root) -> None:
        client = client_for(owner)
        created = client.post(URL, {"authors": create_payload(owner)["authors"]}, format="json").json()
        manuscript = Manuscript.objects.get(pk=created["id"])

        response = submit(owner, manuscript)

        assert response.status_code == 400 and error_code(response) == "VALIDATION_ERROR"
        assert set(response.json()["error"]["details"]) == {
            "title", "abstract", "keywords", "area", "language", "draft_file",
        }
        manuscript.refresh_from_db()
        assert manuscript.status == "DRAFT" and not ManuscriptVersion.objects.exists()

    def test_the_entered_data_is_kept_as_a_draft(self, owner, submit) -> None:
        client = client_for(owner)
        created = client.post(
            URL, create_payload(owner, abstract="", area=""), format="json"
        ).json()
        manuscript = Manuscript.objects.get(pk=created["id"])

        assert submit(owner, manuscript).status_code == 400

        manuscript.refresh_from_db()
        assert manuscript.title == "Efecto del clima en cultivos andinos"
        assert manuscript.status == "DRAFT"

    def test_a_draft_without_pdf_cannot_be_submitted(self, owner, submit) -> None:
        created = client_for(owner).post(URL, create_payload(owner), format="json").json()
        manuscript = Manuscript.objects.get(pk=created["id"])

        response = submit(owner, manuscript)

        assert response.status_code == 400
        assert set(response.json()["error"]["details"]) == {"draft_file"}

    def test_blank_spaces_do_not_count_as_metadata(self, owner, submit) -> None:
        manuscript = ready_draft(owner)
        Manuscript.objects.filter(pk=manuscript.pk).update(title="   ")

        response = submit(owner, manuscript)

        assert response.status_code == 400 and "title" in response.json()["error"]["details"]

    def test_author_list_is_checked_again_at_the_submission(self, owner, submit) -> None:
        manuscript = ready_draft(owner)
        ManuscriptAuthor.objects.filter(manuscript=manuscript).update(is_corresponding=False)

        response = submit(owner, manuscript)

        assert response.status_code == 400
        assert "authors" in response.json()["error"]["details"]

    def test_the_registrant_must_still_be_listed(self, owner, submit) -> None:
        manuscript = ready_draft(owner)
        ManuscriptAuthor.objects.filter(manuscript=manuscript).update(email="otro@unl.edu.ec")

        response = submit(owner, manuscript)

        assert response.status_code == 400
        assert "debe figurar" in response.json()["error"]["details"]["authors"][0]

    def test_a_draft_pdf_damaged_after_the_upload_is_rejected(self, owner, submit, media_root) -> None:
        manuscript = ready_draft(owner)
        (media_root / "private" / manuscript.draft_file_path).write_bytes(b"%PDF-1.7 corrupto")

        response = submit(owner, manuscript)

        assert response.status_code == 400 and error_code(response) == "PDF_INVALID"
        assert_untouched(manuscript, media_root)

    def test_a_missing_draft_file_answers_503(self, owner, submit, media_root) -> None:
        manuscript = ready_draft(owner)
        (media_root / "private" / manuscript.draft_file_path).unlink()

        response = submit(owner, manuscript)

        assert response.status_code == 503 and error_code(response) == "STORAGE_UNAVAILABLE"
        manuscript.refresh_from_db()
        assert manuscript.status == "DRAFT" and not ManuscriptVersion.objects.exists()


class TestState:
    def test_a_repeated_submission_answers_409_and_creates_nothing_more(self, owner, submit) -> None:
        manuscript = ready_draft(owner)
        assert submit(owner, manuscript).status_code == 201

        second = submit(owner, manuscript)

        assert second.status_code == 409 and error_code(second) == "STATE_CONFLICT"
        assert "quedó registrado" in second.json()["error"]["message"]
        assert ManuscriptVersion.objects.filter(manuscript=manuscript).count() == 1
        assert CorrectionRound.objects.filter(manuscript=manuscript).count() == 1
        assert AuditLog.objects.filter(action="MANUSCRIPT_SUBMITTED").count() == 1

    @pytest.mark.parametrize(
        "status", ["SUBMITTED", "UNDER_REVIEW", "REQUIRES_CORRECTIONS", "ACCEPTED", "REJECTED"]
    )
    def test_any_state_but_draft_answers_409(self, owner, submit, status) -> None:
        manuscript = owned_manuscript(owner, status=status)

        response = submit(owner, manuscript)

        assert response.status_code == 409
        assert response.json()["error"]["details"]["status"] == status
        assert not ManuscriptVersion.objects.exists()

    def test_a_withdrawn_draft_answers_409(self, owner, submit) -> None:
        manuscript = ready_draft(owner)
        Manuscript.objects.filter(pk=manuscript.pk).update(is_active=False, withdrawn_at=timezone.now())

        assert submit(owner, manuscript).status_code == 409

    def test_after_the_submission_edition_and_draft_upload_are_blocked(self, owner, submit) -> None:
        manuscript = ready_draft(owner)
        submit(owner, manuscript)
        client = client_for(owner)

        patched = client.patch(detail_url(manuscript), {"title": "X"}, format="json", HTTP_IF_MATCH='"1"')
        uploaded = client.post(draft_url(manuscript), {"file": pdf_file()}, format="multipart")

        assert patched.status_code == 409 and uploaded.status_code == 409


class TestAccess:
    def test_anonymous_answers_401(self, owner) -> None:
        from rest_framework.test import APIClient

        manuscript = ready_draft(owner)

        assert APIClient().post(submit_url(manuscript)).status_code == 401

    @pytest.mark.parametrize("roles", [("EDITOR",), ("REVIEWER",), ("ADMIN",), ()])
    def test_roles_without_the_author_module_answer_403(self, owner, submit, roles) -> None:
        manuscript = ready_draft(owner)

        assert submit(actor(*roles), manuscript).status_code == 403
        assert not ManuscriptVersion.objects.exists()

    def test_someone_elses_manuscript_answers_404(self, owner, submit) -> None:
        manuscript = ready_draft(owner)

        response = submit(actor("AUTHOR"), manuscript)

        assert response.status_code == 404
        assert not ManuscriptVersion.objects.exists()

    def test_multirole_user_cannot_submit_a_manuscript_seen_as_editor(self, submit) -> None:
        person = actor("AUTHOR", "EDITOR")
        foreign = owned_manuscript(actor("AUTHOR"), status="SUBMITTED")

        assert submit(person, foreign).status_code == 404

    def test_get_is_not_allowed(self, owner) -> None:
        manuscript = ready_draft(owner)

        assert client_for(owner).get(submit_url(manuscript)).status_code == 405


class TestEditorSeesTheSubmission:
    def test_the_editor_gets_the_manuscript_with_v1_and_its_seal(self, owner, submit) -> None:
        data = factory.clean_pdf()
        manuscript = ready_draft(owner, pdf=data, name="envio.pdf")
        submit(owner, manuscript)

        item = client_for(actor("EDITOR")).get(detail_url(manuscript)).json()

        assert item["status"] == "SUBMITTED" and item["current_version"] == 1
        [version] = item["versions"]
        assert version["version_number"] == 1 and version["round_number"] == 0
        assert version["original_filename"] == "envio.pdf"
        assert version["original_sha256"] == hashlib.sha256(data).hexdigest()
        assert "path" not in json.dumps(version)
