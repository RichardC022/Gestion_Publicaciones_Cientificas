"""Tests for the ``verify_integrity`` command (TSK-76).

Acceptance criterion: it reports discrepancies without modifying files or
the audit trail, and exits with a non-zero code when it finds any.
"""

from __future__ import annotations

import hashlib
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection

from apps.audit.models import AuditLog
from apps.audit.services import AuditService
from apps.publications.services.snapshot import canonical_json, metadata_sha256
from tests.factories import CatalogEntryFactory, ManuscriptFactory, ManuscriptVersionFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def media_root(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    return tmp_path


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make_sealed_version(media_root):
    """A version whose two PDFs and metadata seal match what is on disk."""
    manuscript = ManuscriptFactory()
    base = f"manuscripts/{manuscript.pk}/v0001"
    contents = {"original": b"%PDF-1.7 original", "sanitized": b"%PDF-1.7 sanitized"}
    for kind, data in contents.items():
        path = media_root / "private" / base / f"{kind}.pdf"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    snapshot = {"title": "Artículo"}
    return ManuscriptVersionFactory(
        manuscript=manuscript,
        original_file_path=f"{base}/original.pdf",
        original_sha256=sha(contents["original"]),
        sanitized_file_path=f"{base}/sanitized.pdf",
        sanitized_sha256=sha(contents["sanitized"]),
        metadata_snapshot=snapshot,
        metadata_sha256=metadata_sha256(canonical_json(snapshot)),
    )


def run() -> tuple[str, str]:
    out, err = StringIO(), StringIO()
    call_command("verify_integrity", stdout=out, stderr=err)
    return out.getvalue(), err.getvalue()


def record(action: str = "LOGIN") -> AuditLog:
    return AuditService.record(
        action=action,
        entity_type="SESSION",
        request_id="rid-1",
        details={"source": "test"},
    )


def tamper_audit(sql: str, params=()) -> None:
    """Edit the append-only table the way a database superuser could."""
    with connection.cursor() as cursor:
        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
        cursor.execute("ALTER TABLE audit_audit_log DISABLE TRIGGER trg_audit_no_update")
        cursor.execute(sql, params)
        cursor.execute("ALTER TABLE audit_audit_log ENABLE TRIGGER trg_audit_no_update")


class TestCleanSystem:
    def test_empty_system_passes(self, media_root) -> None:
        out, err = run()

        assert "sin discrepancias" in out
        assert err == ""

    def test_intact_files_and_chain_pass(self, media_root) -> None:
        make_sealed_version(media_root)
        record("LOGIN")
        record("LOGOUT")

        out, _ = run()

        assert "Archivos verificados: 2" in out
        assert "entradas de auditoría verificadas: 2" in out
        assert "sin discrepancias" in out


class TestPdfDiscrepancies:
    def test_altered_pdf_is_reported_and_exit_is_nonzero(self, media_root) -> None:
        version = make_sealed_version(media_root)
        target = media_root / "private" / version.sanitized_file_path
        target.write_bytes(b"manipulado")

        err = StringIO()
        with pytest.raises(CommandError):
            call_command("verify_integrity", stdout=StringIO(), stderr=err)

        assert "sanitizado" in err.getvalue()
        assert "hash distinto" in err.getvalue()

    def test_missing_pdf_is_reported(self, media_root) -> None:
        version = make_sealed_version(media_root)
        (media_root / "private" / version.original_file_path).unlink()

        err = StringIO()
        with pytest.raises(CommandError):
            call_command("verify_integrity", stdout=StringIO(), stderr=err)

        assert "archivo ausente" in err.getvalue()

    def test_altered_metadata_seal_is_reported(self, media_root) -> None:
        version = make_sealed_version(media_root)
        # Las versiones son inmutables por trigger: se simula el sello ya roto
        # sustituyendo el que se calcula, no editando la fila.
        sealed = ManuscriptVersionFactory(
            manuscript=version.manuscript,
            version_number=2,
            original_file_path=version.original_file_path,
            original_sha256=version.original_sha256,
            sanitized_file_path=version.sanitized_file_path,
            sanitized_sha256=version.sanitized_sha256,
            metadata_snapshot={"title": "Otro"},
            metadata_sha256=version.metadata_sha256,
        )

        err = StringIO()
        with pytest.raises(CommandError, match="1 discrepancia"):
            call_command("verify_integrity", stdout=StringIO(), stderr=err)

        assert f"versión {sealed.pk}" in err.getvalue()
        assert "metadata_sha256" in err.getvalue()

    def test_missing_public_copy_is_reported(self, media_root) -> None:
        make_sealed_version(media_root)
        CatalogEntryFactory(is_active=True)

        err = StringIO()
        with pytest.raises(CommandError):
            call_command("verify_integrity", stdout=StringIO(), stderr=err)

        assert "copia pública ausente" in err.getvalue()

    def test_it_does_not_modify_files_or_records(self, media_root) -> None:
        version = make_sealed_version(media_root)
        target = media_root / "private" / version.sanitized_file_path
        target.write_bytes(b"manipulado")
        snapshot = (target.read_bytes(), version.sanitized_sha256)

        with pytest.raises(CommandError):
            run()

        version.refresh_from_db()
        assert (target.read_bytes(), version.sanitized_sha256) == snapshot


class TestAuditChain:
    def test_altered_row_breaks_its_hash(self, media_root) -> None:
        first = record("LOGIN")
        record("LOGOUT")
        tamper_audit("UPDATE audit_audit_log SET action = 'ADMIN' WHERE id = %s", [first.pk])

        err = StringIO()
        with pytest.raises(CommandError):
            call_command("verify_integrity", stdout=StringIO(), stderr=err)

        assert f"auditoría #{first.pk}" in err.getvalue()
        assert "entry_hash" in err.getvalue()

    def test_deleted_row_breaks_the_link(self, media_root) -> None:
        record("LOGIN")
        middle = record("REFRESH")
        last = record("LOGOUT")
        tamper_audit("DELETE FROM audit_audit_log WHERE id = %s", [middle.pk])

        err = StringIO()
        with pytest.raises(CommandError):
            call_command("verify_integrity", stdout=StringIO(), stderr=err)

        assert f"auditoría #{last.pk}" in err.getvalue()
        assert "previous_hash" in err.getvalue()

    def test_it_never_writes_to_the_audit_trail(self, media_root) -> None:
        record("LOGIN")
        tamper_audit("UPDATE audit_audit_log SET action = 'ADMIN'")
        before = list(AuditLog.objects.values_list("pk", "action", "entry_hash"))

        with pytest.raises(CommandError):
            run()

        assert list(AuditLog.objects.values_list("pk", "action", "entry_hash")) == before
