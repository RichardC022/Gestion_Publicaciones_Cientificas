"""Formal versions: the core shared by v1 and every later version.

A formal version is the immutable record of one submission: the exact
PDF, its sanitized copy, ``metadata.json``, the canonical metadata
snapshot and the three SHA-256 seals (plan sections 4.2-4.5).

* :func:`create_formal_version` writes the files in a brand-new version
  directory and inserts the row. It is used by the initial submission
  (``submission.py``) and by :func:`submit_new_version`.
* :func:`run_formal_write` runs one of those operations in ONE
  transaction and guarantees the all-or-nothing contract: if anything
  fails — storage, sanitization or the audit — the database rolls back
  and the directories this call created are removed; a directory that
  already existed is never touched.
* :func:`submit_new_version` is ``POST /api/manuscripts/{id}/versions/``:
  from ``REQUIRES_CORRECTIONS``, it creates the next consecutive
  version, ties it to the current round (closing it), moves the
  manuscript back to ``SUBMITTED`` and keeps every previous version
  untouched. A submission that changes neither the PDF nor the metadata
  is rejected.
"""

from __future__ import annotations

import logging
import shutil
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, TypeVar
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
from apps.publications.services.manuscripts import missing_metadata
from apps.publications.services.pdf import PdfService, sha256_of_file
from apps.publications.services.snapshot import (
    build_metadata_snapshot,
    canonical_json,
    metadata_sha256,
)
from apps.publications.services.storage import (
    allocate_version_dir,
    copy_exclusive,
    remove_quietly,
    version_relative_dir,
    write_exclusive,
)
from apps.publications.services.uploads import check_declared_file, stage_upload
from apps.publications.signals import new_version_submitted
from apps.users.models import Role, User
from apps.users.services.auth import AUDIT_UNAVAILABLE_MESSAGE
from config.exceptions import DomainError, ErrorCode

logger = logging.getLogger(__name__)

T = TypeVar("T")

NOT_REQUIRES_CORRECTIONS_MESSAGE = (
    "Solo se puede enviar una nueva versión cuando el manuscrito requiere correcciones."
)
NO_CHANGES_MESSAGE = (
    "La nueva versión no cambia ni el PDF ni los metadatos; debe existir al menos una corrección."
)
STORAGE_MESSAGE = "No se pudo almacenar el manuscrito; el envío fue cancelado."


@dataclass(frozen=True)
class Submission:
    """What a formal submission created: the manuscript, its version and round."""

    manuscript: Manuscript
    version: ManuscriptVersion
    round: CorrectionRound


@dataclass
class Rollback:
    """Version directories created by the running operation.

    Only directories registered here are removed on failure, so a
    directory that already existed before the call is never deleted.
    """

    directories: list[Path] = field(default_factory=list)

    def discard(self) -> None:
        for directory in self.directories:
            shutil.rmtree(directory, ignore_errors=True)


def record_audit(
    action: str,
    manuscript_id: UUID,
    user: User,
    context: dict,
    *,
    result: str = AuditLog.Result.SUCCESS,
    **extra: Any,
) -> None:
    AuditService.record(
        action=action,
        entity_type="MANUSCRIPT",
        entity_id=manuscript_id,
        result=result,
        actor=user,
        actor_role=Role.Code.AUTHOR,
        **extra,
        **context,
    )


def _audit_failure(action: str, manuscript_id: UUID, user: User, context: dict, reason: str) -> None:
    """Leave a ``FAILURE`` event; it is written after the rollback, on its own."""
    try:
        with transaction.atomic():
            record_audit(
                action,
                manuscript_id,
                user,
                context,
                result=AuditLog.Result.FAILURE,
                reason=reason,
            )
    except AuditUnavailable:
        logger.warning("No se pudo auditar el fallo de %s en %s", action, manuscript_id)


def run_formal_write(
    *,
    action: str,
    manuscript_id: UUID,
    user: User,
    context: dict,
    work: Callable[[Rollback], T],
) -> T:
    """Run ``work`` in one transaction with the all-or-nothing guarantee."""
    rollback = Rollback()
    try:
        with transaction.atomic():
            return work(rollback)
    except AuditUnavailable as exc:
        rollback.discard()
        raise DomainError(AUDIT_UNAVAILABLE_MESSAGE, code=ErrorCode.AUDIT_UNAVAILABLE) from exc
    except OSError as exc:
        # Incluye FileExistsError: el directorio de la versión ya existía.
        rollback.discard()
        logger.error("Fallo de almacenamiento en %s de %s: %s", action, manuscript_id, exc)
        _audit_failure(
            action, manuscript_id, user, context, f"Fallo de almacenamiento ({type(exc).__name__})."
        )
        raise DomainError(STORAGE_MESSAGE, code=ErrorCode.STORAGE_UNAVAILABLE) from exc
    except BaseException:
        rollback.discard()
        raise


def create_formal_version(
    *,
    manuscript: Manuscript,
    user: User,
    source: Path,
    original_filename: str,
    version_number: int,
    round_number: int,
    snapshot: dict[str, Any],
    canonical: str,
    submitted_at: datetime,
    pdf: PdfService,
    rollback: Rollback,
) -> ManuscriptVersion:
    """Write ``original.pdf``, ``sanitized.pdf`` and ``metadata.json`` and insert the row.

    ``source`` is copied byte for byte (never moved or linked). The new
    directory is registered in ``rollback`` as soon as it exists.
    """
    directory = allocate_version_dir(manuscript.pk, version_number)
    rollback.directories.append(directory)

    original = directory / "original.pdf"
    sanitized = directory / "sanitized.pdf"
    copied = copy_exclusive(source, original)
    pdf.sanitize(original, sanitized)
    write_exclusive(directory / "metadata.json", canonical.encode("utf-8"))

    base = version_relative_dir(manuscript.pk, version_number)
    return ManuscriptVersion.objects.create(
        manuscript=manuscript,
        version_number=version_number,
        round_number=round_number,
        original_file_path=str(base / "original.pdf"),
        original_filename=original_filename,
        original_size_bytes=copied.size_bytes,
        original_sha256=copied.sha256,
        sanitized_file_path=str(base / "sanitized.pdf"),
        sanitized_sha256=sha256_of_file(sanitized),
        metadata_snapshot=snapshot,
        metadata_sha256=metadata_sha256(canonical),
        submitted_by=user,
        submitted_at=submitted_at,
    )


def ensure_requires_corrections(manuscript: Manuscript) -> None:
    """A new version only exists as the answer to a correction request (``409``)."""
    if not manuscript.is_active or manuscript.status != Manuscript.Status.REQUIRES_CORRECTIONS:
        raise DomainError(
            NOT_REQUIRES_CORRECTIONS_MESSAGE,
            code=ErrorCode.STATE_CONFLICT,
            details={"status": manuscript.status, "is_active": manuscript.is_active},
        )


def _notify_after_commit(manuscript_id: UUID, version_id: UUID, user_id: UUID) -> None:
    for receiver, error in new_version_submitted.send_robust(
        sender=Manuscript,
        manuscript_id=manuscript_id,
        version_id=version_id,
        submitted_by_id=user_id,
    ):
        if isinstance(error, Exception):
            logger.error("Un receptor de la nueva versión falló (%s): %s", receiver, error)


def submit_new_version(
    *,
    manuscript_id: UUID,
    user: User,
    uploaded: Any,
    idempotency_key: str,
    context: dict,
) -> Submission:
    """Create the next version from the uploaded PDF and the current metadata."""
    check_declared_file(uploaded)
    pdf = PdfService()
    staged = stage_upload(uploaded, pdf)
    try:
        # Antes de bloquear nada: un PDF inválido no cuesta una transacción.
        pdf.validate(staged)

        def work(rollback: Rollback) -> Submission:
            manuscript = (
                Manuscript.objects.select_for_update(of=("self",))
                .select_related("created_by")
                .get(pk=manuscript_id)
            )
            ensure_requires_corrections(manuscript)

            errors = missing_metadata(manuscript)
            if errors:
                raise DomainError(
                    "Complete los campos obligatorios antes de enviar la nueva versión.",
                    code=ErrorCode.VALIDATION_ERROR,
                    details=errors,
                )

            previous = ManuscriptVersion.objects.get(
                manuscript=manuscript, version_number=manuscript.current_version
            )
            snapshot = build_metadata_snapshot(manuscript)
            canonical = canonical_json(snapshot)
            pdf_changed = sha256_of_file(staged) != previous.original_sha256
            metadata_changed = metadata_sha256(canonical) != previous.metadata_sha256
            if not (pdf_changed or metadata_changed):
                raise DomainError(
                    NO_CHANGES_MESSAGE,
                    code=ErrorCode.VALIDATION_ERROR,
                    details={"changes": [NO_CHANGES_MESSAGE]},
                )

            current_round = (
                CorrectionRound.objects.select_for_update()
                .filter(manuscript=manuscript, round_number=manuscript.current_round)
                .first()
            )
            if current_round is None:
                raise DomainError(
                    "La ronda vigente del manuscrito no está registrada.",
                    code=ErrorCode.STATE_CONFLICT,
                )

            now = timezone.now()
            version_number = manuscript.current_version + 1
            version = create_formal_version(
                manuscript=manuscript,
                user=user,
                source=staged,
                original_filename=uploaded.name,
                version_number=version_number,
                round_number=current_round.round_number,
                snapshot=snapshot,
                canonical=canonical,
                submitted_at=now,
                pdf=pdf,
                rollback=rollback,
            )
            if current_round.closed_by_version_id is None:
                current_round.closed_by_version = version
                current_round.closed_at = now
                current_round.save(update_fields=("closed_by_version", "closed_at"))

            manuscript.status = Manuscript.Status.SUBMITTED
            manuscript.current_version = version_number
            manuscript.lock_version += 1
            manuscript.save(
                update_fields=("status", "current_version", "lock_version", "updated_at")
            )
            StatusEvent.objects.create(
                manuscript=manuscript,
                from_status=Manuscript.Status.REQUIRES_CORRECTIONS,
                to_status=Manuscript.Status.SUBMITTED,
                actor=user,
                metadata={
                    "version_number": version_number,
                    "round_number": current_round.round_number,
                },
            )
            record_audit(
                "MANUSCRIPT_VERSION_SUBMITTED",
                manuscript.pk,
                user,
                context,
                details={
                    "code": manuscript.code,
                    "version_number": version_number,
                    "round_number": current_round.round_number,
                    "original_sha256": version.original_sha256,
                    "sanitized_sha256": version.sanitized_sha256,
                    "metadata_sha256": version.metadata_sha256,
                    "changes": {"pdf": pdf_changed, "metadata": metadata_changed},
                    "idempotency_key": idempotency_key,
                },
            )
            transaction.on_commit(
                lambda: _notify_after_commit(manuscript.pk, version.pk, user.pk)
            )
            return Submission(manuscript=manuscript, version=version, round=current_round)

        return run_formal_write(
            action="MANUSCRIPT_VERSION_SUBMITTED",
            manuscript_id=manuscript_id,
            user=user,
            context=context,
            work=work,
        )
    finally:
        remove_quietly(staged)
