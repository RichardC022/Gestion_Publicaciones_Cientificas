"""Upload and replacement of the draft PDF (plan sections 2.3 and 4.2).

The draft is a replaceable file that belongs to a ``DRAFT`` manuscript.
It is NOT a version: uploading it creates no version, round or metadata
snapshot, and it never enters the history. The formal submission
(TSK-35) is what turns it into ``v1``.

Order of work, so a failure never leaves a half-done upload:

1. The upload is staged in ``tmp/uploads`` and validated there with
   :class:`~apps.publications.services.pdf.PdfService`.
2. The valid file is moved, without overwriting, to
   ``drafts/<user_uuid>/<draft_uuid>.pdf`` of the private volume.
3. One transaction locks the manuscript, re-checks its state, points it
   to the new file and audits. Any failure removes the new file and the
   previous draft stays intact.
4. Only after the commit the replaced draft is deleted.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from django.db import transaction
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.audit.services import AuditService, AuditUnavailable
from apps.publications.models import Manuscript
from apps.publications.services.pdf import PdfService
from apps.publications.services.storage import (
    draft_relative_path,
    move_exclusive,
    private_path,
    remove_quietly,
)
from apps.publications.services.uploads import check_declared_file, stage_upload
from apps.users.models import Role, User
from apps.users.services.auth import AUDIT_UNAVAILABLE_MESSAGE
from config.exceptions import DomainError, ErrorCode


@dataclass(frozen=True)
class DraftUpload:
    """Result of an upload: the manuscript and whether it replaced a draft."""

    manuscript: Manuscript
    replaced: bool


NOT_A_DRAFT_MESSAGE = (
    "Solo se puede adjuntar el PDF de borrador mientras el manuscrito es un borrador."
)


def ensure_draft(manuscript: Manuscript, message: str = NOT_A_DRAFT_MESSAGE) -> None:
    """The manuscript must still be an active ``DRAFT`` (otherwise ``409``)."""
    if not manuscript.is_active or manuscript.status != Manuscript.Status.DRAFT:
        raise DomainError(
            message,
            code=ErrorCode.STATE_CONFLICT,
            details={"status": manuscript.status, "is_active": manuscript.is_active},
        )


def attach_draft_file(
    *, manuscript_id, user: User, uploaded: Any, context: dict
) -> DraftUpload:
    """Validate and store the draft PDF, replacing the previous one."""
    check_declared_file(uploaded)
    service = PdfService()

    staged = stage_upload(uploaded, service)
    final: Path | None = None
    try:
        service.validate(staged)
        relative = draft_relative_path(user.pk, uuid4())
        final = private_path(relative)
        move_exclusive(staged, final)
    except BaseException:
        remove_quietly(staged)
        raise

    try:
        with transaction.atomic():
            manuscript = Manuscript.objects.select_for_update().get(pk=manuscript_id)
            ensure_draft(manuscript)

            previous = manuscript.draft_file_path
            manuscript.draft_file_path = str(relative)
            manuscript.draft_filename = uploaded.name
            manuscript.draft_size_bytes = uploaded.size
            manuscript.draft_uploaded_at = timezone.now()
            # El borrador no es metadato: no cambia lock_version (el ETag del
            # PATCH sigue vigente) y solo se tocan estas columnas.
            manuscript.save(
                update_fields=(
                    "draft_file_path",
                    "draft_filename",
                    "draft_size_bytes",
                    "draft_uploaded_at",
                    "updated_at",
                )
            )
            AuditService.record(
                action="MANUSCRIPT_DRAFT_FILE_REPLACED"
                if previous
                else "MANUSCRIPT_DRAFT_FILE_UPLOADED",
                entity_type="MANUSCRIPT",
                entity_id=manuscript.pk,
                result=AuditLog.Result.SUCCESS,
                actor=user,
                actor_role=Role.Code.AUTHOR,
                # Solo tamaño: el nombre del archivo puede contener identidad.
                details={"size_bytes": uploaded.size, "replaced": previous is not None},
                **context,
            )
    except AuditUnavailable as exc:
        remove_quietly(final)
        raise DomainError(AUDIT_UNAVAILABLE_MESSAGE, code=ErrorCode.AUDIT_UNAVAILABLE) from exc
    except BaseException:
        remove_quietly(final)
        raise

    if previous:
        remove_quietly(private_path(previous))
    return DraftUpload(manuscript=manuscript, replaced=previous is not None)
