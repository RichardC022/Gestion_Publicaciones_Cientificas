"""Institutional auth endpoints: login, refresh, logout and /me/ (TSK-19).

Cookie contract (plan sections 2.2 and 6.1): the refresh token only
travels in the ``gpc_refresh`` cookie — ``HttpOnly``, ``SameSite=Strict``
and ``Secure`` in production — scoped to ``/api/v1/auth/``. The access token
is returned in the JSON body and lives in client memory only.
"""

from __future__ import annotations

from django.conf import settings
from django.db import transaction
from drf_spectacular.utils import extend_schema, extend_schema_view
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
    MeSerializer,
    SessionSerializer,
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
from config.openapi import error_response
from config.request_context import client_ip


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


@extend_schema_view(
    post=extend_schema(
        tags=["Autenticación"],
        operation_id="auth_login",
        summary="Iniciar sesión",
        description=(
            "Valida las credenciales institucionales y abre la sesión. Devuelve el token de "
            "acceso en `data.access` y deja el de renovación en la cookie `gpc_refresh` "
            "(`HttpOnly`, `SameSite=Strict`). Toda falla de credenciales responde lo mismo "
            "(`AUTH_INVALID`) para no revelar qué cuentas existen. Cinco fallos en quince "
            "minutos bloquean el identificador (`AUTH_LOCKED`, con `Retry-After`)."
        ),
        request=LoginSerializer,
        responses={
            200: SessionSerializer,
            401: error_response("Credenciales inválidas (AUTH_INVALID)."),
            429: error_response("Identificador bloqueado temporalmente (AUTH_LOCKED)."),
            503: error_response("La auditoría no está disponible (AUDIT_UNAVAILABLE)."),
        },
        auth=[],
    ),
)
class LoginView(APIView):
    """``POST /api/v1/auth/login/``: validate credentials, open the session.

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
            ip_address=client_ip(request),
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


@extend_schema_view(
    post=extend_schema(
        tags=["Autenticación"],
        operation_id="auth_refresh",
        summary="Renovar la sesión",
        description=(
            "Rota la cookie de renovación `gpc_refresh` y emite un token de acceso nuevo. "
            "No lleva cuerpo ni `Authorization`: la cookie es la credencial."
        ),
        request=None,
        responses={
            200: SessionSerializer,
            401: error_response("Cookie ausente, vencida o revocada (AUTH_INVALID)."),
        },
        auth=[],
    ),
)
class RefreshView(APIView):
    """``POST /api/v1/auth/refresh/``: rotate the cookie, issue a new access."""

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


@extend_schema_view(
    post=extend_schema(
        tags=["Autenticación"],
        operation_id="auth_logout",
        summary="Cerrar sesión",
        description=(
            "Revoca el token de renovación actual y borra la cookie. La revocación y la "
            "auditoría comparten transacción: si no se puede auditar, no se revoca y responde 503."
        ),
        request=None,
        responses={
            204: None,
            503: error_response("La auditoría no está disponible (AUDIT_UNAVAILABLE)."),
        },
    ),
)
class LogoutView(APIView):
    """``POST /api/v1/auth/logout/``: revoke the current refresh token (204).

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
                    ip_address=client_ip(request),
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


@extend_schema_view(
    get=extend_schema(
        tags=["Autenticación"],
        operation_id="auth_me",
        summary="Usuario autenticado",
        description="Identidad, roles activos (releídos de la base de datos) y módulos de navegación.",
        responses={200: MeSerializer},
    ),
)
class MeView(APIView):
    """``GET /api/v1/auth/me/``: identity, active roles and navigation.

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


@extend_schema_view(
    get=extend_schema(
        tags=["Tablero"],
        operation_id="dashboard_retrieve",
        summary="Tablero unificado",
        description=(
            "Una sección por cada rol activo. Cada sección se resuelve por separado: si una "
            "falla, la respuesta sigue siendo 200 y esa sección trae `status: error`."
        ),
        responses={200: DashboardSerializer},
    ),
)
class DashboardView(APIView):
    """``GET /api/v1/dashboard/``: every enabled section in one response.

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
