"""Institutional auth endpoints: login, refresh, logout and /me/ (TSK-19).

Cookie contract (plan sections 2.2 and 6.1): the refresh token only
travels in the ``gpc_refresh`` cookie — ``HttpOnly``, ``SameSite=Strict``
and ``Secure`` in production — scoped to ``/api/auth/``. The access token
is returned in the JSON body and lives in client memory only.
"""

from __future__ import annotations

from django.conf import settings
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.users.models import RevocationReason
from apps.users.serializers import (
    LoginSerializer,
    SessionUserSerializer,
    navigation_permissions,
)
from apps.users.services.auth import (
    GENERIC_AUTH_MESSAGE,
    active_role_codes,
    authenticate_by_identifier,
    issue_session,
    revoke_current,
    rotate,
)
from config.exceptions import DomainError, ErrorCode


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
    """``POST /api/auth/login/``: validate credentials, open the session."""

    # Sin clases de autenticación: un Authorization viejo o vencido nunca
    # debe impedir iniciar sesión.
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request: Request) -> Response:
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = authenticate_by_identifier(
            serializer.validated_data["identifier"],
            serializer.validated_data["password"],
        )
        if user is None:
            # Credenciales inválidas, cuenta inexistente o cuenta inactiva:
            # la misma respuesta genérica (plan §6.1).
            raise DomainError(GENERIC_AUTH_MESSAGE, code=ErrorCode.AUTH_INVALID)

        session = issue_session(user)
        response = Response(
            {
                "access": session.access,
                "user": SessionUserSerializer(user).data,
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
    """``POST /api/auth/logout/``: revoke the current refresh token (204)."""

    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        raw_refresh = request.COOKIES.get(settings.REFRESH_COOKIE_NAME)
        if raw_refresh:
            revoke_current(raw_refresh, reason=RevocationReason.LOGOUT)
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
