"""Normal verdict flow: decision, state change and publication (TSK-51).

``register_verdict`` is ``POST /api/editor/manuscripts/{id}/verdicts/``
without the HTTP layer. In ONE transaction, under the manuscript lock,
it checks the preconditions, appends the :class:`Verdict`, moves the
manuscript to its new state and, by decision:

* ``ACCEPTED`` — publishes the public copy in the catalog, synchronously;
* ``REJECTED`` — publishes nothing;
* ``REQUIRES_CORRECTIONS`` — opens the next correction round, keeps its
  reference to the verdict and increments ``current_round``.

If the public copy, the storage or the audit fail, nothing is kept: the
database rolls back and the copy this call wrote is removed. A version
has a single normal verdict (second one: ``VERDICT_CONFLICT``).

The administrative correction (CA-HU-13-12, TSK-78) goes through the same
function: if the manuscript has an ACTIVE :class:`VerdictCorrection` (TSK-77),
the new verdict links to the one it replaces (``previous_verdict`` comes from
the authorization, never from the client), the authorization is consumed in
the same transaction and the catalog follows the new decision: an accepted
manuscript is published (or its entry and copy restored), a rejected one or
one that requires corrections leaves the catalog. The original verdict and
``current_version`` are never touched; the audit event is ``VERDICT_CORRECTED``.
If any step fails the authorization stays active. Without an active
authorization a second verdict is still a ``409``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.publications.models import (
    CatalogEntry,
    CorrectionRound,
    Manuscript,
    StatusEvent,
    Verdict,
    VerdictCorrection,
)
from apps.publications.services.catalog import (
    discard_leftover_copy,
    ensure_public_copy,
    publish_version,
    remove_public_copy,
    retire_entry,
)
from apps.publications.services.corrections import consumption_problem
from apps.publications.services.idempotency import IdempotencyScope
from apps.publications.services.pdf import PdfService
from apps.publications.services.versions import (
    Rollback,
    audit_refusal,
    record_audit,
    run_formal_write,
)
from apps.publications.signals import verdict_registered
from apps.reviews.models import Evaluation
from apps.reviews.services.eligibility import has_conflict
from apps.users.models import Role, User
from config.exceptions import DomainError, ErrorCode

logger = logging.getLogger(__name__)

ACTION = "VERDICT_REGISTERED"
CORRECTED_ACTION = "VERDICT_CORRECTED"

CONFLICT_MESSAGE = "Un Editor con conflicto de interés no puede registrar el veredicto."
WITHDRAWN_MESSAGE = "El manuscrito fue dado de baja; no admite veredicto."
DUPLICATE_MESSAGE = "La versión evaluada ya tiene un veredicto registrado."
NOT_UNDER_REVIEW_MESSAGE = "Solo un manuscrito en revisión admite un veredicto."
NO_FINAL_EVALUATION_MESSAGE = (
    "Debe existir una evaluación final completa de la versión vigente antes del veredicto."
)
STALE_MESSAGE = "El manuscrito cambió desde que lo consultó; recargue e intente de nuevo."
JUSTIFICATION_REQUIRED_MESSAGE = (
    "Indique la justificación: el veredicto rechaza el manuscrito o se aparta de la recomendación."
)
OBSERVATIONS_REQUIRED_MESSAGE = "Indique las observaciones para solicitar correcciones."

#: Manuscript status that each decision produces.
STATUS_BY_DECISION = {
    Verdict.Decision.ACCEPTED: Manuscript.Status.ACCEPTED,
    Verdict.Decision.REJECTED: Manuscript.Status.REJECTED,
    Verdict.Decision.REQUIRES_CORRECTIONS: Manuscript.Status.REQUIRES_CORRECTIONS,
}

#: Decision that follows each reviewer recommendation.
DECISION_BY_RECOMMENDATION = {
    Evaluation.Recommendation.ACCEPT: Verdict.Decision.ACCEPTED,
    Evaluation.Recommendation.REJECT: Verdict.Decision.REJECTED,
    Evaluation.Recommendation.REQUIRES_CORRECTIONS: Verdict.Decision.REQUIRES_CORRECTIONS,
}


@dataclass(frozen=True)
class VerdictResult:
    """What registering a verdict created or changed."""

    manuscript: Manuscript
    verdict: Verdict
    catalog_entry: CatalogEntry | None
    opened_round: CorrectionRound | None
    correction: VerdictCorrection | None = None


class _Refusal(DomainError):
    """A refused attempt that must leave an audit event of its own.

    The transaction of the attempt rolls back, so the event is written
    afterwards, outside of it (CA-HU-13-08 and plan section 2.4).
    """

    def __init__(self, message: str, *, audit_result: str, **kwargs) -> None:
        super().__init__(message, **kwargs)
        self.audit_result = audit_result


def _validation_error(field: str, message: str) -> DomainError:
    return DomainError(message, code=ErrorCode.VALIDATION_ERROR, details={field: [message]})


def _clean(text: str | None) -> str | None:
    """Trimmed text, or ``None`` when blank."""
    return (text or "").strip() or None


def _check_decision(decision: str, justification: str | None, observations: str | None) -> None:
    if decision not in Verdict.Decision.values:
        raise _validation_error("decision", "Seleccione Aceptado, Rechazado o Requiere correcciones.")
    if decision == Verdict.Decision.REJECTED and justification is None:
        raise _validation_error("justification", JUSTIFICATION_REQUIRED_MESSAGE)
    if decision == Verdict.Decision.REQUIRES_CORRECTIONS and observations is None:
        raise _validation_error("observations", OBSERVATIONS_REQUIRED_MESSAGE)


def _announce(
    manuscript_id: UUID,
    verdict_id: UUID,
    decision: str,
    editor_id: UUID,
    previous_verdict_id: UUID | None = None,
) -> None:
    # `previous_verdict_id` viaja solo en una corrección: el contrato del veredicto
    # normal no cambia.
    extra = {} if previous_verdict_id is None else {"previous_verdict_id": previous_verdict_id}
    for receiver, error in verdict_registered.send_robust(
        sender=Manuscript,
        manuscript_id=manuscript_id,
        verdict_id=verdict_id,
        decision=decision,
        editor_id=editor_id,
        **extra,
    ):
        if isinstance(error, Exception):
            logger.error("Un receptor del veredicto falló (%s): %s", receiver, error)


def register_verdict(
    *,
    manuscript_id: UUID,
    editor: User,
    decision: str,
    justification: str | None = None,
    observations: str | None = None,
    expected_lock_version: int | None = None,
    context: dict,
    idempotency: IdempotencyScope | None = None,
) -> VerdictResult:
    """Register the verdict over the evaluated version of the manuscript."""
    justification, observations = _clean(justification), _clean(observations)
    _check_decision(decision, justification, observations)

    pdf = PdfService()

    def work(rollback: Rollback) -> VerdictResult:
        manuscript = (
            Manuscript.objects.select_for_update(of=("self",))
            .select_related("created_by")
            .get(pk=manuscript_id)
        )
        if has_conflict(manuscript, editor):
            raise _Refusal(
                CONFLICT_MESSAGE, code=ErrorCode.FORBIDDEN, audit_result=AuditLog.Result.DENIED
            )
        if not manuscript.is_active:
            raise _Refusal(
                WITHDRAWN_MESSAGE,
                code=ErrorCode.STATE_CONFLICT,
                details={"status": manuscript.status, "is_active": False},
                audit_result=AuditLog.Result.FAILURE,
            )
        # Una autorización activa del Administrador (CA-HU-13-12) es la única forma de
        # decidir de nuevo; el cliente no puede declararla (el cuerpo no tiene
        # `previous_verdict_id`): se deriva de la autorización, bloqueada aquí.
        correction = (
            VerdictCorrection.objects.select_for_update()
            .select_related("original_verdict__version", "original_verdict__evaluation")
            .filter(manuscript=manuscript, is_active=True)
            .first()
        )
        previous = correction.original_verdict if correction else None
        if correction is None:
            version = manuscript.versions.get(version_number=manuscript.current_version)
            if Verdict.objects.filter(version=version, previous_verdict__isnull=True).exists():
                raise DomainError(DUPLICATE_MESSAGE, code=ErrorCode.VERDICT_CONFLICT)
            if manuscript.status != Manuscript.Status.UNDER_REVIEW:
                raise DomainError(
                    NOT_UNDER_REVIEW_MESSAGE,
                    code=ErrorCode.STATE_CONFLICT,
                    details={"status": manuscript.status},
                )
            evaluation = (
                Evaluation.objects.select_for_update()
                .filter(version=version, status=Evaluation.Status.FINAL)
                .first()
            )
            if evaluation is None:
                raise DomainError(
                    NO_FINAL_EVALUATION_MESSAGE,
                    code=ErrorCode.STATE_CONFLICT,
                    details={"status": manuscript.status},
                )
        else:
            problem = consumption_problem(previous)
            if problem is not None:
                raise DomainError(
                    problem,
                    code=ErrorCode.CORRECTION_NOT_AUTHORIZED,
                    details={"verdict_id": str(previous.pk)},
                )
            version, evaluation = previous.version, previous.evaluation
        if expected_lock_version is not None and manuscript.lock_version != expected_lock_version:
            raise DomainError(
                STALE_MESSAGE,
                code=ErrorCode.VERSION_CONFLICT,
                details={"lock_version": manuscript.lock_version},
            )
        departs = DECISION_BY_RECOMMENDATION[evaluation.recommendation] != decision
        if departs and justification is None:
            raise _validation_error("justification", JUSTIFICATION_REQUIRED_MESSAGE)

        now = timezone.now()
        previous_status = manuscript.status
        verdict = Verdict.objects.create(
            manuscript=manuscript,
            version=version,
            evaluation=evaluation,
            editor=editor,
            decision=decision,
            justification=justification,
            observations=observations,
            previous_verdict=previous,
        )
        if correction is not None:
            correction.is_active = False
            correction.consumed_at = now
            correction.consumed_by_verdict = verdict
            correction.save(update_fields=("is_active", "consumed_at", "consumed_by_verdict"))

        catalog_entry = opened_round = retired_copy = None
        event_metadata = {"verdict_id": str(verdict.pk), "version_number": version.version_number}
        if correction is not None:
            event_metadata.update(
                previous_verdict_id=str(previous.pk), correction_id=str(correction.pk)
            )
        if decision == Verdict.Decision.ACCEPTED:
            manuscript.accepted_at = now
            active = (
                CatalogEntry.objects.select_for_update()
                .filter(manuscript=manuscript, is_active=True)
                .first()
                if correction is not None
                else None
            )
            if active is not None:
                catalog_entry = active
                ensure_public_copy(active, version, pdf=pdf, rollback=rollback)
            else:
                if correction is not None:
                    discard_leftover_copy(manuscript.pk, version.pk)
                catalog_entry = publish_version(
                    manuscript=manuscript, version=version, pdf=pdf, rollback=rollback
                )
        else:
            if correction is not None:
                # La decisión ya no es "aceptado": el artículo sale del catálogo y
                # la copia pública se borra tras el commit (plan sección 4.8, paso 7).
                manuscript.accepted_at = None
                retired_copy = retire_entry(manuscript.pk, now=now)
                if retired_copy:
                    transaction.on_commit(lambda path=retired_copy: remove_public_copy(path))
            if decision == Verdict.Decision.REQUIRES_CORRECTIONS and not (
                correction is not None
                and CorrectionRound.objects.filter(
                    manuscript=manuscript, closed_at__isnull=True
                ).exists()
            ):
                manuscript.current_round += 1
                opened_round = CorrectionRound.objects.create(
                    manuscript=manuscript,
                    round_number=manuscript.current_round,
                    opened_by_verdict=verdict,
                    opened_at=now,
                )
                event_metadata["round_number"] = opened_round.round_number

        manuscript.status = STATUS_BY_DECISION[decision]
        manuscript.lock_version += 1
        manuscript.save(
            update_fields=(
                "status",
                "current_round",
                "accepted_at",
                "lock_version",
                "updated_at",
            )
        )
        StatusEvent.objects.create(
            manuscript=manuscript,
            from_status=previous_status,
            to_status=manuscript.status,
            actor=editor,
            metadata=event_metadata,
        )
        audit_details = {
            "code": manuscript.code,
            "verdict_id": str(verdict.pk),
            "decision": decision,
            "version_number": version.version_number,
            "evaluation_id": str(evaluation.pk),
            "round_opened": opened_round.round_number if opened_round else None,
            "catalog_entry_id": str(catalog_entry.pk) if catalog_entry else None,
            "departs_from_recommendation": departs,
        }
        if correction is not None:
            audit_details.update(
                previous_verdict_id=str(previous.pk),
                previous_decision=previous.decision,
                correction_id=str(correction.pk),
            )
        record_audit(
            CORRECTED_ACTION if correction is not None else ACTION,
            manuscript.pk,
            editor,
            context,
            actor_role=Role.Code.EDITOR,
            details=audit_details,
        )
        previous_id = previous.pk if previous is not None else None
        transaction.on_commit(
            lambda: _announce(manuscript.pk, verdict.pk, decision, editor.pk, previous_id)
        )
        return VerdictResult(
            manuscript=manuscript,
            verdict=verdict,
            catalog_entry=catalog_entry,
            opened_round=opened_round,
            correction=correction,
        )

    try:
        return run_formal_write(
            action=ACTION,
            manuscript_id=manuscript_id,
            user=editor,
            context=context,
            work=work,
            idempotency=idempotency,
            actor_role=Role.Code.EDITOR,
        )
    except _Refusal as refusal:
        audit_refusal(
            ACTION,
            manuscript_id,
            editor,
            context,
            str(refusal.detail),
            result=refusal.audit_result,
            actor_role=Role.Code.EDITOR,
        )
        raise
