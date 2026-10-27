"""Unified dashboard composition (plan sections 2.2 and 3.4).

One call to ``GET /api/dashboard/`` returns every section enabled by
the actor's active roles — the panel never asks to choose a role:

* Sections appear only for active roles: a single-role person never
  sees empty modules of roles they do not hold.
* Each section resolves independently. When one fails, the response
  still is ``200``: the failed section carries a retryable message and
  the healthy ones are returned complete.
* A person without active roles receives an explicitly empty
  ``sections`` object: the interface shows "Sin roles habilitados" and
  blocks the internal routes (guards of TSK-25, permissions of TSK-21).

Section data providers are registered per role. The domain modules
fill their own sections as their models arrive — author with the
publications module (TSK-32 onwards), reviewer with the reviews module
(TSK-60 onwards), editor with the editor module (TSK-47 onwards) and
admin with the audit module (TSK-73 onwards). Until then every section
renders with empty data, already composed by this service.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from apps.users.models import Role
from apps.users.services.auth import active_role_codes

logger = logging.getLogger("apps.users.dashboard")

#: Retryable message carried by a failed section (plan section 2.2).
SECTION_ERROR_MESSAGE = "No se pudo cargar esta sección. Intente de nuevo."


def build_author_section(user) -> dict[str, Any]:
    """AUTHOR section data: own manuscripts and pending tasks.

    The manuscript counters arrive with the publications module
    (TSK-32 onwards).
    """
    return {}


def build_reviewer_section(user) -> dict[str, Any]:
    """REVIEWER section data: pending assignments and deadlines.

    The assignment data arrive with the reviews module (TSK-60
    onwards).
    """
    return {}


def build_editor_section(user) -> dict[str, Any]:
    """EDITOR section data: new submissions and expired assignments.

    The submission data arrive with the editor module (TSK-47
    onwards).
    """
    return {}


def build_admin_section(user) -> dict[str, Any]:
    """ADMIN section data: audit overview and correction grants.

    The audit data arrive with the admin module (TSK-73 onwards).
    """
    return {}


#: Section data providers by active role code.
SECTION_BUILDERS: dict[str, Callable[[Any], dict[str, Any]]] = {
    Role.Code.AUTHOR: build_author_section,
    Role.Code.REVIEWER: build_reviewer_section,
    Role.Code.EDITOR: build_editor_section,
    Role.Code.ADMIN: build_admin_section,
}


def build_dashboard(user) -> dict[str, Any]:
    """Compose the active roles and their sections for one actor.

    Roles are re-read from PostgreSQL (plan section 6.1) and every
    section is resolved in isolation: one failing provider never
    cancels the others.
    """
    roles = active_role_codes(user)
    sections: dict[str, dict[str, Any]] = {}
    for role in roles:
        builder = SECTION_BUILDERS.get(role)
        if builder is None:
            continue
        try:
            section = {"status": "ok", "data": builder(user), "message": None}
        except Exception:
            # Aislamiento por sección: el fallo no cancela las demás.
            # Se registra solo el rol, sin datos personales.
            logger.exception("Dashboard section failed [role=%s]", role)
            section = {
                "status": "error",
                "data": None,
                "message": SECTION_ERROR_MESSAGE,
            }
        sections[role.lower()] = section
    return {"roles": roles, "sections": sections}
