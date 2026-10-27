"""Authorized delivery of a version's PDF (plan sections 4.6 and 6.4).

Django only authorizes; Nginx serves the bytes. The answer is an empty
``200`` whose ``X-Accel-Redirect`` points to the internal location
``/_protected/``, which Nginx maps to ``/data/media/private/``. Rules:

* The internal path is built ONLY from the manuscript UUID and the
  version number — never from the stored name, a query parameter or
  any user input. Author and editor always get ``original.pdf``; the
  reviewer has its own entry point that serves ``sanitized.pdf`` and
  can never resolve the original.
* The download is audited BEFORE answering. If the audit trail cannot
  be written no redirect is emitted and the answer is ``503``.
* A file that cannot be found is a storage failure (``503``), and it is
  not audited as a download because nothing was delivered.
"""

from __future__ import annotations

from django.db import transaction
from django.http import HttpResponse

from apps.audit.models import AuditLog
from apps.audit.services import AuditService, AuditUnavailable
from apps.publications.models import Manuscript, ManuscriptVersion
from apps.publications.services.storage import private_path, version_relative_dir
from apps.users.models import Role, User
from apps.users.services.auth import AUDIT_UNAVAILABLE_MESSAGE
from config.exceptions import DomainError, ErrorCode

INTERNAL_PREFIX = "/_protected/"
FILE_UNAVAILABLE_MESSAGE = "El PDF de esta versión no está disponible por ahora."


def authorize_original_download(
    *, manuscript: Manuscript, version: ManuscriptVersion, user: User, context: dict
) -> str:
    """Audit the download and return the internal URI Nginx must serve."""
    role = Role.Code.AUTHOR if manuscript.created_by_id == user.pk else Role.Code.EDITOR
    return _authorize_download(
        kind="original",
        manuscript=manuscript,
        version=version,
        user=user,
        role=role,
        context=context,
    )


def authorize_sanitized_download(
    *, manuscript: Manuscript, version: ManuscriptVersion, user: User, context: dict
) -> str:
    """Same as the original one, for the reviewer's ``sanitized.pdf``."""
    return _authorize_download(
        kind="sanitized",
        manuscript=manuscript,
        version=version,
        user=user,
        role=Role.Code.REVIEWER,
        context=context,
    )


def _authorize_download(
    *,
    kind: str,
    manuscript: Manuscript,
    version: ManuscriptVersion,
    user: User,
    role: str,
    context: dict,
) -> str:
    relative = version_relative_dir(manuscript.pk, version.version_number) / f"{kind}.pdf"
    if not private_path(relative).is_file():
        raise DomainError(FILE_UNAVAILABLE_MESSAGE, code=ErrorCode.STORAGE_UNAVAILABLE)

    try:
        with transaction.atomic():
            AuditService.record(
                action="MANUSCRIPT_FILE_DOWNLOADED",
                entity_type="MANUSCRIPT_VERSION",
                entity_id=version.pk,
                result=AuditLog.Result.SUCCESS,
                actor=user,
                actor_role=role,
                details={
                    "manuscript_id": str(manuscript.pk),
                    "version_number": version.version_number,
                    "kind": kind,
                },
                **context,
            )
    except AuditUnavailable as exc:
        raise DomainError(AUDIT_UNAVAILABLE_MESSAGE, code=ErrorCode.AUDIT_UNAVAILABLE) from exc
    return f"{INTERNAL_PREFIX}{relative}"


def xaccel_response(internal_uri: str, filename: str) -> HttpResponse:
    """Empty ``200`` that tells Nginx to serve ``internal_uri`` as an attachment."""
    response = HttpResponse(status=200)
    response["X-Accel-Redirect"] = internal_uri
    response["Content-Type"] = "application/pdf"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, no-store"
    return response
