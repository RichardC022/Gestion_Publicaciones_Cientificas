"""Who can review a manuscript: eligible reviewers and conflicts of interest.

A reviewer is eligible when the account and the ``REVIEWER`` role are
active, the profile marks them as available and, if asked, they declare
the manuscript's area. Whoever registered the manuscript or figures as
author or coauthor — by account or by e-mail — has a conflict of
interest and is never eligible (plan section 2.4, assignment rules).
"""

from __future__ import annotations

from django.db.models import Count, Q, QuerySet
from django.db.models.functions import Lower

from apps.publications.models import Manuscript
from apps.reviews.models import Assignment
from apps.users.models import Role, User


def author_emails(manuscript: Manuscript) -> list[str]:
    """Lower-cased e-mails of the manuscript's authors."""
    return [email.lower() for email in manuscript.authors.values_list("email", flat=True)]


def has_conflict(manuscript: Manuscript, user: User) -> bool:
    """The user registered the manuscript or is one of its authors."""
    if user.pk == manuscript.created_by_id:
        return True
    return manuscript.authors.filter(Q(user=user) | Q(email__iexact=user.email)).exists()


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
