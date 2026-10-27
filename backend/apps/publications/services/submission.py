"""Formal submission: the draft becomes ``v1`` of round 0 (plan sections 4.2-4.5).

``submit_manuscript`` runs in ONE transaction that locks the manuscript
and, in this order: checks the state and the completeness of the
metadata, validates the draft PDF again, creates the version through
the shared core (``versions.py``: ``original.pdf``, ``sanitized.pdf``,
``metadata.json`` and the immutable row), inserts round 0, moves the
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
from pathlib import Path
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from apps.publications.models import (
    CorrectionRound,
    Manuscript,
    StatusEvent,
)
from apps.publications.services.drafts import ensure_draft
from apps.publications.services.idempotency import IdempotencyScope
from apps.publications.services.manuscripts import missing_metadata
from apps.publications.services.pdf import PdfService
from apps.publications.services.snapshot import build_metadata_snapshot, canonical_json
from apps.publications.services.storage import private_path, remove_quietly
from apps.publications.services.versions import (
    Rollback,
    Submission,
    create_formal_version,
    record_audit,
    run_formal_write,
)
from apps.publications.signals import manuscript_submitted
from apps.users.models import User
from config.exceptions import DomainError, ErrorCode

logger = logging.getLogger(__name__)

ALREADY_SUBMITTED_MESSAGE = (
    "Solo un manuscrito en borrador puede enviarse; si ya lo envió, el envío quedó registrado."
)
STORAGE_MESSAGE = "No se pudo almacenar el manuscrito; el envío fue cancelado."

__all__ = ["ALREADY_SUBMITTED_MESSAGE", "Submission", "missing_requirements", "submit_manuscript"]


def missing_requirements(manuscript: Manuscript) -> dict[str, list[str]]:
    """Every field that blocks the submission, keyed by field (CA-HU-04-05)."""
    errors = missing_metadata(manuscript)
    if not manuscript.draft_file_path:
        errors["draft_file"] = ["Adjunte el PDF del manuscrito antes de enviarlo."]
    return errors


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


def submit_manuscript(
    *,
    manuscript_id: UUID,
    user: User,
    idempotency_key: str,
    context: dict,
    idempotency: IdempotencyScope | None = None,
) -> Submission:
    """Create ``v1`` and round 0 from the draft and move to ``SUBMITTED``."""

    def work(rollback: Rollback) -> Submission:
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
        version = create_formal_version(
            manuscript=manuscript,
            user=user,
            source=draft,
            original_filename=manuscript.draft_filename,
            version_number=version_number,
            round_number=0,
            snapshot=snapshot,
            canonical=canonical_json(snapshot),
            submitted_at=now,
            pdf=pdf,
            rollback=rollback,
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
        record_audit(
            "MANUSCRIPT_SUBMITTED",
            manuscript.pk,
            user,
            context,
            details={
                "code": manuscript.code,
                "version_number": version_number,
                "round_number": 0,
                "original_sha256": version.original_sha256,
                "sanitized_sha256": version.sanitized_sha256,
                "metadata_sha256": version.metadata_sha256,
                "idempotency_key": idempotency_key,
            },
        )

        transaction.on_commit(
            lambda: _after_commit(manuscript.pk, version.pk, user.pk, draft)
        )
        return Submission(manuscript=manuscript, version=version, round=round_zero)

    return run_formal_write(
        action="MANUSCRIPT_SUBMITTED",
        manuscript_id=manuscript_id,
        user=user,
        context=context,
        work=work,
        idempotency=idempotency,
    )
