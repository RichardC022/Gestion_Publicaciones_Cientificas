"""Failure injection: a broken step never leaves a partial version (TSK-40).

Acceptance criterion: "un fallo de auditoría o almacenamiento no deja
una versión parcial". Instead of trying only the failures that come to
mind, every step of the two write pipelines is broken in turn — the
initial submission (``v1``) and the new version — and each time the
same invariant is checked: no version, round, status event, file,
stored idempotency key or success audit entry survives, the draft or
the previous version is untouched, and the same request can be retried
with the same key once the cause is gone.
"""

from __future__ import annotations

import pytest
from django.db import DatabaseError
from rest_framework.test import APIClient

from apps.audit.models import AuditLog
from apps.audit.services import AuditService, AuditUnavailable
from apps.publications.models import (
    CorrectionRound,
    IdempotencyKey,
    Manuscript,
    ManuscriptVersion,
    StatusEvent,
)
from apps.publications.services import versions as versions_module
from apps.publications.services.pdf import PdfInvalid, PdfService
from apps.publications.signals import manuscript_submitted, new_version_submitted
from tests.publications import pdf_factory as factory
from tests.publications.test_draft_file import pdf_file
from tests.publications.test_lifecycle import assert_audit_chain_intact, tree_digest
from tests.publications.test_manuscript_api import actor, client_for, error_code  # noqa: F401
from tests.publications.test_new_version import request_corrections, versions_url
from tests.publications.test_submission import (  # noqa: F401
    media_root,
    owner,
    ready_draft,
    seeded_roles,
    submit,
    submit_url,
    version_dir_of,
)

pytestmark = pytest.mark.django_db

V1 = factory.clean_pdf(pages=1)
V2 = factory.clean_pdf(pages=2)


def disk_full(*args, **kwargs):
    raise OSError("No space left on device")


def partial_copy_then_fail(source, destination):
    destination.write_bytes(b"parcial")  # el directorio de la versión ya tiene un archivo
    raise OSError("No space left on device")


def db_failure(*args, **kwargs):
    raise DatabaseError("fallo de la base de datos")


def audit_down(**kwargs):
    raise AuditUnavailable("sin auditoría")


def invalid_sanitization(self, source, destination):
    raise PdfInvalid("No se pudo generar la copia sanitizada del PDF.")


# (id, how to break it, expected status). A raw database failure surfaces
# as an unhandled 500: the point is that nothing survives it.
COMMON = [
    ("directory", lambda mp: mp.setattr(versions_module, "allocate_version_dir", disk_full), 503),
    ("copy-original", lambda mp: mp.setattr(versions_module, "copy_exclusive", partial_copy_then_fail), 503),
    ("sanitize", lambda mp: mp.setattr(PdfService, "sanitize", invalid_sanitization), 400),
    ("metadata-file", lambda mp: mp.setattr(versions_module, "write_exclusive", disk_full), 503),
    ("version-row", lambda mp: mp.setattr(ManuscriptVersion.objects, "create", db_failure), 500),
    ("status-event", lambda mp: mp.setattr(StatusEvent.objects, "create", db_failure), 500),
    ("audit", lambda mp: mp.setattr(AuditService, "record", staticmethod(audit_down)), 503),
]
SUBMIT_ONLY = [
    ("round-row", lambda mp: mp.setattr(CorrectionRound.objects, "create", db_failure), 500),
]
VERSION_ONLY = [
    ("round-close", lambda mp: mp.setattr(CorrectionRound, "save", db_failure), 500),
]


def calm_client(user) -> APIClient:
    """A client that reports an unhandled error as a 500 instead of raising it."""
    client = APIClient(raise_request_exception=False)
    client.force_authenticate(user)
    return client


def listen(signal, bucket: list, uid: str):
    def listener(sender, **kwargs):
        bucket.append(kwargs)

    signal.connect(listener, dispatch_uid=uid)
    return listener


class TestInitialSubmission:
    @pytest.mark.parametrize("point", COMMON + SUBMIT_ONLY, ids=lambda p: p[0] if isinstance(p, tuple) else None)
    def test_a_broken_step_leaves_nothing_behind_and_the_retry_succeeds(
        self, owner, media_root, monkeypatch, point
    ) -> None:
        name, break_it, expected = point
        manuscript = ready_draft(owner, pdf=V1)
        draft_path = media_root / "private" / manuscript.draft_file_path
        draft_bytes = draft_path.read_bytes()
        events_before = StatusEvent.objects.filter(manuscript=manuscript).count()
        sent = []
        listener = listen(manuscript_submitted, sent, f"inject-{name}")
        url = submit_url(manuscript)

        try:
            with monkeypatch.context() as broken:
                break_it(broken)
                failed = calm_client(owner).post(url, format="json", HTTP_IDEMPOTENCY_KEY="intento-1")

            assert failed.status_code == expected, (name, failed.content[:200])
            manuscript.refresh_from_db()
            assert manuscript.status == "DRAFT"
            assert (manuscript.current_version, manuscript.current_round, manuscript.lock_version) == (0, 0, 0)
            assert not ManuscriptVersion.objects.filter(manuscript=manuscript).exists()
            assert not CorrectionRound.objects.filter(manuscript=manuscript).exists()
            assert StatusEvent.objects.filter(manuscript=manuscript).count() == events_before
            assert not IdempotencyKey.objects.exists()
            assert not AuditLog.objects.filter(action="MANUSCRIPT_SUBMITTED", result="SUCCESS").exists()
            assert not version_dir_of(media_root, manuscript).exists()
            assert draft_path.read_bytes() == draft_bytes and manuscript.draft_file_path
            assert list((media_root / "tmp" / "uploads").glob("*")) == []
            assert sent == []
            assert_audit_chain_intact()

            retry = client_for(owner).post(url, format="json", HTTP_IDEMPOTENCY_KEY="intento-1")
            assert retry.status_code == 201 and "Idempotent-Replayed" not in retry.headers
            assert ManuscriptVersion.objects.filter(manuscript=manuscript).count() == 1
        finally:
            manuscript_submitted.disconnect(dispatch_uid=f"inject-{name}")
            del listener

    def test_a_storage_failure_is_audited_as_a_failure_not_as_a_success(self, owner, monkeypatch) -> None:
        manuscript = ready_draft(owner, pdf=V1)
        monkeypatch.setattr(versions_module, "copy_exclusive", disk_full)

        calm_client(owner).post(submit_url(manuscript), format="json", HTTP_IDEMPOTENCY_KEY="k")

        [entry] = AuditLog.objects.filter(action="MANUSCRIPT_SUBMITTED")
        assert entry.result == "FAILURE" and "OSError" in entry.reason
        assert "No space" not in str(entry.reason)

    def test_storage_and_audit_failing_together_still_answers_503_and_leaves_nothing(
        self, owner, media_root, monkeypatch
    ) -> None:
        manuscript = ready_draft(owner, pdf=V1)
        monkeypatch.setattr(versions_module, "copy_exclusive", disk_full)
        monkeypatch.setattr(AuditService, "record", staticmethod(audit_down))

        response = calm_client(owner).post(submit_url(manuscript), format="json", HTTP_IDEMPOTENCY_KEY="k")

        assert response.status_code == 503 and error_code(response) == "STORAGE_UNAVAILABLE"
        manuscript.refresh_from_db()
        assert manuscript.status == "DRAFT" and not ManuscriptVersion.objects.exists()
        assert not version_dir_of(media_root, manuscript).exists()
        assert not AuditLog.objects.filter(action="MANUSCRIPT_SUBMITTED").exists()


@pytest.fixture
def awaiting(owner, submit, media_root):
    """v1 submitted and a correction requested (round 1 open)."""
    manuscript = ready_draft(owner, pdf=V1)
    assert submit(owner, manuscript).status_code == 201
    request_corrections(manuscript)
    return manuscript


class TestNewVersion:
    @pytest.mark.parametrize("point", COMMON + VERSION_ONLY, ids=lambda p: p[0] if isinstance(p, tuple) else None)
    def test_a_broken_step_leaves_nothing_behind_and_the_retry_succeeds(
        self, owner, awaiting, media_root, monkeypatch, point
    ) -> None:
        name, break_it, expected = point
        v1_files = tree_digest(version_dir_of(media_root, awaiting, 1))
        v1_row = ManuscriptVersion.objects.values().get(manuscript=awaiting, version_number=1)
        events_before = StatusEvent.objects.filter(manuscript=awaiting).count()
        keys_before = IdempotencyKey.objects.count()
        sent = []
        listen(new_version_submitted, sent, f"inject-v-{name}")

        def post(client):
            return client.post(
                versions_url(awaiting),
                {"file": pdf_file(V2)},
                format="multipart",
                HTTP_IDEMPOTENCY_KEY="intento-1",
            )

        try:
            with monkeypatch.context() as broken:
                break_it(broken)
                failed = post(calm_client(owner))

            assert failed.status_code == expected, (name, failed.content[:200])
            awaiting.refresh_from_db()
            assert awaiting.status == "REQUIRES_CORRECTIONS"
            assert (awaiting.current_version, awaiting.current_round) == (1, 1)
            assert ManuscriptVersion.objects.filter(manuscript=awaiting).count() == 1
            assert ManuscriptVersion.objects.values().get(manuscript=awaiting, version_number=1) == v1_row
            assert CorrectionRound.objects.get(manuscript=awaiting, round_number=1).closed_by_version is None
            assert StatusEvent.objects.filter(manuscript=awaiting).count() == events_before
            assert IdempotencyKey.objects.count() == keys_before
            assert not AuditLog.objects.filter(action="MANUSCRIPT_VERSION_SUBMITTED", result="SUCCESS").exists()
            assert not version_dir_of(media_root, awaiting, 2).exists()
            assert tree_digest(version_dir_of(media_root, awaiting, 1)) == v1_files
            assert list((media_root / "tmp" / "uploads").glob("*")) == []
            assert sent == []
            assert_audit_chain_intact()

            retry = post(client_for(owner))
            assert retry.status_code == 201 and "Idempotent-Replayed" not in retry.headers
            assert ManuscriptVersion.objects.filter(manuscript=awaiting).count() == 2
        finally:
            new_version_submitted.disconnect(dispatch_uid=f"inject-v-{name}")

    def test_storage_and_audit_failing_together_still_answers_503_and_leaves_nothing(
        self, owner, awaiting, media_root, monkeypatch
    ) -> None:
        monkeypatch.setattr(versions_module, "copy_exclusive", disk_full)
        monkeypatch.setattr(AuditService, "record", staticmethod(audit_down))

        response = calm_client(owner).post(
            versions_url(awaiting), {"file": pdf_file(V2)}, format="multipart", HTTP_IDEMPOTENCY_KEY="k"
        )

        assert response.status_code == 503 and error_code(response) == "STORAGE_UNAVAILABLE"
        awaiting.refresh_from_db()
        assert awaiting.status == "REQUIRES_CORRECTIONS" and awaiting.current_version == 1
        assert not version_dir_of(media_root, awaiting, 2).exists()

    def test_a_pre_existing_version_directory_is_never_deleted_by_the_cleanup(
        self, owner, awaiting, media_root
    ) -> None:
        occupied = version_dir_of(media_root, awaiting, 2)
        occupied.mkdir(parents=True)
        (occupied / "original.pdf").write_bytes(b"evidencia previa")

        response = calm_client(owner).post(
            versions_url(awaiting), {"file": pdf_file(V2)}, format="multipart", HTTP_IDEMPOTENCY_KEY="k"
        )

        assert response.status_code == 503
        assert (occupied / "original.pdf").read_bytes() == b"evidencia previa"
        awaiting.refresh_from_db()
        assert awaiting.status == "REQUIRES_CORRECTIONS" and awaiting.current_version == 1
