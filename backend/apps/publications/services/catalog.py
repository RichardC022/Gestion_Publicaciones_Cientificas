"""Public catalog: the copy of an accepted version (plan sections 4.7, 1.12).

``publish_version`` writes the public copy and inserts the active
:class:`~apps.publications.models.CatalogEntry`. The copy is generated
from the private original with the same sanitization pipeline as the
review copy (:meth:`PdfService.sanitize`), into a brand-new file under
``public/catalog``: it shares no inode with the original and is created
with ``O_CREAT | O_EXCL``, so nothing is overwritten. If the caller's
transaction fails afterwards, the file registered in ``rollback`` is
removed; a file that already existed is never touched.

The read side (TSK-74) lives here too: :func:`public_entries` is the ONLY
queryset the anonymous endpoints start from. It keeps accepted, active
manuscripts with an active entry, so a draft, a manuscript in review, a
rejected one or a withdrawn one never reaches a public serializer, and
:func:`retire_entry` / :func:`remove_public_copy` take an article out when
its manuscript is withdrawn (plan section 4.8, steps 5 and 7).
"""

from __future__ import annotations

import logging
from uuid import UUID

from django.contrib.postgres.search import SearchQuery
from django.db.models import Exists, OuterRef, Q, QuerySet
from django.utils import timezone

from apps.publications.models import (
    CatalogEntry,
    Manuscript,
    ManuscriptAuthor,
    ManuscriptVersion,
)
from apps.publications.services.pdf import PdfService
from apps.publications.services.storage import (
    DIRECTORY_MODE,
    catalog_path,
    catalog_relative_path,
    private_path,
)
from apps.publications.services.versions import Rollback
from config.exceptions import DomainError, ErrorCode

logger = logging.getLogger(__name__)

ALREADY_PUBLISHED_MESSAGE = "El manuscrito ya tiene una entrada activa en el catálogo."
ORDERING_FIELDS = {"published_at": "published_at", "title": "manuscript__title"}
DEFAULT_ORDERING = "-published_at"


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


def retire_entry(manuscript_id: UUID, *, now=None) -> str | None:
    """Deactivate the manuscript's active entry; return its public path, if any.

    Call it inside the withdrawal's transaction (plan section 4.8, step 5).
    The file is NOT touched here: it is removed after the commit by
    :func:`remove_public_copy`, so a rollback never leaves an active entry
    without its copy.
    """
    entry = (
        CatalogEntry.objects.select_for_update()
        .filter(manuscript_id=manuscript_id, is_active=True)
        .first()
    )
    if entry is None:
        return None
    entry.is_active = False
    entry.unpublished_at = now or timezone.now()
    entry.save(update_fields=("is_active", "unpublished_at"))
    return entry.public_file_path


def remove_public_copy(relative_path: str) -> None:
    """Delete a retired public copy; a failure is logged, never raised.

    The entry is already inactive, so the catalog no longer shows the
    article even if the file stays behind; ``verify_integrity`` and the
    next withdrawal sweep are the safety net.
    """
    try:
        catalog_path(relative_path).unlink(missing_ok=True)
    except OSError:
        logger.exception("No se pudo eliminar la copia pública %s", relative_path)


def public_entries() -> QuerySet[CatalogEntry]:
    """Entries any visitor may see: active, of an accepted and active manuscript."""
    return (
        CatalogEntry.objects.filter(
            is_active=True,
            manuscript__status=Manuscript.Status.ACCEPTED,
            manuscript__is_active=True,
        )
        .select_related("manuscript", "version")
        .prefetch_related("manuscript__authors")
    )


def retired_article_exists(code: str) -> bool:
    """An accepted manuscript whose public article was taken down (``410``)."""
    return CatalogEntry.objects.filter(
        manuscript__code=code, manuscript__status=Manuscript.Status.ACCEPTED
    ).exists()


def search_entries(queryset: QuerySet[CatalogEntry], params: dict) -> QuerySet[CatalogEntry]:
    """Apply the validated public filters and the ordering."""
    term = params.get("search")
    if term:
        by_author = ManuscriptAuthor.objects.filter(manuscript=OuterRef("manuscript_id")).filter(
            Q(full_name__icontains=term) | Q(affiliation__icontains=term)
        )
        queryset = queryset.filter(
            Q(manuscript__search_vector=SearchQuery(term, config="spanish", search_type="websearch"))
            | Q(manuscript__title__icontains=term)
            | Q(manuscript__code__icontains=term)
            | Q(manuscript__area__icontains=term)
            | Exists(by_author)
        )
    if "area" in params:
        queryset = queryset.filter(manuscript__area__iexact=params["area"])
    if "language" in params:
        queryset = queryset.filter(manuscript__language=params["language"])
    if "keyword" in params:
        queryset = queryset.filter(manuscript__keywords__contains=[params["keyword"]])
    if "date_from" in params:
        queryset = queryset.filter(published_at__date__gte=params["date_from"])
    if "date_to" in params:
        queryset = queryset.filter(published_at__date__lte=params["date_to"])
    ordering = params.get("ordering", DEFAULT_ORDERING)
    descending = ordering.startswith("-")
    column = ORDERING_FIELDS[ordering.lstrip("-")]
    return queryset.order_by(f"-{column}" if descending else column, "id")
