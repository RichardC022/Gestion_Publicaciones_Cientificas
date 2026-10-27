"""Institutional JWT authentication for the REST API (plan section 6.1).

``InstitutionalJWTAuthentication`` extends SimpleJWT's bearer scheme with
the domain invariant of the plan: every rejection — malformed token,
expired token, unknown account or disabled account — answers with the same
``AUTH_INVALID`` error so a failed authentication can never be used to
enumerate institutional accounts.
"""

from __future__ import annotations

from rest_framework.request import Request
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed

from apps.users.services.auth import GENERIC_AUTH_MESSAGE
from config.exceptions import DomainError, ErrorCode


class InstitutionalJWTAuthentication(JWTAuthentication):
    """Bearer authentication that never reveals the failure reason."""

    def authenticate(self, request: Request):
        try:
            return super().authenticate(request)
        except AuthenticationFailed:
            # Token vencido, malformado, usuario inexistente o cuenta
            # deshabilitada: la misma respuesta genérica.
            raise DomainError(
                GENERIC_AUTH_MESSAGE, code=ErrorCode.AUTH_INVALID
            ) from None
