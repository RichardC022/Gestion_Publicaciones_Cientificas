"""Editor actions over reviews: start the review, assign and revoke (TSK-47).

Every action runs in ONE transaction that also records the audit: if the
audit trail is unavailable nothing is kept and the answer is ``503``.
The manuscript row is locked first, so two editors acting at once see
each other's result instead of racing; the partial unique index of
``reviews_assignment`` stays as the last barrier.

The deadline is fixed by PostgreSQL (``now() + 20 days``) and never by
the client clock. Area, availability and capacity rules, notices and
the reaction to a withdrawal belong to TSK-48.
"""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID

from django.db import IntegrityError, transaction
from django.db.models import TextChoices
from django.db.models.functions import Now

from apps.audit.models import AuditLog
from apps.audit.services import AuditService, AuditUnavailable
from apps.publications.models import Manuscript, StatusEvent
from apps.reviews.models import ASSIGNMENT_DAYS, Assignment
from apps.reviews.services.eligibility import has_conflict
from apps.users.models import Role, User
from apps.users.services.auth import AUDIT_UNAVAILABLE_MESSAGE
from config.exceptions import DomainError, ErrorCode

NOT_ACTIVE_MESSAGE = "El manuscrito fue dado de baja."
NOT_SUBMITTED_MESSAGE = "Solo un manuscrito enviado puede pasar a revisión."
NOT_UNDER_REVIEW_MESSAGE = (
    "El manuscrito debe estar en revisión para asignar un Revisor."
)
ACTIVE_ASSIGNMENT_MESSAGE = "El manuscrito ya tiene un Revisor activo."
EXPIRED_ASSIGNMENT_MESSAGE = (
    "La asignación vencida debe revocarse antes de asignar a otro Revisor."
)
NOT_REVOCABLE_MESSAGE = "Solo una asignación activa o vencida puede revocarse."
EARLY_CAUSE_MESSAGE = (
    "Una asignación vigente solo se revoca por conflicto de interés, "
    "error de asignación o cuenta inhabilitada."
)
OVERDUE_CAUSE_MESSAGE = "La causa 'plazo vencido' exige que la asignación haya vencido."
INVALID_REVIEWER_MESSAGE = "El Revisor indicado no está disponible para esta asignación."
REVIEWER_CONFLICT_MESSAGE = "El Revisor figura como autor del manuscrito."


class RevocationCause(TextChoices):
    """Why an editor revokes an assignment."""

    CONFLICT_OF_INTEREST = "CONFLICT_OF_INTEREST", "Conflicto de interés"
    ASSIGNMENT_ERROR = "ASSIGNMENT_ERROR", "Error de asignación"
    ACCOUNT_DISABLED = "ACCOUNT_DISABLED", "Cuenta inhabilitada"
    OVERDUE = "OVERDUE", "Plazo vencido"


#: Causes allowed while the assignment is still within its deadline.
EARLY_CAUSES = (
    RevocationCause.CONFLICT_OF_INTEREST,
    RevocationCause.ASSIGNMENT_ERROR,
    RevocationCause.ACCOUNT_DISABLED,
)


def record_editor_audit(
    action: str,
    entity_type: str,
    entity_id: UUID,
    editor: User,
    context: dict,
    **extra,
) -> None:
    """Append an audit event of an editor action to the current transaction."""
    AuditService.record(
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        result=AuditLog.Result.SUCCESS,
        actor=editor,
        actor_role=Role.Code.EDITOR,
        **extra,
        **context,
    )


def _validation_error(field: str, message: str) -> DomainError:
    return DomainError(
        message, code=ErrorCode.VALIDATION_ERROR, details={field: [message]}
    )


def _lock_manuscript(manuscript_id: UUID) -> Manuscript:
    manuscript = Manuscript.objects.select_for_update().get(pk=manuscript_id)
    if not manuscript.is_active:
        raise DomainError(
            NOT_ACTIVE_MESSAGE,
            code=ErrorCode.STATE_CONFLICT,
            details={"status": manuscript.status, "is_active": False},
        )
    return manuscript


def _ensure_no_open_assignment(manuscript: Manuscript) -> None:
    """One reviewer at a time; an expired one is revoked first, never replaced."""
    open_statuses = manuscript.assignments.filter(
        status__in=(Assignment.Status.ACTIVE, Assignment.Status.EXPIRED)
    ).values_list("status", flat=True)
    if Assignment.Status.ACTIVE in open_statuses:
        raise DomainError(ACTIVE_ASSIGNMENT_MESSAGE, code=ErrorCode.ASSIGNMENT_CONFLICT)
    if Assignment.Status.EXPIRED in open_statuses:
        raise DomainError(EXPIRED_ASSIGNMENT_MESSAGE, code=ErrorCode.ASSIGNMENT_CONFLICT)


def _reviewer_for_assignment(manuscript: Manuscript, reviewer_id: UUID) -> User:
    reviewer = User.objects.filter(
        pk=reviewer_id,
        is_active=True,
        role_assignments__is_active=True,
        role_assignments__role__code=Role.Code.REVIEWER,
    ).first()
    if reviewer is None:
        raise _validation_error("reviewer_id", INVALID_REVIEWER_MESSAGE)
    if has_conflict(manuscript, reviewer):
        raise _validation_error("reviewer_id", REVIEWER_CONFLICT_MESSAGE)
    return reviewer


def _create_assignment(
    manuscript: Manuscript, reviewer_id: UUID, editor: User, context: dict
) -> Assignment:
    """Insert the assignment inside the caller's transaction."""
    _ensure_no_open_assignment(manuscript)
    reviewer = _reviewer_for_assignment(manuscript, reviewer_id)
    version = manuscript.versions.get(version_number=manuscript.current_version)
    try:
        with transaction.atomic():
            assignment = Assignment.objects.create(
                manuscript=manuscript,
                version=version,
                reviewer=reviewer,
                assigned_by=editor,
                # `Now()` es el instante de la transacción: ambos campos
                # coinciden con la restricción `due_at = assigned_at + 20 días`.
                assigned_at=Now(),
                due_at=Now() + timedelta(days=ASSIGNMENT_DAYS),
            )
    except IntegrityError as exc:
        raise DomainError(ACTIVE_ASSIGNMENT_MESSAGE, code=ErrorCode.ASSIGNMENT_CONFLICT) from exc
    assignment.refresh_from_db()
    record_editor_audit(
        "ASSIGNMENT_CREATED",
        "ASSIGNMENT",
        assignment.pk,
        editor,
        context,
        details={
            "manuscript_id": str(manuscript.pk),
            "code": manuscript.code,
            "reviewer_id": str(reviewer.pk),
            "version_number": version.version_number,
            "due_at": assignment.due_at.isoformat(),
        },
    )
    return assignment


def _audited(work):
    """Run ``work`` atomically; a missing audit trail aborts it with ``503``."""
    try:
        with transaction.atomic():
            return work()
    except AuditUnavailable as exc:
        raise DomainError(AUDIT_UNAVAILABLE_MESSAGE, code=ErrorCode.AUDIT_UNAVAILABLE) from exc


def start_review(
    *, manuscript_id: UUID, editor: User, reviewer_id: UUID | None, context: dict
) -> tuple[Manuscript, Assignment | None]:
    """Move ``SUBMITTED`` to ``UNDER_REVIEW``, optionally assigning a reviewer.

    Both changes commit together or not at all.
    """

    def work() -> tuple[Manuscript, Assignment | None]:
        manuscript = _lock_manuscript(manuscript_id)
        if manuscript.status != Manuscript.Status.SUBMITTED:
            raise DomainError(
                NOT_SUBMITTED_MESSAGE,
                code=ErrorCode.STATE_CONFLICT,
                details={"status": manuscript.status},
            )
        manuscript.status = Manuscript.Status.UNDER_REVIEW
        manuscript.lock_version += 1
        manuscript.save(update_fields=("status", "lock_version", "updated_at"))
        StatusEvent.objects.create(
            manuscript=manuscript,
            from_status=Manuscript.Status.SUBMITTED,
            to_status=Manuscript.Status.UNDER_REVIEW,
            actor=editor,
            metadata={"round_number": manuscript.current_round},
        )
        record_editor_audit(
            "REVIEW_STARTED",
            "MANUSCRIPT",
            manuscript.pk,
            editor,
            context,
            details={"code": manuscript.code, "reviewer_assigned": reviewer_id is not None},
        )
        assignment = None
        if reviewer_id is not None:
            assignment = _create_assignment(manuscript, reviewer_id, editor, context)
        return manuscript, assignment

    return _audited(work)


def assign_reviewer(
    *, manuscript_id: UUID, editor: User, reviewer_id: UUID, context: dict
) -> Assignment:
    """Create the single active assignment of a manuscript under review."""

    def work() -> Assignment:
        manuscript = _lock_manuscript(manuscript_id)
        if manuscript.status != Manuscript.Status.UNDER_REVIEW:
            raise DomainError(
                NOT_UNDER_REVIEW_MESSAGE,
                code=ErrorCode.STATE_CONFLICT,
                details={"status": manuscript.status},
            )
        return _create_assignment(manuscript, reviewer_id, editor, context)

    return _audited(work)


def revoke_assignment(
    *, assignment_id: UUID, editor: User, cause: str, reason: str, context: dict
) -> Assignment:
    """Revoke an active or expired assignment; the reason is mandatory.

    While the deadline has not passed only the early causes are valid.
    The manuscript stays ``UNDER_REVIEW``, pending a new assignment, and
    evaluations already written are left untouched.
    """

    def work() -> Assignment:
        assignment = Assignment.objects.select_for_update().get(pk=assignment_id)
        if assignment.status not in (Assignment.Status.ACTIVE, Assignment.Status.EXPIRED):
            raise DomainError(
                NOT_REVOCABLE_MESSAGE,
                code=ErrorCode.STATE_CONFLICT,
                details={"status": assignment.status},
            )
        overdue = assignment.status == Assignment.Status.EXPIRED or Assignment.objects.filter(
            pk=assignment.pk, due_at__lte=Now()
        ).exists()
        if not overdue and cause not in EARLY_CAUSES:
            raise _validation_error(
                "cause",
                OVERDUE_CAUSE_MESSAGE
                if cause == RevocationCause.OVERDUE
                else EARLY_CAUSE_MESSAGE,
            )
        previous_status = assignment.status
        assignment.status = Assignment.Status.REVOKED
        assignment.revoked_by = editor
        assignment.revocation_reason = reason
        assignment.lock_version += 1
        assignment.revoked_at = Now()
        assignment.save(
            update_fields=(
                "status",
                "revoked_by",
                "revoked_at",
                "revocation_reason",
                "lock_version",
                "updated_at",
            )
        )
        assignment.refresh_from_db()
        record_editor_audit(
            "ASSIGNMENT_REVOKED",
            "ASSIGNMENT",
            assignment.pk,
            editor,
            context,
            reason=reason,
            details={
                "manuscript_id": str(assignment.manuscript_id),
                "cause": cause,
                "previous_status": previous_status,
            },
        )
        return assignment

    return _audited(work)
