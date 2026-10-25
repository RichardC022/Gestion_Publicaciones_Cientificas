"""Institutional auth endpoints: login, refresh, logout and /me/ (TSK-19).

Cookie contract (plan sections 2.2 and 6.1): the refresh token only
travels in the ``gpc_refresh`` cookie — ``HttpOnly``, ``SameSite=Strict``
and ``Secure`` in production — scoped to ``/api/auth/``. The access token
is returned in the JSON body and lives in client memory only.
"""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_ipv46_address
from django.db import transaction
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.models import AuditLog
from apps.audit.services import AuditService, AuditUnavailable
from apps.users.models import RevocationReason
from apps.users.serializers import (
    DashboardSerializer,
    LoginSerializer,
    SessionUserSerializer,
    navigation_permissions,
)
from apps.users.services.auth import (
    AUDIT_UNAVAILABLE_MESSAGE,
    GENERIC_AUTH_MESSAGE,
    active_role_codes,
    login,
    revoke_current,
    rotate,
)
from apps.users.services.dashboard import build_dashboard
from config.exceptions import DomainError, ErrorCode
from config.middleware import get_request_id


def _client_ip(request: Request) -> str | None:
    """Best-effort client IP for the attempt registry and the audit trail.

    Nginx (TSK-04) forwards ``X-Forwarded-For`` and ``X-Real-IP``; the
    first forwarded entry wins. Anything that is not a valid address is
    dropped instead of breaking the login.
    """
    forwarded = (request.META.get("HTTP_X_FORWARDED_FOR") or "")
    candidate = forwarded.split(",")[0].strip()
    if not candidate:
        candidate = (request.META.get("HTTP_X_REAL_IP") or "").strip()
    if not candidate:
        candidate = (request.META.get("REMOTE_ADDR") or "").strip()
    if not candidate:
        return None
    try:
        validate_ipv46_address(candidate)
    except DjangoValidationError:
        return None
    return candidate


def _set_refresh_cookie(response: Response, raw_refresh: str) -> None:
    """Attach the refresh token cookie with the flags of TSK-16."""
    response.set_cookie(
        settings.REFRESH_COOKIE_NAME,
        raw_refresh,
        max_age=settings.JWT_REFRESH_DAYS * 24 * 60 * 60,
        path=settings.REFRESH_COOKIE_PATH,
        httponly=settings.REFRESH_COOKIE_HTTPONLY,
        samesite=settings.REFRESH_COOKIE_SAMESITE,
        secure=settings.COOKIE_SECURE,
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        settings.REFRESH_COOKIE_NAME,
        path=settings.REFRESH_COOKIE_PATH,
        samesite=settings.REFRESH_COOKIE_SAMESITE,
    )


class LoginView(APIView):
    """``POST /api/auth/login/``: validate credentials, open the session.

    The full flow lives in the service (TSK-20): rate limit of five
    failures per identifier in fifteen minutes, generic answer for every
    credential failure and audit of success, failure and block.
    """

    # Sin clases de autenticación: un Authorization viejo o vencido nunca
    # debe impedir iniciar sesión.
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request: Request) -> Response:
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        session = login(
            serializer.validated_data["identifier"],
            serializer.validated_data["password"],
            ip_address=_client_ip(request),
            user_agent=(request.META.get("HTTP_USER_AGENT") or "")[:300] or None,
            request_id=get_request_id(request),
        )
        response = Response(
            {
                "access": session.access,
                "user": SessionUserSerializer(session.record.user).data,
                "roles": session.roles,
            },
            status=status.HTTP_200_OK,
        )
        _set_refresh_cookie(response, session.refresh)
        return response


class RefreshView(APIView):
    """``POST /api/auth/refresh/``: rotate the cookie, issue a new access."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request: Request) -> Response:
        raw_refresh = request.COOKIES.get(settings.REFRESH_COOKIE_NAME)
        if not raw_refresh:
            raise DomainError(GENERIC_AUTH_MESSAGE, code=ErrorCode.AUTH_INVALID)

        session = rotate(raw_refresh)
        response = Response(
            {
                "access": session.access,
                "user": SessionUserSerializer(session.record.user).data,
                "roles": session.roles,
            },
            status=status.HTTP_200_OK,
        )
        _set_refresh_cookie(response, session.refresh)
        return response


class LogoutView(APIView):
    """``POST /api/auth/logout/``: revoke the current refresh token (204).

    The logout is a critical event of the audit trail (plan section 6.5):
    the revocation and the audit row share one transaction, so if the
    audit cannot be written the revocation rolls back and the endpoint
    answers ``503`` instead of leaving a half-closed session.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        raw_refresh = request.COOKIES.get(settings.REFRESH_COOKIE_NAME)
        try:
            with transaction.atomic():
                if raw_refresh:
                    revoke_current(raw_refresh, reason=RevocationReason.LOGOUT)
                AuditService.record(
                    action="LOGOUT",
                    entity_type="SESSION",
                    result=AuditLog.Result.SUCCESS,
                    actor=request.user,
                    request_id=get_request_id(request),
                    ip_address=_client_ip(request),
                    user_agent=(request.META.get("HTTP_USER_AGENT") or "")[:300]
                    or None,
                )
        except AuditUnavailable as exc:
            raise DomainError(
                AUDIT_UNAVAILABLE_MESSAGE, code=ErrorCode.AUDIT_UNAVAILABLE
            ) from exc
        response = Response(status=status.HTTP_204_NO_CONTENT)
        _clear_refresh_cookie(response)
        return response


class MeView(APIView):
    """``GET /api/auth/me/``: identity, active roles and navigation.

    Roles are always re-read from PostgreSQL; the ``roles`` claim of the
    access token is only a hint and never authorizes by itself.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        roles = active_role_codes(request.user)
        return Response(
            {
                "user": SessionUserSerializer(request.user).data,
                "roles": roles,
                "navigation": navigation_permissions(roles),
            }
        )


class DashboardView(APIView):
    """``GET /api/dashboard/``: every enabled section in one response.

    Roles are re-read from PostgreSQL; sections appear only for the
    active ones and each one resolves independently (plan sections 2.2
    and 3.4). A failing section keeps the ``200`` and carries a
    retryable message; the panel never asks to choose a role.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        dashboard = build_dashboard(request.user)
        payload = {
            "user": request.user,
            "roles": dashboard["roles"],
            "sections": dashboard["sections"],
        }
        return Response(DashboardSerializer(payload).data)
