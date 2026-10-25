"""Role and object permissions for the institutional API (plan sections 2.9 and 6.2).

Authorization is layered, and every layer re-reads PostgreSQL:

* Module permissions — :class:`IsAuthor`, :class:`IsReviewer`,
  :class:`IsEditor`, :class:`IsAdmin` — answer ``403`` when the actor
  lacks an active role for the module. They read the active roles from
  ``users_user_role`` on EVERY request through the single
  :func:`~apps.users.services.auth.active_role_codes` helper: the
  ``roles`` claim of the access token is only a hint, so a role revoked
  mid-session blocks the next action even though the token is still
  valid.
* Object permissions — :class:`~apps.publications.permissions.IsManuscriptOwner`
  and :class:`~apps.reviews.permissions.IsAssignedReviewer` — extend
  :class:`BaseObjectPermission` and answer ``404`` (never ``403``) for an
  object outside the actor's scope, so the response never reveals that
  the object exists.
* :class:`IsPublicCatalog` opens the public catalog to anonymous,
  read-only access; limiting the results to accepted and active articles
  is the catalog QuerySet's invariant (plan section 2.6) — the
  permission never acts as the only filter.

``IsAdmin`` grants the audit and verdict-correction modules only
(CA-HU-13-12). It must never appear in the ``permission_classes`` of a
manuscript, evaluation or PDF view: an Administrator has no access to
them by API.
"""

from __future__ import annotations

from django.http import Http404
from rest_framework.permissions import SAFE_METHODS, BasePermission

from apps.users.models import Role
from apps.users.services.auth import active_role_codes

_ROLES_CACHE_ATTRIBUTE = "_gpc_active_role_codes"


def request_active_roles(request) -> list[str]:
    """Active role codes of the actor, read from PostgreSQL once per request.

    Single source of role truth for the permission layer, shared with
    ``GET /api/auth/me/``. The result is memoized for the lifetime of the
    request only: the next request reads the database again, so a role
    granted or revoked between requests applies immediately.
    """
    cached = getattr(request, _ROLES_CACHE_ATTRIBUTE, None)
    if cached is None:
        cached = active_role_codes(request.user)
        setattr(request, _ROLES_CACHE_ATTRIBUTE, cached)
    return cached


class BaseActiveRolePermission(BasePermission):
    """Module permission backed by the ACTIVE roles in PostgreSQL."""

    role_code: str = ""

    def has_permission(self, request, view) -> bool:
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return False
        return self.role_code in request_active_roles(request)


class IsAuthor(BaseActiveRolePermission):
    """Active ``AUTHOR`` role required for the author module."""

    role_code = Role.Code.AUTHOR


class IsReviewer(BaseActiveRolePermission):
    """Active ``REVIEWER`` role required for the reviewer module."""

    role_code = Role.Code.REVIEWER


class IsEditor(BaseActiveRolePermission):
    """Active ``EDITOR`` role required for the editor module."""

    role_code = Role.Code.EDITOR


class IsAdmin(BaseActiveRolePermission):
    """Active ``ADMIN`` role required for the admin module.

    Scope (plan section 6.2, CA-HU-13-12): the audit query and the
    verdict-correction authorization only. This permission never
    unlocks manuscripts, evaluations or PDFs; those views must not list
    it in ``permission_classes``.
    """

    role_code = Role.Code.ADMIN


class IsPublicCatalog(BasePermission):
    """Anonymous, read-only access to the public catalog.

    The permission only opens safe methods to any visitor, with or
    without a session. The invariant "accepted and active articles
    only" is enforced by the catalog QuerySet (plan section 2.6); the
    permission is never the only filter.
    """

    def has_permission(self, request, view) -> bool:
        return request.method in SAFE_METHODS


class BaseObjectPermission(BasePermission):
    """Base for object-level permissions: a foreign object answers ``404``.

    The module role is validated by the role permission listed before
    this class in ``permission_classes``; a user without the module role
    gets ``403`` there. When the module role is fine but the object is
    outside the actor's scope, :meth:`has_object_permission` raises
    ``Http404`` instead of returning ``False``: an object that is not
    the actor's must never reveal that it exists (plan sections 2.9 and
    6.2).
    """

    def has_permission(self, request, view) -> bool:
        return True

    def has_object_permission(self, request, view, obj) -> bool:
        if self.check_object(request, view, obj):
            return True
        raise Http404

    def check_object(self, request, view, obj) -> bool:
        raise NotImplementedError
