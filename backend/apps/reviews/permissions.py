"""Object permissions of the reviews domain (plan sections 2.9 and 6.2)."""

from __future__ import annotations

from apps.users.permissions import BaseObjectPermission

#: Assignment statuses per the plan (section 1.13).
ACTIVE = "ACTIVE"
COMPLETED = "COMPLETED"


def resolve_assignment(obj):
    """Find the reviewer assignment behind ``obj``: itself or a related object.

    The permission works against the model contract of the plan
    (section 1.13): an assignment carries ``reviewer_id`` and
    ``status``; related objects such as evaluations reach it through
    their ``assignment`` relation.
    """
    current = obj
    for _ in range(5):
        if current is None:
            return None
        if hasattr(current, "reviewer_id"):
            return current
        current = getattr(current, "assignment", None)
    return None


class IsAssignedReviewer(BaseObjectPermission):
    """The actor is the reviewer assigned to the object being accessed.

    Follows the plan (section 2.9): the actor needs an assignment of
    their own in status ``ACTIVE`` or ``COMPLETED``. A foreign
    assignment answers ``404``, never ``403``.
    """

    require_active = False
    allowed_statuses = (ACTIVE, COMPLETED)

    def check_object(self, request, view, obj) -> bool:
        assignment = resolve_assignment(obj)
        if assignment is None:
            return False
        if assignment.reviewer_id != request.user.id:
            return False
        if self.require_active:
            return assignment.status == ACTIVE
        return assignment.status in self.allowed_statuses


class IsActiveAssignedReviewer(IsAssignedReviewer):
    """PDF downloads: only an ``ACTIVE`` assignment grants the document.

    Stricter variant used by the reviewer document endpoint (plan
    section 4.6); a ``COMPLETED`` assignment no longer downloads.
    """

    require_active = True
