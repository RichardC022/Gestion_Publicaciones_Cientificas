"""PDF validation, sanitization and integrity hashes (plan sections 4.2-4.5).

``PdfService.validate`` is the security barrier of every upload: the
client-side check in Angular is only UX. It rejects, in this order, a
file over the size limit (``413``), an empty one, one without the
``%PDF-`` signature, one that cannot be opened — truncated or damaged,
without attempting any repair — an encrypted one, one without pages and
one carrying active content (``400``).

``PdfService.sanitize`` writes the copy a reviewer reads: no ``/Info``,
no XMP, no ``/PieceInfo``, no annotations and no active content. It
never modifies the source and never overwrites the destination. The
result is reopened and checked again, so a copy that still carries
active content is discarded and the upload rejected.

SHA-256 digests are computed in streaming so a 50 MB file is never held
in memory by the hashing code.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO

import pikepdf
from django.conf import settings

from apps.publications.services.storage import iter_file_chunks, open_exclusive
from config.exceptions import DomainError, ErrorCode

PDF_SIGNATURE = b"%PDF-"

#: Keys that only exist to run code or to hide files. ``/JS`` and ``/EF``
#: are the script body and the file specification of the same features.
ACTIVE_KEYS = (
    "/JavaScript",
    "/JS",
    "/OpenAction",
    "/AA",
    "/Launch",
    "/EmbeddedFiles",
    "/EF",
)

#: Action types (``/S``) that run code or launch programs.
ACTIVE_ACTIONS = ("/JavaScript", "/Launch")

#: Removed from the sanitized copy (page level and document level).
ROOT_KEYS_TO_STRIP = ("/OpenAction", "/AA", "/Metadata", "/PieceInfo", "/AcroForm")
NAME_TREES_TO_STRIP = ("/JavaScript", "/EmbeddedFiles")
PAGE_KEYS_TO_STRIP = ("/Annots", "/AA", "/Metadata", "/PieceInfo")

_MIB = 1024 * 1024


class PdfInvalid(DomainError):
    """The file is not an acceptable PDF (``400``)."""

    def __init__(self, message: str, *, details: Any = None) -> None:
        super().__init__(message, code=ErrorCode.PDF_INVALID, details=details)


class PdfTooLarge(DomainError):
    """The file exceeds the size limit (``413``)."""

    def __init__(self, max_bytes: int) -> None:
        super().__init__(
            f"El archivo supera el límite de {max_bytes // _MIB} MB.",
            code=ErrorCode.PDF_TOO_LARGE,
            details={"max_bytes": max_bytes},
        )


@dataclass(frozen=True)
class PdfInfo:
    """Facts about a validated PDF."""

    pages: int
    size_bytes: int


def sha256_of_chunks(chunks: Iterable[bytes]) -> str:
    """Hex SHA-256 of a stream of chunks."""
    digest = hashlib.sha256()
    for chunk in chunks:
        digest.update(chunk)
    return digest.hexdigest()


def sha256_of_file(path: Path) -> str:
    """Hex SHA-256 of a file, read in chunks."""
    return sha256_of_chunks(iter_file_chunks(path))


def _dictionaries(pdf: pikepdf.Pdf) -> Iterator[pikepdf.Dictionary]:
    """Every dictionary of the document, indirect or written inline.

    ``pdf.objects`` only lists indirect objects, and an action is often
    an inline dictionary, so the direct children are walked too. The walk
    is iterative: a hostile, deeply nested file cannot exhaust the stack.
    """
    stack: list[Any] = list(pdf.objects)
    while stack:
        current = stack.pop()
        if isinstance(current, pikepdf.Stream):
            current = current.stream_dict
        if isinstance(current, pikepdf.Dictionary):
            yield current
            children = current.values()
        elif isinstance(current, pikepdf.Array):
            children = current
        else:
            continue
        stack.extend(
            child
            for child in children
            if isinstance(child, pikepdf.Object) and not child.is_indirect
        )


def find_active_content(pdf: pikepdf.Pdf) -> list[str]:
    """Names of the active-content features present in the document."""
    found: set[str] = set()
    for dictionary in _dictionaries(pdf):
        found.update(key for key in ACTIVE_KEYS if key in dictionary)
        if dictionary.get("/S") in ACTIVE_ACTIONS:
            found.add(str(dictionary["/S"]))
        if dictionary.get("/Type") == "/EmbeddedFile":
            found.add("/EmbeddedFiles")
    return sorted(found)


class PdfService:
    """Validates uploads and produces the sanitized copy for review."""

    def __init__(self, max_bytes: int | None = None) -> None:
        self.max_bytes = settings.MAX_PDF_SIZE_BYTES if max_bytes is None else max_bytes

    def validate(self, source: Any) -> PdfInfo:
        """Validate an uploaded file (``.size``/``.read``/``.seek``) or a path."""
        if isinstance(source, (str, os.PathLike)):
            with open(source, "rb") as handle:
                return self._validate_stream(handle, os.fstat(handle.fileno()).st_size)
        return self._validate_stream(source, source.size)

    def _validate_stream(self, stream: BinaryIO, size: int) -> PdfInfo:
        if size > self.max_bytes:
            raise PdfTooLarge(self.max_bytes)
        if size == 0:
            raise PdfInvalid("El archivo está vacío.")

        stream.seek(0)
        if stream.read(len(PDF_SIGNATURE)) != PDF_SIGNATURE:
            raise PdfInvalid("El contenido del archivo no es un PDF.")
        stream.seek(0)

        try:
            # Sin recuperación: un archivo truncado o dañado se rechaza en
            # lugar de repararse en silencio.
            with pikepdf.open(stream, attempt_recovery=False) as pdf:
                if pdf.is_encrypted:
                    raise PdfInvalid("El PDF está protegido o cifrado.")
                pages = len(pdf.pages)
                if pages == 0:
                    raise PdfInvalid("El PDF no contiene páginas.")
                active = find_active_content(pdf)
        except PdfInvalid:
            raise
        except pikepdf.PasswordError as exc:
            raise PdfInvalid("El PDF está protegido con contraseña.") from exc
        except (pikepdf.PdfError, ValueError, RuntimeError) as exc:
            raise PdfInvalid("El PDF está dañado o no puede abrirse correctamente.") from exc

        if active:
            raise PdfInvalid(
                "El PDF contiene contenido activo no permitido.",
                details={"active_content": active},
            )
        stream.seek(0)
        return PdfInfo(pages=pages, size_bytes=size)

    def sanitize(self, source: Path, destination: Path) -> None:
        """Write the review copy of ``source`` to a NEW file ``destination``.

        ``FileExistsError`` if ``destination`` exists. The source is only
        read. If the copy cannot be produced or still carries active
        content, ``destination`` is removed and the upload is rejected.
        """
        try:
            with pikepdf.open(source, attempt_recovery=False) as pdf, open_exclusive(
                destination
            ) as handle:
                self._strip(pdf)
                pdf.save(handle, linearize=True)
            with pikepdf.open(destination, attempt_recovery=False) as produced:
                leftover = find_active_content(produced)
        except (pikepdf.PdfError, ValueError, RuntimeError) as exc:
            # `open_exclusive` ya eliminó la copia parcial que creó.
            raise PdfInvalid("No se pudo generar la copia sanitizada del PDF.") from exc

        if leftover:
            destination.unlink(missing_ok=True)
            raise PdfInvalid(
                "La copia sanitizada conserva contenido activo.",
                details={"active_content": leftover},
            )

    @staticmethod
    def _strip(pdf: pikepdf.Pdf) -> None:
        """Remove metadata, annotations and active content in place."""
        if "/Info" in pdf.trailer:
            del pdf.trailer["/Info"]

        root = pdf.Root
        for key in ROOT_KEYS_TO_STRIP:
            if key in root:
                del root[key]
        names = root.get("/Names")
        if names is not None:
            for key in NAME_TREES_TO_STRIP:
                if key in names:
                    del names[key]

        for page in pdf.pages:
            for key in PAGE_KEYS_TO_STRIP:
                if key in page:
                    del page[key]

        # XMP y datos de aplicación pueden colgar de cualquier objeto
        # (imágenes, fuentes, flujos de contenido).
        for dictionary in _dictionaries(pdf):
            for key in ("/Metadata", "/PieceInfo"):
                if key in dictionary:
                    del dictionary[key]
