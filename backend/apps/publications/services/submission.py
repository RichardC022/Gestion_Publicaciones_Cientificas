"""Formal submission: the draft becomes ``v1`` of round 0 (plan sections 4.2-4.5).

``submit_manuscript`` runs in ONE transaction that locks the manuscript
and, in this order: checks the state and the completeness of the
metadata, validates the draft PDF again, writes ``original.pdf``,
``sanitized.pdf`` and ``metadata.json`` in a brand-new version
directory, inserts the immutable version and round 0, moves the
manuscript to ``SUBMITTED``, records the status event and audits last
(the audit insert takes a global advisory lock, so it is held as
briefly as possible).

If ANY step fails the transaction rolls back and the version directory
this call created is removed; a directory that already existed is never
touched. The notifications are not sent inside the transaction: a
domain signal is emitted after the commit, and the consumed draft file
is deleted then too.
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.audit.services import AuditService, AuditUnavailable
from apps.publications.models import (
    CorrectionRound,
    Manuscript,
    ManuscriptVersion,
    StatusEvent,
)
from apps.publications.services.drafts import ensure_draft
from apps.publications.services.manuscripts import REQUIRED_METADATA, validate_author_roster
from apps.publications.services.pdf import PdfService, sha256_of_file
from apps.publications.services.snapshot import (
    build_metadata_snapshot,
    canonical_json,
    metadata_sha256,
)
from apps.publications.services.storage import (
    allocate_version_dir,
    copy_exclusive,
    private_path,
    remove_quietly,
    version_relative_dir,
    write_exclusive,
)
from apps.publications.signals import manuscript_submitted
from apps.users.models import Role, User
from apps.users.services.auth import AUDIT_UNAVAILABLE_MESSAGE
from config.exceptions import DomainError, ErrorCode

logger = logging.getLogger(__name__)

ALREADY_SUBMITTED_MESSAGE = (
    "Solo un manuscrito en borrador puede enviarse; si ya lo envió, el envío quedó registrado."
)
REQUIRED_MESSAGE = "Este campo es obligatorio."
STORAGE_MESSAGE = "No se pudo almacenar el manuscrito; el envío fue cancelado."


@dataclass(frozen=True)
class Submission:
    """What the formal submission created."""

    manuscript: Manuscript
    version: ManuscriptVersion
    round: CorrectionRound


def missing_requirements(manuscript: Manuscript) -> dict[str, list[str]]:
    """Every field that blocks the submission, keyed by field (CA-HU-04-05)."""
    errors: dict[str, list[str]] = {}
    for field in REQUIRED_METADATA:
        value = getattr(manuscript, field)
        if not (value.strip() if isinstance(value, str) else value):
            errors[field] = [REQUIRED_MESSAGE]

    roster = list(manuscript.authors.values_list("email", "is_corresponding"))
    try:
        validate_author_roster(roster, manuscript.created_by.email)
    except ValueError as exc:
        errors["authors"] = [str(exc)]

    if not manuscript.draft_file_path:
        errors["draft_file"] = ["Adjunte el PDF del manuscrito antes de enviarlo."]
    return errors


def _record(
    manuscript_id: UUID, user: User, context: dict, *, result: str, **details: Any
) -> None:
    AuditService.record(
        action="MANUSCRIPT_SUBMITTED",
        entity_type="MANUSCRIPT",
        entity_id=manuscript_id,
        result=result,
        actor=user,
        actor_role=Role.Code.AUTHOR,
        **details,
        **context,
    )


def _audit_failure(manuscript_id: UUID, user: User, context: dict, reason: str) -> None:
    """Leave a ``FAILURE`` event; it is written after the rollback, on its own."""
    try:
        with transaction.atomic():
            _record(
                manuscript_id,
                user,
                context,
                result=AuditLog.Result.FAILURE,
                reason=reason,
            )
    except AuditUnavailable:
        logger.warning("No se pudo auditar el fallo del envío de %s", manuscript_id)


def _after_commit(manuscript_id: UUID, version_id: UUID, user_id: UUID, draft: Path) -> None:
    """The draft is consumed and the listeners are told, once the data is safe."""
    remove_quietly(draft)
    for receiver, error in manuscript_submitted.send_robust(
        sender=Manuscript,
        manuscript_id=manuscript_id,
        version_id=version_id,
        submitted_by_id=user_id,
    ):
        if isinstance(error, Exception):
            logger.error("Un receptor del envío falló (%s): %s", receiver, error)


def submit_manuscript(*, manuscript_id: UUID, user: User, context: dict) -> Submission:
    """Create ``v1`` and round 0 from the draft and move to ``SUBMITTED``."""
    created_dir: Path | None = None
    try:
        with transaction.atomic():
            manuscript = (
                Manuscript.objects.select_for_update(of=("self",))
                .select_related("created_by")
                .get(pk=manuscript_id)
            )
            ensure_draft(manuscript, ALREADY_SUBMITTED_MESSAGE)

            errors = missing_requirements(manuscript)
            if errors:
                raise DomainError(
                    "Complete los campos obligatorios antes de enviar el manuscrito.",
                    code=ErrorCode.VALIDATION_ERROR,
                    details=errors,
                )

            draft = private_path(manuscript.draft_file_path)
            if not draft.is_file():
                raise DomainError(STORAGE_MESSAGE, code=ErrorCode.STORAGE_UNAVAILABLE)
            pdf = PdfService()
            pdf.validate(draft)

            version_number = manuscript.current_version + 1
            now = timezone.now()
            snapshot = build_metadata_snapshot(manuscript)
            canonical = canonical_json(snapshot)

            created_dir = allocate_version_dir(manuscript.pk, version_number)
            original = created_dir / "original.pdf"
            sanitized = created_dir / "sanitized.pdf"
            copied = copy_exclusive(draft, original)
            pdf.sanitize(original, sanitized)
            write_exclusive(created_dir / "metadata.json", canonical.encode("utf-8"))

            base = version_relative_dir(manuscript.pk, version_number)
            version = ManuscriptVersion.objects.create(
                manuscript=manuscript,
                version_number=version_number,
                round_number=0,
                original_file_path=str(base / "original.pdf"),
                original_filename=manuscript.draft_filename,
                original_size_bytes=copied.size_bytes,
                original_sha256=copied.sha256,
                sanitized_file_path=str(base / "sanitized.pdf"),
                sanitized_sha256=sha256_of_file(sanitized),
                metadata_snapshot=snapshot,
                metadata_sha256=metadata_sha256(canonical),
                submitted_by=user,
                submitted_at=now,
            )
            round_zero = CorrectionRound.objects.create(
                manuscript=manuscript,
                round_number=0,
                opened_at=now,
                closed_by_version=version,
                closed_at=now,
            )

            manuscript.status = Manuscript.Status.SUBMITTED
            manuscript.current_version = version_number
            manuscript.current_round = 0
            manuscript.lock_version += 1
            manuscript.draft_file_path = None
            manuscript.draft_filename = None
            manuscript.draft_size_bytes = None
            manuscript.draft_uploaded_at = None
            manuscript.save(
                update_fields=(
                    "status",
                    "current_version",
                    "current_round",
                    "lock_version",
                    "draft_file_path",
                    "draft_filename",
                    "draft_size_bytes",
                    "draft_uploaded_at",
                    "updated_at",
                )
            )
            StatusEvent.objects.create(
                manuscript=manuscript,
                from_status=Manuscript.Status.DRAFT,
                to_status=Manuscript.Status.SUBMITTED,
                actor=user,
                metadata={"version_number": version_number, "round_number": 0},
            )
            _record(
                manuscript.pk,
                user,
                context,
                result=AuditLog.Result.SUCCESS,
                details={
                    "code": manuscript.code,
                    "version_number": version_number,
                    "round_number": 0,
                    "original_sha256": version.original_sha256,
                    "sanitized_sha256": version.sanitized_sha256,
                    "metadata_sha256": version.metadata_sha256,
                },
            )

            transaction.on_commit(
                lambda: _after_commit(manuscript.pk, version.pk, user.pk, draft)
            )
    except AuditUnavailable as exc:
        _discard(created_dir)
        raise DomainError(AUDIT_UNAVAILABLE_MESSAGE, code=ErrorCode.AUDIT_UNAVAILABLE) from exc
    except OSError as exc:
        # Incluye FileExistsError: el directorio de la versión ya existía.
        _discard(created_dir)
        logger.error("Fallo de almacenamiento en el envío de %s: %s", manuscript_id, exc)
        _audit_failure(
            manuscript_id, user, context, f"Fallo de almacenamiento ({type(exc).__name__})."
        )
        raise DomainError(STORAGE_MESSAGE, code=ErrorCode.STORAGE_UNAVAILABLE) from exc
    except BaseException:
        _discard(created_dir)
        raise
    return Submission(manuscript=manuscript, version=version, round=round_zero)


def _discard(version_dir: Path | None) -> None:
    """Remove the version directory THIS call created; never a pre-existing one."""
    if version_dir is not None:
        shutil.rmtree(version_dir, ignore_errors=True)
