"""Who can review a manuscript: eligible reviewers and conflicts of interest.

A reviewer is eligible when the account and the ``REVIEWER`` role are
active, the profile marks them as available and, if asked, they declare
the manuscript's area. Whoever registered the manuscript or figures as
author or coauthor — by account or by e-mail — has a conflict of
interest and is never eligible (plan section 2.4, assignment rules).
"""

from __future__ import annotations

from enum import StrEnum

from django.db.models import Count, Q, QuerySet
from django.db.models.functions import Lower

from apps.publications.models import Manuscript
from apps.reviews.models import Assignment
from apps.users.models import ReviewerProfile, Role, User


def author_emails(manuscript: Manuscript) -> list[str]:
    """Lower-cased e-mails of the manuscript's authors."""
    return [email.lower() for email in manuscript.authors.values_list("email", flat=True)]


def has_conflict(manuscript: Manuscript, user: User) -> bool:
    """The user registered the manuscript or is one of its authors."""
    if user.pk == manuscript.created_by_id:
        return True
    return manuscript.authors.filter(Q(user=user) | Q(email__iexact=user.email)).exists()


class Ineligibility(StrEnum):
    """Why an active reviewer account cannot take a manuscript."""

    CONFLICT = "conflict"
    NO_PROFILE = "no_profile"
    UNAVAILABLE = "unavailable"
    OTHER_AREA = "other_area"


INVALID_REVIEWER_MESSAGE = "El Revisor indicado no está disponible para esta asignación."
REVIEWER_CONFLICT_MESSAGE = "El Revisor figura como autor del manuscrito."
REVIEWER_UNAVAILABLE_MESSAGE = "El Revisor marcó que no está disponible."
REVIEWER_AREA_MESSAGE = "El Revisor no declara el área del manuscrito."

MESSAGES = {
    Ineligibility.CONFLICT: REVIEWER_CONFLICT_MESSAGE,
    Ineligibility.NO_PROFILE: INVALID_REVIEWER_MESSAGE,
    Ineligibility.UNAVAILABLE: REVIEWER_UNAVAILABLE_MESSAGE,
    Ineligibility.OTHER_AREA: REVIEWER_AREA_MESSAGE,
}


def diagnose(
    manuscript: Manuscript | None, reviewer: User, *, area: str | None
) -> Ineligibility | None:
    """The first rule the reviewer account breaks; ``None`` if it can review.

    Applies, in order, the same rules as :func:`eligible_reviewers`.
    Without a ``manuscript`` no conflict of interest can be evaluated, and
    without an ``area`` any expertise is accepted. Capacity is not checked
    here: it needs the reviewer's profile row locked and is the service's job.
    """
    if manuscript is not None and has_conflict(manuscript, reviewer):
        return Ineligibility.CONFLICT
    try:
        profile: ReviewerProfile = reviewer.reviewer_profile
    except ReviewerProfile.DoesNotExist:
        return Ineligibility.NO_PROFILE
    if not profile.is_available:
        return Ineligibility.UNAVAILABLE
    if area and area not in profile.expertise_areas:
        return Ineligibility.OTHER_AREA
    return None


def _reviewer_accounts() -> QuerySet:
    """Active accounts with the active ``REVIEWER`` role, profile included."""
    return User.objects.filter(
        is_active=True,
        role_assignments__is_active=True,
        role_assignments__role__code=Role.Code.REVIEWER,
    ).select_related("reviewer_profile")


def ineligibility_reason(manuscript: Manuscript, reviewer_id) -> str | None:
    """Why the account cannot review the manuscript; ``None`` if it can."""
    reviewer = _reviewer_accounts().filter(pk=reviewer_id).first()
    if reviewer is None:
        return INVALID_REVIEWER_MESSAGE
    reason = diagnose(manuscript, reviewer, area=manuscript.area)
    return MESSAGES[reason] if reason else None


def eligibility_breakdown(*, manuscript: Manuscript | None, area: str | None) -> dict[str, int]:
    """How many reviewer accounts exist and what rules exclude them.

    The causes are exclusive and checked in the order of :func:`diagnose`,
    so ``reviewers`` equals the eligible ones plus the sum of the causes.
    It explains an empty list of candidates to the editor.
    """
    counts = {reason.value: 0 for reason in Ineligibility}
    total = 0
    for reviewer in _reviewer_accounts():
        total += 1
        reason = diagnose(manuscript, reviewer, area=area)
        if reason:
            counts[reason.value] += 1
    return {"reviewers": total, **counts}


def eligible_reviewers(*, manuscript: Manuscript | None = None, area: str | None = None) -> QuerySet:
    """Available reviewers, with their current load, free of conflicts.

    ``area`` must match one of the declared expertise areas exactly.
    Without a ``manuscript`` no conflict can be evaluated, so the caller
    must treat the list as a candidate pool only.
    """
    reviewers = (
        User.objects.filter(
            is_active=True,
            role_assignments__is_active=True,
            role_assignments__role__code=Role.Code.REVIEWER,
            reviewer_profile__is_available=True,
        )
        .select_related("reviewer_profile")
        .annotate(
            active_assignments=Count(
                "review_assignments",
                filter=Q(review_assignments__status=Assignment.Status.ACTIVE),
                distinct=True,
            )
        )
    )
    if area:
        reviewers = reviewers.filter(reviewer_profile__expertise_areas__contains=[area])
    if manuscript is not None:
        reviewers = (
            reviewers.exclude(pk=manuscript.created_by_id)
            .exclude(authorships__manuscript=manuscript)
            .annotate(email_lower=Lower("email"))
            .exclude(email_lower__in=author_emails(manuscript))
        )
    return reviewers.order_by("last_name", "first_name", "id")
