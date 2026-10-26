"""Tests for the new version in ``REQUIRES_CORRECTIONS`` (TSK-36).

Covers the acceptance criteria:

1. Only allowed in ``REQUIRES_CORRECTIONS``; any other state answers ``409``.
2. The previous version stays intact: not renamed, not reused, not rewritten.
3. ``Idempotency-Key`` is mandatory, a repeated key never duplicates the
   version, and a submission that changes neither the PDF nor the
   metadata is rejected.

Plus HU-09: the version is consecutive, tied to the current round (which
it closes), moves the manuscript back to ``SUBMITTED``, and an
interrupted submission leaves no partial version.
"""

from __future__ import annotations

import hashlib
import stat

import pytest
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.audit.services import AuditService, AuditUnavailable
from apps.publications.models import (
    CorrectionRound,
    Manuscript,
    ManuscriptVersion,
    StatusEvent,
)
from apps.publications.services import versions as versions_module
from apps.publications.services.pdf import PdfInvalid, PdfService, sha256_of_file
from apps.publications.signals import manuscript_submitted, new_version_submitted
from config.exceptions import DomainError
from tests.publications import pdf_factory as factory
from tests.publications.test_draft_file import draft_url, pdf_file
from tests.publications.test_manuscript_api import (  # noqa: F401
    actor,
    client_for,
    detail_url,
    error_code,
    owned_manuscript,
)
from tests.publications.test_submission import (  # noqa: F401
    media_root,
    owner,
    ready_draft,
    seeded_roles,
    submit,
    version_dir_of,
)

pytestmark = pytest.mark.django_db

MAX_BYTES = 50 * factory.MIB
ORIGINAL_PDF = factory.clean_pdf(pages=1)
CORRECTED_PDF = factory.clean_pdf(pages=2)


def versions_url(manuscript) -> str:
    return f"{detail_url(manuscript)}versions/"


@pytest.fixture
def send(django_capture_on_commit_callbacks):
    """POST a new version, running the after-commit callbacks."""

    def run(user, manuscript, file=None, key: str | None = "clave-0001", **extra):
        headers = {} if key is None else {"HTTP_IDEMPOTENCY_KEY": key}
        body = {"file": file if file is not None else pdf_file(CORRECTED_PDF, name="corregido.pdf")}
        with django_capture_on_commit_callbacks(execute=True):
            return client_for(user).post(
                versions_url(manuscript), body, format="multipart", **headers, **extra
            )

    return run


def request_corrections(manuscript, round_number: int = 1) -> None:
    """What the editor's ``REQUIRES_CORRECTIONS`` verdict leaves behind (TSK-51)."""
    Manuscript.objects.filter(pk=manuscript.pk).update(
        status="REQUIRES_CORRECTIONS", current_round=round_number
    )
    CorrectionRound.objects.create(manuscript=manuscript, round_number=round_number)
    manuscript.refresh_from_db()


@pytest.fixture
def corrected(owner, submit) -> Manuscript:
    """A submitted manuscript whose v1 was answered with a correction request."""
    manuscript = ready_draft(owner, pdf=ORIGINAL_PDF, name="primera.pdf")
    assert submit(owner, manuscript).status_code == 201
    request_corrections(manuscript)
    return manuscript


def tree_digest(directory) -> dict:
    """Name -> (hash, mode) of every file in a version directory."""
    return {
        path.name: (sha256_of_file(path), stat.S_IMODE(path.stat().st_mode))
        for path in sorted(directory.iterdir())
    }


def patch_metadata(user, manuscript, body: dict) -> None:
    manuscript.refresh_from_db()
    response = client_for(user).patch(
        detail_url(manuscript), body, format="json", HTTP_IF_MATCH=f'"{manuscript.lock_version}"'
    )
    assert response.status_code == 200, response.content


class TestNewVersion:
    def test_creates_the_consecutive_version_tied_to_the_current_round(self, owner, corrected, send) -> None:
        response = send(owner, corrected)

        assert response.status_code == 201
        body = response.json()
        assert (body["version_number"], body["round_number"]) == (2, 1)
        assert body["code"] == corrected.code and body["status"] == "SUBMITTED"
        assert body["integrity_seal"] == f"sha256:{hashlib.sha256(CORRECTED_PDF).hexdigest()}"
        assert body["submitted_at"]
        numbers = list(
            ManuscriptVersion.objects.filter(manuscript=corrected).values_list("version_number", "round_number")
        )
        assert numbers == [(1, 0), (2, 1)]

    def test_the_manuscript_returns_to_submitted_with_the_new_version(self, owner, corrected, send) -> None:
        before = corrected.lock_version

        response = send(owner, corrected)

        corrected.refresh_from_db()
        assert corrected.status == "SUBMITTED"
        assert (corrected.current_version, corrected.current_round) == (2, 1)
        assert corrected.lock_version == before + 1 and response["ETag"] == f'"{before + 1}"'

    def test_the_open_round_is_closed_by_the_new_version_and_round_zero_is_untouched(
        self, owner, corrected, send
    ) -> None:
        round_zero = CorrectionRound.objects.get(manuscript=corrected, round_number=0)
        closed_at_zero = round_zero.closed_at

        send(owner, corrected)

        v1, v2 = ManuscriptVersion.objects.filter(manuscript=corrected).order_by("version_number")
        round_one = CorrectionRound.objects.get(manuscript=corrected, round_number=1)
        assert round_one.closed_by_version == v2 and round_one.closed_at
        round_zero.refresh_from_db()
        assert round_zero.closed_by_version == v1 and round_zero.closed_at == closed_at_zero
        assert CorrectionRound.objects.filter(manuscript=corrected).count() == 2

    def test_status_history_records_the_transition(self, owner, corrected, send) -> None:
        send(owner, corrected)

        event = StatusEvent.objects.filter(manuscript=corrected).last()
        assert (event.from_status, event.to_status) == ("REQUIRES_CORRECTIONS", "SUBMITTED")
        assert event.actor == owner and event.metadata == {"version_number": 2, "round_number": 1}

    def test_files_follow_the_version_layout_with_the_exact_upload(self, owner, corrected, send, media_root) -> None:
        send(owner, corrected, pdf_file(CORRECTED_PDF, name="Ana Lopez - corregido.pdf"))

        v2 = ManuscriptVersion.objects.get(manuscript=corrected, version_number=2)
        directory = version_dir_of(media_root, corrected, 2)
        assert sorted(p.name for p in directory.iterdir()) == ["metadata.json", "original.pdf", "sanitized.pdf"]
        assert (directory / "original.pdf").read_bytes() == CORRECTED_PDF
        assert v2.original_file_path == f"manuscripts/{corrected.pk}/v0002/original.pdf"
        assert v2.original_filename == "Ana Lopez - corregido.pdf"
        assert v2.original_sha256 == hashlib.sha256(CORRECTED_PDF).hexdigest()
        assert v2.sanitized_sha256 == sha256_of_file(directory / "sanitized.pdf")
        assert stat.S_IMODE(directory.stat().st_mode) == 0o750
        for path in directory.iterdir():
            assert stat.S_IMODE(path.stat().st_mode) == 0o640

    def test_the_staged_upload_is_removed(self, owner, corrected, send, media_root) -> None:
        send(owner, corrected)

        assert list((media_root / "tmp" / "uploads").glob("*")) == []

    def test_a_new_version_can_follow_a_second_correction_round(self, owner, corrected, send, submit) -> None:
        assert send(owner, corrected).status_code == 201
        request_corrections(corrected, round_number=2)

        response = send(owner, corrected, pdf_file(factory.clean_pdf(pages=3)), key="clave-0002")

        assert response.status_code == 201
        assert (response.json()["version_number"], response.json()["round_number"]) == (3, 2)
        assert CorrectionRound.objects.get(manuscript=corrected, round_number=2).closed_by_version.version_number == 3


class TestPreviousVersionIsIntact:
    def test_row_and_files_of_v1_are_unchanged(self, owner, corrected, send, media_root) -> None:
        v1 = ManuscriptVersion.objects.get(manuscript=corrected, version_number=1)
        row_before = {f.name: getattr(v1, f.name) for f in ManuscriptVersion._meta.fields}
        files_before = tree_digest(version_dir_of(media_root, corrected, 1))

        send(owner, corrected)

        v1.refresh_from_db()
        assert {f.name: getattr(v1, f.name) for f in ManuscriptVersion._meta.fields} == row_before
        assert tree_digest(version_dir_of(media_root, corrected, 1)) == files_before
        assert v1.original_file_path == f"manuscripts/{corrected.pk}/v0001/original.pdf"

    def test_v1_keeps_its_own_snapshot_when_the_metadata_changes(self, owner, corrected, send) -> None:
        patch_metadata(owner, corrected, {"title": "Título corregido tras la revisión"})

        send(owner, corrected)

        v1, v2 = ManuscriptVersion.objects.filter(manuscript=corrected).order_by("version_number")
        assert v1.metadata_snapshot["title"] == "Efecto del clima en cultivos andinos"
        assert v2.metadata_snapshot["title"] == "Título corregido tras la revisión"
        assert v1.metadata_sha256 != v2.metadata_sha256

    def test_the_database_still_rejects_rewriting_v1(self, owner, corrected, send) -> None:
        send(owner, corrected)

        from django.db import transaction
        from django.db.utils import DatabaseError

        with pytest.raises(DatabaseError, match="inmutables"), transaction.atomic():
            ManuscriptVersion.objects.filter(manuscript=corrected, version_number=1).update(
                original_sha256="f" * 64
            )


class TestWhatChanged:
    def test_same_pdf_with_edited_metadata_is_a_valid_correction(self, owner, corrected, send) -> None:
        patch_metadata(owner, corrected, {"abstract": "Resumen corregido."})

        response = send(owner, corrected, pdf_file(ORIGINAL_PDF, name="mismo.pdf"))

        assert response.status_code == 201
        audit = AuditLog.objects.get(action="MANUSCRIPT_VERSION_SUBMITTED")
        assert audit.details["changes"] == {"pdf": False, "metadata": True}

    def test_new_pdf_with_the_same_metadata_is_a_valid_correction(self, owner, corrected, send) -> None:
        response = send(owner, corrected)

        assert response.status_code == 201
        audit = AuditLog.objects.get(action="MANUSCRIPT_VERSION_SUBMITTED")
        assert audit.details["changes"] == {"pdf": True, "metadata": False}

    def test_neither_pdf_nor_metadata_changed_is_rejected(self, owner, corrected, send, media_root) -> None:
        response = send(owner, corrected, pdf_file(ORIGINAL_PDF, name="identico.pdf"))

        assert response.status_code == 400 and error_code(response) == "VALIDATION_ERROR"
        assert "al menos una corrección" in response.json()["error"]["message"]
        corrected.refresh_from_db()
        assert corrected.status == "REQUIRES_CORRECTIONS" and corrected.current_version == 1
        assert ManuscriptVersion.objects.filter(manuscript=corrected).count() == 1
        assert not version_dir_of(media_root, corrected, 2).exists()
        assert CorrectionRound.objects.get(manuscript=corrected, round_number=1).closed_by_version is None
        assert not AuditLog.objects.filter(action="MANUSCRIPT_VERSION_SUBMITTED").exists()

    def test_metadata_only_can_be_saved_but_does_not_register_a_version(self, owner, corrected) -> None:
        patch_metadata(owner, corrected, {"title": "Solo cambié el título"})

        response = client_for(owner).post(
            versions_url(corrected), {}, format="multipart", HTTP_IDEMPOTENCY_KEY="clave-0001"
        )

        assert response.status_code == 400
        corrected.refresh_from_db()
        assert corrected.title == "Solo cambié el título" and corrected.current_version == 1
        assert ManuscriptVersion.objects.filter(manuscript=corrected).count() == 1


class TestIdempotencyKey:
    @pytest.mark.parametrize("key", [None, "", "   ", "clave con espacios", "ñandú", "x" * 101])
    def test_a_missing_or_malformed_key_answers_400(self, owner, corrected, send, key) -> None:
        response = send(owner, corrected, key=key)

        assert response.status_code == 400 and error_code(response) == "VALIDATION_ERROR"
        assert "Idempotency-Key" in response.json()["error"]["message"]
        assert ManuscriptVersion.objects.filter(manuscript=corrected).count() == 1

    @pytest.mark.parametrize("key", ["a", "0b8f2c1e-6d0a-4b8e-9a52-1f7c3d2e4a10", "k" * 100, "intento:1.a_b-c"])
    def test_usual_keys_are_accepted(self, owner, corrected, send, key) -> None:
        assert send(owner, corrected, key=key).status_code == 201

    def test_a_new_attempt_with_another_key_after_success_answers_409(self, owner, corrected, send, media_root) -> None:
        first = send(owner, corrected, key="primera-clave")
        digest = tree_digest(version_dir_of(media_root, corrected, 2))

        second = send(owner, corrected, key="otra-clave")

        assert first.status_code == 201
        assert second.status_code == 409 and error_code(second) == "STATE_CONFLICT"
        assert ManuscriptVersion.objects.filter(manuscript=corrected).count() == 2
        assert CorrectionRound.objects.filter(manuscript=corrected).count() == 2
        assert tree_digest(version_dir_of(media_root, corrected, 2)) == digest
        assert AuditLog.objects.filter(action="MANUSCRIPT_VERSION_SUBMITTED").count() == 1

    def test_the_key_is_kept_in_the_audit_trail(self, owner, corrected, send) -> None:
        send(owner, corrected, key="trazable-001")

        audit = AuditLog.objects.get(action="MANUSCRIPT_VERSION_SUBMITTED")
        assert audit.details["idempotency_key"] == "trazable-001"


class TestAudit:
    def test_new_version_is_audited_with_hashes_and_no_file_name(self, owner, corrected, send) -> None:
        send(owner, corrected, pdf_file(CORRECTED_PDF, name="Ana Lopez - confidencial.pdf"))

        audit = AuditLog.objects.get(action="MANUSCRIPT_VERSION_SUBMITTED")
        v2 = ManuscriptVersion.objects.get(manuscript=corrected, version_number=2)
        assert audit.result == "SUCCESS" and audit.entity_id == corrected.pk
        assert audit.actor_id == owner.pk and audit.actor_role == "AUTHOR" and audit.request_id
        assert audit.details == {
            "code": corrected.code,
            "version_number": 2,
            "round_number": 1,
            "original_sha256": v2.original_sha256,
            "sanitized_sha256": v2.sanitized_sha256,
            "metadata_sha256": v2.metadata_sha256,
            "changes": {"pdf": True, "metadata": False},
            "idempotency_key": "clave-0001",
        }
        assert "Ana" not in str(audit.details) and "confidencial" not in str(audit.details)


class TestAfterCommit:
    def test_the_new_version_signal_is_sent_once_with_ids_only(self, owner, corrected, send) -> None:
        received, initial = [], []

        def on_new_version(sender, **kwargs):
            received.append(kwargs)

        def on_initial(sender, **kwargs):
            initial.append(kwargs)

        new_version_submitted.connect(on_new_version, dispatch_uid="new-version")
        manuscript_submitted.connect(on_initial, dispatch_uid="initial")
        try:
            send(owner, corrected)
        finally:
            new_version_submitted.disconnect(dispatch_uid="new-version")
            manuscript_submitted.disconnect(dispatch_uid="initial")

        v2 = ManuscriptVersion.objects.get(manuscript=corrected, version_number=2)
        assert len(received) == 1 and initial == []
        assert received[0]["manuscript_id"] == corrected.pk and received[0]["version_id"] == v2.pk
        assert received[0]["submitted_by_id"] == owner.pk and "title" not in received[0]

    def test_a_failing_receiver_never_breaks_the_submission(self, owner, corrected, send) -> None:
        def broken(sender, **kwargs):
            raise RuntimeError("listener roto")

        new_version_submitted.connect(broken, dispatch_uid="broken-version")
        try:
            response = send(owner, corrected)
        finally:
            new_version_submitted.disconnect(dispatch_uid="broken-version")

        assert response.status_code == 201


class TestState:
    @pytest.mark.parametrize("status", ["DRAFT", "SUBMITTED", "UNDER_REVIEW", "ACCEPTED", "REJECTED"])
    def test_any_other_state_answers_409_with_an_explanation(self, owner, send, status) -> None:
        manuscript = owned_manuscript(owner, status=status)

        response = send(owner, manuscript)

        assert response.status_code == 409 and error_code(response) == "STATE_CONFLICT"
        assert "requiere correcciones" in response.json()["error"]["message"]
        assert response.json()["error"]["details"]["status"] == status
        assert not ManuscriptVersion.objects.exists()

    def test_state_is_checked_before_the_header_and_the_body(self, owner) -> None:
        manuscript = owned_manuscript(owner, status="SUBMITTED")

        response = client_for(owner).post(versions_url(manuscript), {"x": 1}, format="json")

        assert response.status_code == 409

    def test_a_withdrawn_manuscript_answers_409(self, owner, corrected, send) -> None:
        Manuscript.objects.filter(pk=corrected.pk).update(is_active=False, withdrawn_at=timezone.now())

        assert send(owner, corrected).status_code == 409

    def test_a_missing_current_round_answers_409_and_creates_nothing(self, owner, corrected, send, media_root) -> None:
        CorrectionRound.objects.filter(manuscript=corrected, round_number=1).delete()

        response = send(owner, corrected)

        assert response.status_code == 409
        assert ManuscriptVersion.objects.filter(manuscript=corrected).count() == 1
        assert not version_dir_of(media_root, corrected, 2).exists()

    def test_two_simultaneous_submissions_only_register_one(self, owner, corrected, media_root) -> None:
        context = {"request_id": "r-1", "ip_address": None, "user_agent": None}
        first = versions_module.submit_new_version(
            manuscript_id=corrected.pk, user=owner, uploaded=pdf_file(CORRECTED_PDF),
            idempotency_key="carrera-1", context=context,
        )
        digest = tree_digest(version_dir_of(media_root, corrected, 2))

        with pytest.raises(DomainError) as raised:
            versions_module.submit_new_version(
                manuscript_id=corrected.pk, user=owner, uploaded=pdf_file(factory.clean_pdf(pages=3)),
                idempotency_key="carrera-2", context=context,
            )

        assert first.version.version_number == 2
        assert raised.value.status_code == 409
        assert tree_digest(version_dir_of(media_root, corrected, 2)) == digest
        assert ManuscriptVersion.objects.filter(manuscript=corrected).count() == 2

    def test_after_the_new_version_edition_and_draft_upload_are_blocked(self, owner, corrected, send) -> None:
        send(owner, corrected)
        client = client_for(owner)

        patched = client.patch(detail_url(corrected), {"title": "X"}, format="json", HTTP_IF_MATCH='"3"')
        uploaded = client.post(draft_url(corrected), {"file": pdf_file()}, format="multipart")

        assert patched.status_code == 409 and uploaded.status_code == 409


class TestInvalidUpload:
    def test_missing_file_field_answers_400(self, owner, corrected) -> None:
        response = client_for(owner).post(
            versions_url(corrected), {"otro": "x"}, format="multipart", HTTP_IDEMPOTENCY_KEY="clave-0001"
        )

        assert response.status_code == 400

    @pytest.mark.parametrize(
        "data",
        [
            pytest.param(b"", id="vacio"),
            pytest.param(b"no soy un pdf", id="texto"),
            pytest.param(CORRECTED_PDF[:150], id="truncado"),
            pytest.param(factory.encrypted_pdf("clave"), id="cifrado"),
            pytest.param(factory.pdf_with_active_content("/JavaScript"), id="javascript"),
        ],
    )
    def test_invalid_content_answers_400_and_keeps_requires_corrections(
        self, owner, corrected, send, media_root, data
    ) -> None:
        response = send(owner, corrected, pdf_file(data))

        assert response.status_code == 400 and error_code(response) == "PDF_INVALID"
        corrected.refresh_from_db()
        assert corrected.status == "REQUIRES_CORRECTIONS" and corrected.current_version == 1
        assert ManuscriptVersion.objects.filter(manuscript=corrected).count() == 1
        assert not version_dir_of(media_root, corrected, 2).exists()
        assert list((media_root / "tmp" / "uploads").glob("*")) == []

    def test_only_the_pdf_extension_is_accepted(self, owner, corrected, send) -> None:
        response = send(owner, corrected, pdf_file(CORRECTED_PDF, name="corregido.docx"))

        assert response.status_code == 400 and error_code(response) == "PDF_INVALID"

    def test_file_declared_as_another_type_answers_415(self, owner, corrected, send) -> None:
        response = send(owner, corrected, pdf_file(CORRECTED_PDF, content_type="image/png"))

        assert response.status_code == 415 and error_code(response) == "PDF_UNSUPPORTED"

    def test_json_body_answers_415(self, owner, corrected) -> None:
        response = client_for(owner).post(
            versions_url(corrected), {"file": "x"}, format="json", HTTP_IDEMPOTENCY_KEY="clave-0001"
        )

        assert response.status_code == 415 and error_code(response) == "PDF_UNSUPPORTED"

    def test_one_byte_over_50_mb_answers_413_and_leaves_no_temporary(self, owner, corrected, send, media_root) -> None:
        oversized = factory.pdf_of_size(MAX_BYTES) + b"\n"

        response = send(owner, corrected, pdf_file(oversized))

        assert response.status_code == 413 and error_code(response) == "PDF_TOO_LARGE"
        assert list((media_root / "tmp" / "uploads").glob("*")) == []
        assert ManuscriptVersion.objects.filter(manuscript=corrected).count() == 1

    def test_exactly_50_mb_is_accepted(self, owner, corrected, send) -> None:
        response = send(owner, corrected, pdf_file(factory.pdf_of_size(MAX_BYTES)))

        assert response.status_code == 201

    def test_incomplete_metadata_blocks_the_new_version(self, owner, corrected, send) -> None:
        Manuscript.objects.filter(pk=corrected.pk).update(title="  ")

        response = send(owner, corrected)

        assert response.status_code == 400
        assert "title" in response.json()["error"]["details"]
        assert ManuscriptVersion.objects.filter(manuscript=corrected).count() == 1


def assert_still_awaiting_the_correction(manuscript, media_root) -> None:
    """No partial version exists and v1 is still the current one (CA-HU-09-07)."""
    manuscript.refresh_from_db()
    assert manuscript.status == "REQUIRES_CORRECTIONS"
    assert (manuscript.current_version, manuscript.current_round) == (1, 1)
    assert ManuscriptVersion.objects.filter(manuscript=manuscript).count() == 1
    assert CorrectionRound.objects.get(manuscript=manuscript, round_number=1).closed_by_version is None
    assert not version_dir_of(media_root, manuscript, 2).exists()
    assert list((media_root / "tmp" / "uploads").glob("*")) == []


class TestRollback:
    def test_audit_failure_reverts_everything_and_answers_503(self, owner, corrected, send, media_root, monkeypatch) -> None:
        digest = tree_digest(version_dir_of(media_root, corrected, 1))
        received = []

        def listener(sender, **kwargs):
            received.append(kwargs)

        def fail(**kwargs):
            raise AuditUnavailable("sin auditoría")

        new_version_submitted.connect(listener, dispatch_uid="audit-fail-version")
        monkeypatch.setattr(AuditService, "record", staticmethod(fail))
        try:
            response = send(owner, corrected)
        finally:
            new_version_submitted.disconnect(dispatch_uid="audit-fail-version")

        assert response.status_code == 503 and error_code(response) == "AUDIT_UNAVAILABLE"
        assert_still_awaiting_the_correction(corrected, media_root)
        assert tree_digest(version_dir_of(media_root, corrected, 1)) == digest
        assert received == []

    def test_sanitization_failure_reverts_and_removes_the_files(self, owner, corrected, send, media_root, monkeypatch) -> None:
        def broken(self, source, destination):
            raise PdfInvalid("No se pudo generar la copia sanitizada del PDF.")

        monkeypatch.setattr(PdfService, "sanitize", broken)

        response = send(owner, corrected)

        assert response.status_code == 400 and error_code(response) == "PDF_INVALID"
        assert_still_awaiting_the_correction(corrected, media_root)

    def test_storage_failure_reverts_and_audits_the_failure(self, owner, corrected, send, media_root, monkeypatch) -> None:
        def disk_full(source, destination):
            destination.write_bytes(b"parcial")
            raise OSError("No space left on device")

        monkeypatch.setattr(versions_module, "copy_exclusive", disk_full)

        response = send(owner, corrected)

        assert response.status_code == 503 and error_code(response) == "STORAGE_UNAVAILABLE"
        assert "No space" not in response.content.decode()
        assert_still_awaiting_the_correction(corrected, media_root)
        failure = AuditLog.objects.get(action="MANUSCRIPT_VERSION_SUBMITTED")
        assert failure.result == "FAILURE" and "OSError" in failure.reason

    def test_a_retry_after_an_interruption_succeeds(self, owner, corrected, send, media_root, monkeypatch) -> None:
        real_copy = versions_module.copy_exclusive

        def disk_full(source, destination):
            raise OSError("No space left on device")

        monkeypatch.setattr(versions_module, "copy_exclusive", disk_full)
        assert send(owner, corrected).status_code == 503
        monkeypatch.setattr(versions_module, "copy_exclusive", real_copy)

        assert send(owner, corrected).status_code == 201

    def test_an_existing_version_directory_aborts_without_touching_it(self, owner, corrected, send, media_root) -> None:
        occupied = version_dir_of(media_root, corrected, 2)
        occupied.mkdir(parents=True)
        (occupied / "original.pdf").write_bytes(b"version previa")

        response = send(owner, corrected)

        assert response.status_code == 503 and error_code(response) == "STORAGE_UNAVAILABLE"
        assert (occupied / "original.pdf").read_bytes() == b"version previa"
        assert [p.name for p in occupied.iterdir()] == ["original.pdf"]
        assert ManuscriptVersion.objects.filter(manuscript=corrected).count() == 1
        corrected.refresh_from_db()
        assert corrected.status == "REQUIRES_CORRECTIONS"


class TestAccess:
    def test_anonymous_answers_401(self, corrected) -> None:
        from rest_framework.test import APIClient

        assert APIClient().post(versions_url(corrected)).status_code == 401

    @pytest.mark.parametrize("roles", [("EDITOR",), ("REVIEWER",), ("ADMIN",), ()])
    def test_roles_without_the_author_module_answer_403(self, corrected, send, roles) -> None:
        assert send(actor(*roles), corrected).status_code == 403
        assert ManuscriptVersion.objects.filter(manuscript=corrected).count() == 1

    def test_someone_elses_manuscript_answers_404(self, corrected, send) -> None:
        assert send(actor("AUTHOR"), corrected).status_code == 404

    def test_multirole_user_cannot_send_a_version_for_a_manuscript_seen_as_editor(self, corrected, send) -> None:
        assert send(actor("AUTHOR", "EDITOR"), corrected).status_code == 404

    def test_only_get_and_post_are_allowed(self, owner, corrected) -> None:
        client = client_for(owner)

        assert client.put(versions_url(corrected), {}, format="json").status_code == 405
        assert client.patch(versions_url(corrected), {}, format="json").status_code == 405
        assert client.delete(versions_url(corrected)).status_code == 405


class TestEditorSeesTheHistory:
    def test_the_editor_lists_both_versions_with_their_seals(self, owner, corrected, send) -> None:
        send(owner, corrected, pdf_file(CORRECTED_PDF, name="segunda.pdf"))

        item = client_for(actor("EDITOR")).get(detail_url(corrected)).json()

        assert item["status"] == "SUBMITTED" and item["current_version"] == 2
        assert [v["version_number"] for v in item["versions"]] == [1, 2]
        assert [v["round_number"] for v in item["versions"]] == [0, 1]
        assert [v["original_filename"] for v in item["versions"]] == ["primera.pdf", "segunda.pdf"]
        assert item["versions"][1]["original_sha256"] == hashlib.sha256(CORRECTED_PDF).hexdigest()
