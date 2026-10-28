"""Read-only verification of the stored PDFs and sealed metadata (TSK-76).

For every manuscript version it recomputes the SHA-256 of the original and
of the sanitized PDF and compares them with the stored hashes, and checks
``metadata_sha256`` against its snapshot. For every active catalog entry it
checks that the public copy still exists. It only reads: no file and no row
is ever modified.
"""

from __future__ import annotations

from dataclasses import dataclass

from apps.publications.models import CatalogEntry, ManuscriptVersion
from apps.publications.services.pdf import sha256_of_file
from apps.publications.services.snapshot import canonical_json, metadata_sha256
from apps.publications.services.storage import catalog_path, private_path


@dataclass(frozen=True)
class FileDiscrepancy:
    """One stored artifact that no longer matches its record."""

    subject: str
    problem: str

    def __str__(self) -> str:
        return f"{self.subject}: {self.problem}"


@dataclass(frozen=True)
class FilesReport:
    files_checked: int
    discrepancies: list[FileDiscrepancy]


def _check_pdf(subject: str, relative: str, expected: str, found: list[FileDiscrepancy]) -> None:
    path = private_path(relative)
    try:
        actual = sha256_of_file(path)
    except FileNotFoundError:
        found.append(FileDiscrepancy(subject, f"archivo ausente ({relative})"))
    except OSError as exc:
        found.append(FileDiscrepancy(subject, f"no se pudo leer {relative}: {exc.strerror}"))
    else:
        if actual != expected:
            found.append(FileDiscrepancy(subject, f"hash distinto ({relative})"))


def verify_files() -> FilesReport:
    """Recompute PDF hashes, metadata seals and the catalog copies' presence."""
    found: list[FileDiscrepancy] = []
    files = 0
    for version in ManuscriptVersion.objects.order_by("manuscript_id", "version_number").iterator():
        label = f"versión {version.pk} (v{version.version_number})"
        _check_pdf(
            f"{label} original", version.original_file_path, version.original_sha256, found
        )
        _check_pdf(
            f"{label} sanitizado", version.sanitized_file_path, version.sanitized_sha256, found
        )
        files += 2
        if metadata_sha256(canonical_json(version.metadata_snapshot)) != version.metadata_sha256:
            found.append(FileDiscrepancy(label, "metadata_sha256 no coincide con el snapshot"))
    for entry in CatalogEntry.objects.filter(is_active=True).iterator():
        files += 1
        if not catalog_path(entry.public_file_path).is_file():
            found.append(
                FileDiscrepancy(
                    f"catálogo {entry.pk}", f"copia pública ausente ({entry.public_file_path})"
                )
            )
    return FilesReport(files_checked=files, discrepancies=found)
