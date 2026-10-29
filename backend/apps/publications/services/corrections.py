"""Administrative authorization of a verdict correction (CA-HU-13-12, TSK-77).

Only an administrator can enable a new decision over a verdict that
contains an error, and only over the LATEST verdict of the manuscript,
while no later version exists and no other authorization is active. The
authorization never edits the verdict (append-only) and the administrator
never reaches the manuscript, the evaluations or the PDF: the service
reads the verdict row and the code of its manuscript, nothing else.
Consuming the authorization belongs to the editor's verdict (TSK-78).

``eligibility_problem`` is the single rule behind both the ``409`` of
the endpoint and the ``can_authorize_correction`` flag of the audit
detail, so the SPA never infers it.
"""

from __future__ import annotations

import logging
from uuid import UUID

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.audit.services import AuditService
from apps.publications.models import (
    Manuscript,
    ManuscriptVersion,
    Verdict,
    VerdictCorrection,
)
from apps.publications.services.idempotency import IdempotencyScope
from apps.publications.services.versions import Rollback, run_formal_write
from apps.publications.signals import verdict_correction_authorized
from apps.users.models import Role, User
from config.exceptions import DomainError, ErrorCode

logger = logging.getLogger(__name__)

ACTION = "VERDICT_CORRECTION_AUTHORIZED"
ENTITY_TYPE = "VERDICT_CORRECTION"

WITHDRAWN_MESSAGE = "El manuscrito está dado de baja; no admite una nueva decisión."
STALE_MESSAGE = "El veredicto está desactualizado: ya existe una decisión más reciente."
LATER_VERSION_MESSAGE = "El manuscrito ya tiene una versión posterior al veredicto."
ALREADY_AUTHORIZED_MESSAGE = "Este veredicto ya tiene una autorización de corrección activa."
NOT_FOUND_MESSAGE = "Veredicto no encontrado."


def eligibility_problem(verdict: Verdict) -> str | None:
    """Why a correction cannot be authorized over ``verdict``, or ``None`` if it can."""
    if not Manuscript.objects.filter(pk=verdict.manuscript_id, is_active=True).exists():
        return WITHDRAWN_MESSAGE
    latest = (
        Verdict.objects.filter(manuscript_id=verdict.manuscript_id)
        .order_by("-created_at", "-id")
        .values_list("pk", flat=True)
        .first()
    )
    if latest != verdict.pk:
        return STALE_MESSAGE
    if ManuscriptVersion.objects.filter(
        manuscript_id=verdict.manuscript_id,
        version_number__gt=verdict.version.version_number,
    ).exists():
        return LATER_VERSION_MESSAGE
    if VerdictCorrection.objects.filter(original_verdict=verdict, is_active=True).exists():
        return ALREADY_AUTHORIZED_MESSAGE
    return None


def can_authorize_correction(verdict: Verdict) -> bool:
    return eligibility_problem(verdict) is None


def _announce(manuscript_id: UUID, verdict_id: UUID, correction_id: UUID) -> None:
    for receiver, error in verdict_correction_authorized.send_robust(
        sender=Manuscript,
        manuscript_id=manuscript_id,
        verdict_id=verdict_id,
        correction_id=correction_id,
    ):
        if isinstance(error, Exception):
            logger.error("Un receptor de la corrección falló (%s): %s", receiver, error)


def authorize_correction(
    *,
    verdict_id: UUID,
    admin: User,
    reason: str,
    context: dict,
    idempotency: IdempotencyScope | None = None,
) -> VerdictCorrection:
    """Create the authorization in one transaction, audited and idempotent."""
    manuscript_id = (
        Verdict.objects.filter(pk=verdict_id).values_list("manuscript_id", flat=True).first()
    )
    if manuscript_id is None:
        raise DomainError(NOT_FOUND_MESSAGE, code=ErrorCode.NOT_FOUND)

    def work(rollback: Rollback) -> VerdictCorrection:
        # El mismo candado que toman el envío de versiones y el veredicto:
        # quien llega segundo ve el estado ya cambiado y recibe 409.
        manuscript = Manuscript.objects.select_for_update(of=("self",)).get(pk=manuscript_id)
        verdict = Verdict.objects.select_related("version").get(pk=verdict_id)
        problem = eligibility_problem(verdict)
        if problem is not None:
            raise DomainError(
                problem,
                code=ErrorCode.CORRECTION_NOT_AUTHORIZED,
                details={"verdict_id": str(verdict.pk)},
            )
        try:
            with transaction.atomic():
                correction = VerdictCorrection.objects.create(
                    manuscript=manuscript,
                    original_verdict=verdict,
                    authorized_by=admin,
                    reason=reason,
                    authorized_at=timezone.now(),
                )
        except IntegrityError as exc:
            # Dos autorizaciones simultáneas: el índice parcial deja pasar una.
            raise DomainError(
                ALREADY_AUTHORIZED_MESSAGE,
                code=ErrorCode.CORRECTION_NOT_AUTHORIZED,
                details={"verdict_id": str(verdict.pk)},
            ) from exc
        AuditService.record(
            action=ACTION,
            entity_type=ENTITY_TYPE,
            entity_id=correction.pk,
            actor=admin,
            actor_role=Role.Code.ADMIN,
            reason=reason,
            details={
                "manuscript_id": str(manuscript.pk),
                "code": manuscript.code,
                "verdict_id": str(verdict.pk),
                "decision": verdict.decision,
                "version_number": verdict.version.version_number,
            },
            **context,
        )
        transaction.on_commit(lambda: _announce(manuscript.pk, verdict.pk, correction.pk))
        return correction

    return run_formal_write(
        action=ACTION,
        manuscript_id=manuscript_id,
        user=admin,
        context=context,
        work=work,
        idempotency=idempotency,
        actor_role=Role.Code.ADMIN,
    )
