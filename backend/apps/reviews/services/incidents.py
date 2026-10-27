"""Confidential incident reports and their editorial resolution (TSK-64).

The reviewer files a report about an ``ACTIVE`` assignment; the editor
resolves it exactly once (CA-HU-16-06). Both actions run in ONE
transaction that also records the audit: if the audit trail is
unavailable nothing is kept and the answer is ``503``.

Resolutions:

* ``REQUEST_ANONYMIZED_VERSION`` — the manuscript goes from
  ``UNDER_REVIEW`` to ``REQUIRES_CORRECTIONS``, a new round opens (without
  a verdict: this is the audited, one-off exception to the ordinary
  transition) and the active assignment is revoked. The round is linked
  from the report.
* ``REASSIGN`` — the active assignment is revoked and the manuscript stays
  ``UNDER_REVIEW`` waiting for a new reviewer.
* ``DISMISS`` — the report is closed; no state and no assignment change.

The author never learns who reported or that a report exists: the status
event the resolution writes carries a fixed text, and the report, its
description and the reviewer are only reachable through the editor module.
Locks are taken manuscript, then assignment, then report.
"""

from __future__ import annotations

from uuid import UUID

from django.db import IntegrityError, transaction
from django.db.models.functions import Now

from apps.audit.models import AuditLog
from apps.audit.services import AuditService
from apps.publications.models import CorrectionRound, Manuscript, StatusEvent
from apps.reviews.models import Assignment, IncidentReport
from apps.reviews.services.assignments import (
    record_editor_audit,
    revoke_for_incident,
    run_audited,
)
from apps.reviews.services.evaluations import NOT_FOUND_MESSAGE, locked_assignment
from apps.reviews.signals import announce, incident_reported, incident_resolved
from apps.users.models import Role, User
from config.exceptions import DomainError, ErrorCode

NOT_ACTIVE_MESSAGE = "Solo una asignación activa permite reportar un incidente."
ALREADY_OPEN_MESSAGE = "Ya existe un reporte abierto para esta asignación."
ALREADY_RESOLVED_MESSAGE = "El incidente ya fue resuelto."
NOT_UNDER_REVIEW_MESSAGE = (
    "Solo un manuscrito activo en revisión admite solicitar una versión anonimizada "
    "o reasignar."
)
#: Shown to the author in the manuscript history: it names no reviewer and no report.
ANONYMIZED_REQUEST_REASON = "Se solicita una versión anonimizada del manuscrito."


def report_incident(
    *,
    assignment_id: UUID,
    reviewer: User,
    report_type: str,
    description: str,
    context: dict,
) -> IncidentReport:
    """File a confidential report; the evaluation, the PDF and the manuscript are not touched."""

    def work() -> IncidentReport:
        assignment = locked_assignment(assignment_id, reviewer)
        if assignment.status != Assignment.Status.ACTIVE:
            raise DomainError(
                NOT_ACTIVE_MESSAGE,
                code=ErrorCode.STATE_CONFLICT,
                details={"status": assignment.status},
            )
        if IncidentReport.objects.filter(
            assignment=assignment, status=IncidentReport.Status.OPEN
        ).exists():
            raise DomainError(ALREADY_OPEN_MESSAGE, code=ErrorCode.STATE_CONFLICT)
        try:
            with transaction.atomic():
                incident = IncidentReport.objects.create(
                    assignment=assignment,
                    manuscript=assignment.manuscript,
                    reporter=reviewer,
                    report_type=report_type,
                    description=description,
                )
        except IntegrityError as exc:
            raise DomainError(ALREADY_OPEN_MESSAGE, code=ErrorCode.STATE_CONFLICT) from exc

        AuditService.record(
            action="IDENTITY_LEAK_REPORTED",
            entity_type="INCIDENT_REPORT",
            entity_id=incident.pk,
            result=AuditLog.Result.SUCCESS,
            actor=reviewer,
            actor_role=Role.Code.REVIEWER,
            details={
                "manuscript_id": str(assignment.manuscript_id),
                "assignment_id": str(assignment.pk),
                "report_type": report_type,
            },
            **context,
        )
        transaction.on_commit(
            lambda: announce(
                incident_reported,
                incident_id=incident.pk,
                assignment_id=assignment.pk,
                manuscript_id=assignment.manuscript_id,
                report_type=report_type,
            )
        )
        return incident

    return run_audited(work)


def _open_anonymization_round(
    manuscript: Manuscript, editor: User
) -> CorrectionRound:
    """Move the manuscript to ``REQUIRES_CORRECTIONS`` and open the next round."""
    manuscript.current_round += 1
    opened = CorrectionRound.objects.create(
        manuscript=manuscript,
        round_number=manuscript.current_round,
        opened_by_verdict=None,
    )
    manuscript.status = Manuscript.Status.REQUIRES_CORRECTIONS
    manuscript.lock_version += 1
    manuscript.save(update_fields=("status", "current_round", "lock_version", "updated_at"))
    StatusEvent.objects.create(
        manuscript=manuscript,
        from_status=Manuscript.Status.UNDER_REVIEW,
        to_status=Manuscript.Status.REQUIRES_CORRECTIONS,
        actor=editor,
        reason=ANONYMIZED_REQUEST_REASON,
        metadata={
            "round_number": opened.round_number,
            "cause": IncidentReport.Resolution.REQUEST_ANONYMIZED_VERSION,
        },
    )
    return opened


def resolve_incident(
    *, incident_id: UUID, editor: User, resolution: str, context: dict
) -> IncidentReport:
    """Resolve an open report once; a second attempt answers ``409``."""

    def work() -> IncidentReport:
        try:
            manuscript_id = (
                IncidentReport.objects.for_editor(editor)
                .values_list("manuscript_id", flat=True)
                .get(pk=incident_id)
            )
        except IncidentReport.DoesNotExist as exc:
            raise DomainError(NOT_FOUND_MESSAGE, code=ErrorCode.NOT_FOUND) from exc
        manuscript = Manuscript.objects.select_for_update(of=("self",)).get(pk=manuscript_id)
        incident = (
            IncidentReport.objects.select_for_update(of=("self", "assignment"))
            .select_related("assignment")
            .get(pk=incident_id)
        )
        if incident.status != IncidentReport.Status.OPEN:
            raise DomainError(
                ALREADY_RESOLVED_MESSAGE,
                code=ErrorCode.STATE_CONFLICT,
                details={"status": incident.status},
            )

        opened_round = None
        revoked = False
        if resolution != IncidentReport.Resolution.DISMISS:
            if not manuscript.is_active or manuscript.status != Manuscript.Status.UNDER_REVIEW:
                raise DomainError(
                    NOT_UNDER_REVIEW_MESSAGE,
                    code=ErrorCode.STATE_CONFLICT,
                    details={"status": manuscript.status, "is_active": manuscript.is_active},
                )
            revoked = revoke_for_incident(incident.assignment, editor=editor, context=context)
            if resolution == IncidentReport.Resolution.REQUEST_ANONYMIZED_VERSION:
                opened_round = _open_anonymization_round(manuscript, editor)

        incident.status = IncidentReport.Status.RESOLVED
        incident.resolution = resolution
        incident.resolved_by = editor
        incident.resolved_at = Now()
        incident.correction_round = opened_round
        incident.save(
            update_fields=("status", "resolution", "resolved_by", "resolved_at", "correction_round")
        )
        record_editor_audit(
            "INCIDENT_RESOLVED",
            "INCIDENT_REPORT",
            incident.pk,
            editor,
            context,
            details={
                "manuscript_id": str(manuscript.pk),
                "assignment_id": str(incident.assignment_id),
                "resolution": resolution,
                "assignment_revoked": revoked,
                "correction_round_id": str(opened_round.pk) if opened_round else None,
                "round_number": opened_round.round_number if opened_round else None,
            },
        )
        transaction.on_commit(
            lambda: announce(
                incident_resolved,
                incident_id=incident.pk,
                assignment_id=incident.assignment_id,
                manuscript_id=manuscript.pk,
                resolution=resolution,
                correction_round_id=opened_round.pk if opened_round else None,
            )
        )
        incident.refresh_from_db()
        return incident

    return run_audited(work)
