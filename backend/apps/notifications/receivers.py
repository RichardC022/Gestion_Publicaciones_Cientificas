"""Receivers of the eleven domain signals (TSK-75, closes D-10b).

Each receiver gets identifiers only, reads what it needs from the
database and writes notices whose payload comes from
:func:`~apps.notifications.payloads.build_payload`: the event, the public
code and title of the manuscript, the action expected, the deadline and a
SPA link. That is what keeps the double blind (plan section 2.9):

* the notices for a reviewer never include an author, and the ones for an
  author never include a reviewer, because no receiver puts a person in a
  payload at all;
* the free text of a revocation, an incident or a verdict (justification,
  observations, comments) is never read here;
* the notice for the author of an incident resolved with
  ``REQUEST_ANONYMIZED_VERSION`` talks about the manuscript, never about
  the report or whoever filed it.

All of them run after the business transaction committed and are sent
with ``send_robust``: a failure here is logged and never undoes the action.
"""

from __future__ import annotations

from django.dispatch import receiver

from apps.notifications.services import (
    assigning_editor,
    authors_of,
    editors_for,
    notify_each,
    reviewer_of,
)
from apps.publications.models import Manuscript, Verdict
from apps.publications.signals import (
    manuscript_submitted,
    manuscript_withdrawn,
    new_version_submitted,
    verdict_correction_authorized,
    verdict_registered,
)
from apps.reviews.models import Assignment, IncidentReport
from apps.reviews.services.assignments import RevocationCause
from apps.reviews.signals import (
    assignment_created,
    assignment_expired,
    assignment_revoked,
    evaluation_submitted,
    incident_reported,
    incident_resolved,
    reviewer_conflict_declared,
)
from apps.users.models import Role

AUTHOR, EDITOR, REVIEWER = Role.Code.AUTHOR, Role.Code.EDITOR, Role.Code.REVIEWER


def _manuscript(manuscript_id) -> Manuscript:
    return Manuscript.objects.get(pk=manuscript_id)


def _assignment(assignment_id) -> Assignment:
    return Assignment.objects.select_related("manuscript", "reviewer", "assigned_by").get(
        pk=assignment_id
    )


def _author_link(manuscript: Manuscript) -> str:
    return f"/app/author/manuscripts/{manuscript.pk}"


def _editor_link(manuscript: Manuscript) -> str:
    return f"/app/editor/submissions/{manuscript.pk}"


def _reviewer_link(assignment: Assignment) -> str:
    return f"/app/reviewer/assignments/{assignment.pk}"


@receiver(manuscript_submitted, dispatch_uid="notifications-manuscript-submitted")
def on_manuscript_submitted(sender, manuscript_id, version_id, **kwargs) -> None:
    manuscript = _manuscript(manuscript_id)
    notify_each(
        authors_of(manuscript),
        event_type="MANUSCRIPT_SUBMITTED",
        subject_id=version_id,
        role=AUTHOR,
        manuscript=manuscript,
        title="Manuscrito enviado",
        message="Su manuscrito fue enviado y quedó en la bandeja del Editor.",
        action=None,
        link=_author_link(manuscript),
    )
    notify_each(
        editors_for(manuscript),
        event_type="SUBMISSION_RECEIVED",
        subject_id=version_id,
        role=EDITOR,
        manuscript=manuscript,
        title="Nuevo manuscrito recibido",
        message="Hay un manuscrito nuevo pendiente de revisión editorial.",
        action="Inicie la revisión y asigne un Revisor.",
        link=_editor_link(manuscript),
    )


@receiver(new_version_submitted, dispatch_uid="notifications-new-version-submitted")
def on_new_version_submitted(sender, manuscript_id, version_id, **kwargs) -> None:
    manuscript = _manuscript(manuscript_id)
    notify_each(
        authors_of(manuscript),
        event_type="NEW_VERSION_SUBMITTED",
        subject_id=version_id,
        role=AUTHOR,
        manuscript=manuscript,
        title="Nueva versión enviada",
        message="Su nueva versión fue recibida y vuelve a la revisión editorial.",
        link=_author_link(manuscript),
    )
    notify_each(
        editors_for(manuscript),
        event_type="NEW_VERSION_RECEIVED",
        subject_id=version_id,
        role=EDITOR,
        manuscript=manuscript,
        title="Nueva versión recibida",
        message="El Autor respondió a las correcciones con una nueva versión.",
        action="Revise la nueva versión.",
        link=_editor_link(manuscript),
    )


@receiver(verdict_registered, dispatch_uid="notifications-verdict-registered")
def on_verdict_registered(sender, manuscript_id, verdict_id, decision, **kwargs) -> None:
    manuscript = _manuscript(manuscript_id)
    messages = {
        Verdict.Decision.ACCEPTED: (
            "Manuscrito aceptado",
            "Su manuscrito fue aceptado y se publicará en el catálogo.",
            None,
        ),
        Verdict.Decision.REJECTED: (
            "Manuscrito rechazado",
            "El Editor registró su decisión sobre el manuscrito.",
            None,
        ),
        Verdict.Decision.REQUIRES_CORRECTIONS: (
            "Se solicitan correcciones",
            "El Editor solicitó correcciones a su manuscrito.",
            "Revise las observaciones y envíe una nueva versión.",
        ),
    }
    title, message, action = messages[decision]
    notify_each(
        authors_of(manuscript),
        event_type="VERDICT_REGISTERED",
        subject_id=verdict_id,
        role=AUTHOR,
        manuscript=manuscript,
        title=title,
        message=message,
        action=action,
        link=_author_link(manuscript),
    )


@receiver(manuscript_withdrawn, dispatch_uid="notifications-manuscript-withdrawn")
def on_manuscript_withdrawn(
    sender, manuscript_id, withdrawn_by_id, previous_status, **kwargs
) -> None:
    manuscript = _manuscript(manuscript_id)
    if previous_status != Manuscript.Status.DRAFT:
        notify_each(
            editors_for(manuscript),
            event_type="MANUSCRIPT_WITHDRAWN",
            subject_id=manuscript.pk,
            role=EDITOR,
            manuscript=manuscript,
            title="Manuscrito dado de baja",
            message="El Autor dio de baja el manuscrito.",
            link=_editor_link(manuscript),
        )
    notify_each(
        authors_of(manuscript, exclude_ids=[withdrawn_by_id]),
        event_type="MANUSCRIPT_WITHDRAWN",
        subject_id=manuscript.pk,
        role=AUTHOR,
        manuscript=manuscript,
        title="Manuscrito dado de baja",
        message="El manuscrito fue dado de baja.",
        link=_author_link(manuscript),
    )


@receiver(assignment_created, dispatch_uid="notifications-assignment-created")
def on_assignment_created(sender, assignment_id, **kwargs) -> None:
    assignment = _assignment(assignment_id)
    notify_each(
        reviewer_of(assignment),
        event_type="ASSIGNMENT_CREATED",
        subject_id=assignment.pk,
        role=REVIEWER,
        manuscript=assignment.manuscript,
        title="Nueva asignación de revisión",
        message="Se le asignó un manuscrito para evaluar.",
        action="Evalúe el manuscrito antes de la fecha límite.",
        due_at=assignment.due_at,
        link=_reviewer_link(assignment),
    )


@receiver(assignment_revoked, dispatch_uid="notifications-assignment-revoked")
def on_assignment_revoked(sender, assignment_id, cause, **kwargs) -> None:
    assignment = _assignment(assignment_id)
    withdrawn = cause == RevocationCause.MANUSCRIPT_WITHDRAWN
    notify_each(
        reviewer_of(assignment),
        event_type="ASSIGNMENT_REVOKED",
        subject_id=assignment.pk,
        role=REVIEWER,
        manuscript=assignment.manuscript,
        title="Asignación revocada",
        message=(
            "El manuscrito fue dado de baja y su asignación se canceló."
            if withdrawn
            else "Su asignación de revisión fue revocada."
        ),
        link="/app/reviewer/assignments",
    )


@receiver(assignment_expired, dispatch_uid="notifications-assignment-expired")
def on_assignment_expired(sender, assignment_id, **kwargs) -> None:
    assignment = _assignment(assignment_id)
    notify_each(
        assigning_editor(assignment),
        event_type="ASSIGNMENT_EXPIRED",
        subject_id=assignment.pk,
        role=EDITOR,
        manuscript=assignment.manuscript,
        title="Plazo de revisión vencido",
        message="El plazo de la asignación venció sin evaluación final.",
        action="Revoque o reasigne la revisión.",
        due_at=assignment.due_at,
        link="/app/editor/assignments/expired",
    )


@receiver(evaluation_submitted, dispatch_uid="notifications-evaluation-submitted")
def on_evaluation_submitted(sender, evaluation_id, assignment_id, **kwargs) -> None:
    assignment = _assignment(assignment_id)
    notify_each(
        assigning_editor(assignment),
        event_type="EVALUATION_SUBMITTED",
        subject_id=evaluation_id,
        role=EDITOR,
        manuscript=assignment.manuscript,
        title="Evaluación recibida",
        message="El Revisor envió su evaluación final.",
        action="Revise la evaluación y registre el veredicto.",
        link=_editor_link(assignment.manuscript),
    )


@receiver(reviewer_conflict_declared, dispatch_uid="notifications-conflict-declared")
def on_conflict_declared(sender, assignment_id, **kwargs) -> None:
    assignment = _assignment(assignment_id)
    notify_each(
        assigning_editor(assignment),
        event_type="CONFLICT_DECLARED",
        subject_id=assignment.pk,
        role=EDITOR,
        manuscript=assignment.manuscript,
        title="Conflicto de interés declarado",
        message="El Revisor declaró un conflicto de interés y su evaluación quedó bloqueada.",
        action="Revoque la asignación o reasigne la revisión.",
        link=_editor_link(assignment.manuscript),
    )


@receiver(incident_reported, dispatch_uid="notifications-incident-reported")
def on_incident_reported(sender, incident_id, assignment_id, **kwargs) -> None:
    assignment = _assignment(assignment_id)
    notify_each(
        assigning_editor(assignment),
        event_type="INCIDENT_REPORTED",
        subject_id=incident_id,
        role=EDITOR,
        manuscript=assignment.manuscript,
        title="Reporte confidencial recibido",
        message="Se registró un reporte confidencial sobre el manuscrito.",
        action="Revise y resuelva el reporte.",
        link="/app/editor/incidents",
    )


@receiver(incident_resolved, dispatch_uid="notifications-incident-resolved")
def on_incident_resolved(sender, incident_id, manuscript_id, resolution, **kwargs) -> None:
    # Solo se avisa al Autor cuando se le pide una versión anonimizada; el aviso
    # habla del manuscrito, nunca del reporte ni de quien lo presentó.
    if resolution != IncidentReport.Resolution.REQUEST_ANONYMIZED_VERSION:
        return
    manuscript = _manuscript(manuscript_id)
    notify_each(
        authors_of(manuscript),
        event_type="ANONYMIZED_VERSION_REQUESTED",
        subject_id=incident_id,
        role=AUTHOR,
        manuscript=manuscript,
        title="Se solicita una versión anonimizada",
        message="El Editor solicita una versión anonimizada del manuscrito.",
        action="Envíe una nueva versión sin datos que identifiquen a los autores.",
        link=_author_link(manuscript),
    )


@receiver(verdict_correction_authorized, dispatch_uid="notifications-correction-authorized")
def on_correction_authorized(sender, manuscript_id, verdict_id, correction_id, **kwargs) -> None:
    # Se avisa al Editor que emitió el veredicto, o a los elegibles si ya no puede actuar.
    manuscript = _manuscript(manuscript_id)
    eligible = editors_for(manuscript)
    issuer = Verdict.objects.get(pk=verdict_id).editor_id
    recipients = [user for user in eligible if user.pk == issuer] or eligible
    notify_each(
        recipients,
        event_type="VERDICT_CORRECTION_AUTHORIZED",
        subject_id=correction_id,
        role=EDITOR,
        manuscript=manuscript,
        title="Corrección de veredicto habilitada",
        message="Un Administrador habilitó una nueva decisión sobre el veredicto registrado.",
        action="Registre la nueva decisión.",
        link=_editor_link(manuscript),
    )
