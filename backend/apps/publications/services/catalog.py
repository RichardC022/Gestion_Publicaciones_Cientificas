"""Public catalog: the copy of an accepted version (plan sections 4.7, 1.12).

``publish_version`` writes the public copy and inserts the active
:class:`~apps.publications.models.CatalogEntry`. The copy is generated
from the private original with the same sanitization pipeline as the
review copy (:meth:`PdfService.sanitize`), into a brand-new file under
``public/catalog``: it shares no inode with the original and is created
with ``O_CREAT | O_EXCL``, so nothing is overwritten. If the caller's
transaction fails afterwards, the file registered in ``rollback`` is
removed; a file that already existed is never touched.
"""

from __future__ import annotations

from django.utils import timezone

from apps.publications.models import CatalogEntry, Manuscript, ManuscriptVersion
from apps.publications.services.pdf import PdfService
from apps.publications.services.storage import (
    DIRECTORY_MODE,
    catalog_path,
    catalog_relative_path,
    private_path,
)
from apps.publications.services.versions import Rollback
from config.exceptions import DomainError, ErrorCode

ALREADY_PUBLISHED_MESSAGE = "El manuscrito ya tiene una entrada activa en el catálogo."


def publish_version(
    *,
    manuscript: Manuscript,
    version: ManuscriptVersion,
    pdf: PdfService,
    rollback: Rollback,
) -> CatalogEntry:
    """Generate the public copy of ``version`` and publish it.

    Call it inside the transaction that holds the manuscript lock.
    """
    already_active = CatalogEntry.objects.select_for_update().filter(
        manuscript=manuscript, is_active=True
    )
    if already_active.exists():
        raise DomainError(ALREADY_PUBLISHED_MESSAGE, code=ErrorCode.STATE_CONFLICT)

    relative = catalog_relative_path(manuscript.pk, version.pk)
    destination = catalog_path(relative)
    destination.parent.mkdir(mode=DIRECTORY_MODE, parents=True, exist_ok=True)
    pdf.sanitize(private_path(version.original_file_path), destination)
    # Registrada solo cuando la copia ya existe: un destino previo no se borra.
    rollback.files.append(destination)

    return CatalogEntry.objects.create(
        manuscript=manuscript,
        version=version,
        public_file_path=str(relative),
        published_at=timezone.now(),
    )
