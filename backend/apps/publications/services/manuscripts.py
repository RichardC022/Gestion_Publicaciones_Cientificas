"""Creation and edition of manuscripts (plan sections 2.3 and 2.11).

Both operations write the manuscript, its authors, the status history
and the audit event in ONE transaction: if the audit trail cannot be
written everything rolls back and the caller answers ``503`` (plan
section 6.5). Edition takes a row lock and compares ``lock_version``
with the ``If-Match`` the client sent, so a stale edit answers ``409``
and the winning edit is kept.

The audit details carry field NAMES only, never manuscript content.
"""

from __future__ import annotations

from typing import Any

from django.db import transaction
from django.db.models.functions import Lower

from apps.audit.models import AuditLog
from apps.audit.services import AuditService, AuditUnavailable
from apps.publications.models import Manuscript, ManuscriptAuthor, StatusEvent
from apps.users.models import Role, User
from apps.users.services.auth import AUDIT_UNAVAILABLE_MESSAGE
from config.exceptions import DomainError, ErrorCode

#: Statuses in which the author may still edit the metadata.
EDITABLE_STATUSES = (
    Manuscript.Status.DRAFT,
    Manuscript.Status.REQUIRES_CORRECTIONS,
)

#: Metadata edited with ``PATCH``; the authors are compared separately.
METADATA_FIELDS = ("title", "abstract", "keywords", "area", "language")

#: A draft may be saved partially (CA-HU-04-01): missing metadata is empty.
DRAFT_DEFAULTS: dict[str, Any] = {
    "title": "",
    "abstract": "",
    "keywords": [],
    "area": "",
    "language": "",
}


def ensure_editable(manuscript: Manuscript) -> None:
    """Reject the edition outside ``DRAFT``/``REQUIRES_CORRECTIONS`` or after a withdrawal."""
    if not manuscript.is_active or manuscript.status not in EDITABLE_STATUSES:
        raise DomainError(
            "El manuscrito no admite edición en su estado actual.",
            code=ErrorCode.STATE_CONFLICT,
            details={"status": manuscript.status, "is_active": manuscript.is_active},
        )


def _accounts_by_email(emails: list[str]) -> dict[str, User]:
    """Institutional accounts that match the authors' emails (case-insensitive).

    The link is what makes the conflict-of-interest rules work: a
    coauthor with an account can never review or edit the manuscript.
    """
    lowered = [email.lower() for email in emails]
    accounts = User.objects.annotate(email_lower=Lower("email")).filter(
        email_lower__in=lowered
    )
    return {account.email.lower(): account for account in accounts}


def _author_rows(manuscript: Manuscript, authors: list[dict[str, Any]]) -> list[ManuscriptAuthor]:
    """Authors in list order; ``author_order`` is the 1-based position."""
    accounts = _accounts_by_email([author["email"] for author in authors])
    return [
        ManuscriptAuthor(
            manuscript=manuscript,
            user=accounts.get(author["email"].lower()),
            full_name=author["full_name"],
            email=author["email"],
            affiliation=author["affiliation"],
            is_corresponding=author.get("is_corresponding", False),
            author_order=position,
        )
        for position, author in enumerate(authors, start=1)
    ]


def _authors_signature(authors: list[dict[str, Any]]) -> list[tuple]:
    return [
        (
            author["full_name"],
            author["email"],
            author["affiliation"],
            author.get("is_corresponding", False),
        )
        for author in authors
    ]


def _audit(action: str, manuscript: Manuscript, user: User, context: dict, details: dict) -> None:
    AuditService.record(
        action=action,
        entity_type="MANUSCRIPT",
        entity_id=manuscript.pk,
        result=AuditLog.Result.SUCCESS,
        actor=user,
        actor_role=Role.Code.AUTHOR,
        details=details,
        **context,
    )


def create_manuscript(*, user: User, data: dict[str, Any], context: dict) -> Manuscript:
    """Create a ``DRAFT`` with its authors; it creates no version and no round."""
    data = {**DRAFT_DEFAULTS, **data}
    authors = data.pop("authors")
    try:
        with transaction.atomic():
            manuscript = Manuscript.objects.create(created_by=user, **data)
            ManuscriptAuthor.objects.bulk_create(_author_rows(manuscript, authors))
            StatusEvent.objects.create(
                manuscript=manuscript,
                to_status=Manuscript.Status.DRAFT,
                actor=user,
            )
            _audit(
                "MANUSCRIPT_CREATED",
                manuscript,
                user,
                context,
                {"code": manuscript.code, "authors": len(authors)},
            )
    except AuditUnavailable as exc:
        raise DomainError(AUDIT_UNAVAILABLE_MESSAGE, code=ErrorCode.AUDIT_UNAVAILABLE) from exc
    return manuscript


def update_manuscript(
    *,
    manuscript_id,
    user: User,
    expected_lock_version: int,
    data: dict[str, Any],
    context: dict,
) -> Manuscript:
    """Edit the metadata of an editable manuscript; it creates no version or round.

    Returns the manuscript untouched (same ``lock_version``) when the
    request changes nothing; otherwise bumps ``lock_version`` and audits
    the names of the modified fields.
    """
    data = dict(data)
    authors = data.pop("authors", None)
    try:
        with transaction.atomic():
            manuscript = Manuscript.objects.select_for_update().get(pk=manuscript_id)
            ensure_editable(manuscript)
            if manuscript.lock_version != expected_lock_version:
                raise DomainError(
                    "El manuscrito cambió desde que lo consultó; recargue e intente de nuevo.",
                    code=ErrorCode.VERSION_CONFLICT,
                    details={"lock_version": manuscript.lock_version},
                )

            changed = [
                field
                for field in METADATA_FIELDS
                if field in data and data[field] != getattr(manuscript, field)
            ]
            for field in changed:
                setattr(manuscript, field, data[field])

            if authors is not None:
                current = _authors_signature(
                    list(
                        manuscript.authors.values(
                            "full_name", "email", "affiliation", "is_corresponding"
                        )
                    )
                )
                if _authors_signature(authors) != current:
                    manuscript.authors.all().delete()
                    ManuscriptAuthor.objects.bulk_create(_author_rows(manuscript, authors))
                    changed.append("authors")

            if changed:
                manuscript.lock_version += 1
                manuscript.save()
                _audit(
                    "MANUSCRIPT_UPDATED",
                    manuscript,
                    user,
                    context,
                    {"fields": sorted(changed)},
                )
    except AuditUnavailable as exc:
        raise DomainError(AUDIT_UNAVAILABLE_MESSAGE, code=ErrorCode.AUDIT_UNAVAILABLE) from exc
    return manuscript
