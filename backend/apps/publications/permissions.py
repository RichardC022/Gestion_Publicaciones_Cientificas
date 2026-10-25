"""Object permissions of the publications domain (plan sections 2.9 and 6.2)."""

from __future__ import annotations

from apps.users.permissions import BaseObjectPermission


def resolve_manuscript(obj):
    """Find the manuscript behind ``obj``: itself or a related object.

    The permission works against the model contract of the plan
    (section 1.8): a manuscript carries ``created_by_id``; related
    objects such as versions reach it through their ``manuscript``
    relation.
    """
    current = obj
    for _ in range(5):
        if current is None:
            return None
        if hasattr(current, "created_by_id"):
            return current
        current = getattr(current, "manuscript", None)
    return None


class IsManuscriptOwner(BaseObjectPermission):
    """The actor registered the manuscript.

    Compares ``manuscript.created_by_id`` with the actor (plan section
    2.9). Someone else's manuscript answers ``404``, never ``403``, so
    the response does not reveal that it exists. Applied to a related
    object, the check walks its ``manuscript`` relation first.
    """

    def check_object(self, request, view, obj) -> bool:
        manuscript = resolve_manuscript(obj)
        if manuscript is None:
            return False
        return manuscript.created_by_id == request.user.id
