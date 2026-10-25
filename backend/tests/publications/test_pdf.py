"""Tests for PDF validation, sanitization and hashes (TSK-33).

Covers the acceptance criteria:

1. A PDF of exactly 50 MB is accepted; 50 MB + 1 byte answers ``413``.
2. A truncated, empty or encrypted PDF, or one with ``/JavaScript``,
   ``/OpenAction``, ``/AA``, ``/Launch`` or ``/EmbeddedFiles``, is
   rejected with ``400``.
3. Sanitizing removes ``/Info``, XMP, ``/Metadata``, ``/PieceInfo``,
   annotations and active content, and never overwrites a file.
"""

from __future__ import annotations

import hashlib

import pikepdf
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.publications.services.pdf import (
    PdfInvalid,
    PdfService,
    PdfTooLarge,
    find_active_content,
    sha256_of_chunks,
    sha256_of_file,
)
from tests.publications import pdf_factory as factory

MAX_BYTES = 50 * factory.MIB


def upload(data: bytes, name: str = "articulo.pdf") -> SimpleUploadedFile:
    return SimpleUploadedFile(name, data, content_type="application/pdf")


@pytest.fixture(scope="module")
def exact_limit_pdf() -> bytes:
    return factory.pdf_of_size(MAX_BYTES)


@pytest.fixture
def service() -> PdfService:
    return PdfService()


class TestSizeLimit:
    def test_pdf_of_exactly_50_mb_is_accepted(self, service, exact_limit_pdf) -> None:
        assert len(exact_limit_pdf) == MAX_BYTES

        info = service.validate(upload(exact_limit_pdf))

        assert info.size_bytes == MAX_BYTES and info.pages == 1

    def test_one_byte_over_the_limit_answers_413(self, service, exact_limit_pdf) -> None:
        with pytest.raises(PdfTooLarge) as raised:
            service.validate(upload(exact_limit_pdf + b"\n"))

        assert raised.value.status_code == 413
        assert raised.value.error_code == "PDF_TOO_LARGE"
        assert raised.value.error_details == {"max_bytes": MAX_BYTES}

    def test_the_size_is_checked_before_parsing_anything(self, service) -> None:
        # Basura del tamaño límite + 1: se rechaza sin intentar abrirla.
        with pytest.raises(PdfTooLarge):
            service.validate(upload(b"%PDF-" + b"0" * MAX_BYTES))

    def test_the_limit_comes_from_the_settings(self, settings) -> None:
        settings.MAX_PDF_SIZE_BYTES = 100
        data = factory.clean_pdf()

        assert len(data) > 100
        with pytest.raises(PdfTooLarge):
            PdfService().validate(upload(data))


class TestValidPdf:
    def test_clean_pdf_is_accepted_with_its_page_count(self, service) -> None:
        info = service.validate(upload(factory.clean_pdf(pages=3)))

        assert info.pages == 3

    def test_validation_leaves_the_stream_at_the_start(self, service) -> None:
        uploaded = upload(factory.clean_pdf())

        service.validate(uploaded)

        assert uploaded.read(5) == b"%PDF-"

    def test_a_path_is_validated_like_an_upload(self, service, tmp_path) -> None:
        path = tmp_path / "borrador.pdf"
        path.write_bytes(factory.clean_pdf(pages=2))

        assert service.validate(path).pages == 2

    def test_a_misleading_extension_does_not_matter_only_the_content(self, service) -> None:
        assert service.validate(upload(factory.clean_pdf(), name="articulo.txt")).pages == 1


class TestRejectedPdf:
    @pytest.mark.parametrize(
        "data",
        [
            pytest.param(b"", id="vacío"),
            pytest.param(b"Esto no es un PDF", id="sin-firma"),
            pytest.param(b"MZ" + b"\x00" * 200, id="ejecutable"),
            pytest.param(b"%PDF-1.7\n" + b"basura" * 50, id="firma-sin-estructura"),
        ],
    )
    def test_content_that_is_not_a_readable_pdf_answers_400(self, service, data) -> None:
        with pytest.raises(PdfInvalid) as raised:
            service.validate(upload(data))

        assert raised.value.status_code == 400
        assert raised.value.error_code == "PDF_INVALID"

    @pytest.mark.parametrize("fraction", [0.3, 0.5, 0.9])
    def test_truncated_pdf_is_rejected_not_repaired(self, service, fraction) -> None:
        data = factory.clean_pdf(pages=5)

        with pytest.raises(PdfInvalid):
            service.validate(upload(data[: int(len(data) * fraction)]))

    def test_pdf_with_a_password_is_rejected(self, service) -> None:
        with pytest.raises(PdfInvalid):
            service.validate(upload(factory.encrypted_pdf("secreto")))

    def test_pdf_encrypted_without_a_user_password_is_rejected_too(self, service) -> None:
        with pytest.raises(PdfInvalid, match="protegido"):
            service.validate(upload(factory.encrypted_pdf("")))

    def test_pdf_without_pages_is_rejected(self, service) -> None:
        with pytest.raises(PdfInvalid, match="páginas"):
            service.validate(upload(factory.pdf_without_pages()))

    @pytest.mark.parametrize(
        "kind",
        ["/JavaScript", "/OpenAction", "/AA", "/Launch", "/EmbeddedFiles"],
    )
    def test_each_forbidden_active_content_is_rejected(self, service, kind) -> None:
        with pytest.raises(PdfInvalid) as raised:
            service.validate(upload(factory.pdf_with_active_content(kind)))

        assert kind in raised.value.error_details["active_content"]

    def test_inline_actions_are_found_too(self, service) -> None:
        with pytest.raises(PdfInvalid) as raised:
            service.validate(upload(factory.pdf_with_active_content("inline-javascript")))

        assert "/JavaScript" in raised.value.error_details["active_content"]

    def test_the_rejection_message_never_leaks_internal_errors(self, service) -> None:
        with pytest.raises(PdfInvalid) as raised:
            service.validate(upload(b"%PDF-1.7\n" + b"x" * 100))

        assert "Traceback" not in str(raised.value.detail)
        assert "qpdf" not in str(raised.value.detail).lower()


def make_source(tmp_path, data: bytes):
    source = tmp_path / "original.pdf"
    source.write_bytes(data)
    return source


class TestSanitize:
    def test_identity_metadata_annotations_and_forms_are_removed(self, tmp_path, service) -> None:
        source = make_source(tmp_path, factory.pdf_with_identity())
        destination = tmp_path / "sanitized.pdf"

        service.sanitize(source, destination)

        with pikepdf.open(destination) as pdf:
            assert "/Info" not in pdf.trailer
            assert "/Metadata" not in pdf.Root
            assert "/PieceInfo" not in pdf.Root
            assert "/AcroForm" not in pdf.Root
            page = pdf.pages[0]
            assert "/Annots" not in page and "/PieceInfo" not in page
        assert b"Ana" not in destination.read_bytes()

    def test_active_content_is_removed_from_the_copy(self, tmp_path, service) -> None:
        for kind in ("/JavaScript", "/OpenAction", "/AA", "/Launch", "/EmbeddedFiles"):
            source = make_source(tmp_path, factory.pdf_with_active_content(kind))
            destination = tmp_path / f"sanitized{kind.strip('/')}.pdf"

            service.sanitize(source, destination)

            with pikepdf.open(destination) as pdf:
                assert find_active_content(pdf) == [], kind

    def test_the_copy_keeps_the_pages_and_passes_validation(self, tmp_path, service) -> None:
        source = make_source(tmp_path, factory.pdf_with_identity())
        destination = tmp_path / "sanitized.pdf"

        service.sanitize(source, destination)

        assert service.validate(destination).pages == 1
        with pikepdf.open(destination) as pdf:
            assert pdf.is_linearized

    def test_the_source_is_never_modified(self, tmp_path, service) -> None:
        source = make_source(tmp_path, factory.pdf_with_identity())
        before = sha256_of_file(source)

        service.sanitize(source, tmp_path / "sanitized.pdf")

        assert sha256_of_file(source) == before
        with pikepdf.open(source) as pdf:
            assert pdf.docinfo["/Author"] == "Ana López"

    def test_an_existing_destination_is_never_overwritten(self, tmp_path, service) -> None:
        source = make_source(tmp_path, factory.clean_pdf())
        destination = tmp_path / "sanitized.pdf"
        destination.write_bytes(b"copia previa")

        with pytest.raises(FileExistsError):
            service.sanitize(source, destination)

        assert destination.read_bytes() == b"copia previa"

    def test_an_unreadable_source_is_rejected_and_leaves_no_copy(self, tmp_path, service) -> None:
        source = make_source(tmp_path, b"%PDF-1.7\nbasura")
        destination = tmp_path / "sanitized.pdf"

        with pytest.raises(PdfInvalid):
            service.sanitize(source, destination)

        assert not destination.exists()

    def test_a_copy_that_keeps_active_content_is_discarded(self, tmp_path, service, monkeypatch) -> None:
        source = make_source(tmp_path, factory.pdf_with_active_content("/JavaScript"))
        destination = tmp_path / "sanitized.pdf"
        monkeypatch.setattr(PdfService, "_strip", staticmethod(lambda pdf: None))

        with pytest.raises(PdfInvalid, match="conserva contenido activo"):
            service.sanitize(source, destination)

        assert not destination.exists()


class TestHashes:
    def test_hash_of_chunks_matches_hashlib(self) -> None:
        data = b"manuscrito" * 100_000

        digest = sha256_of_chunks(data[i : i + 4096] for i in range(0, len(data), 4096))

        assert digest == hashlib.sha256(data).hexdigest()

    def test_hash_of_a_50_mb_file_is_streamed(self, tmp_path, exact_limit_pdf) -> None:
        path = tmp_path / "grande.pdf"
        path.write_bytes(exact_limit_pdf)

        assert sha256_of_file(path) == hashlib.sha256(exact_limit_pdf).hexdigest()
        assert len(sha256_of_file(path)) == 64
