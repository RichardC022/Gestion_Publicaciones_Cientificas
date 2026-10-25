"""Tests for the institutional JWT authentication (TSK-19).

Covers the acceptance criteria:

1. Invalid credentials, an inactive account and a nonexistent account all
   answer with the same generic message.
2. The refresh token rotates on every use and the logout revokes the
   current one; reusing a consumed token is rejected together with its
   replacement chain.
3. Roles and account status are re-read from PostgreSQL on every request;
   the ``roles`` claim of the JWT never authorizes by itself.
"""

from __future__ import annotations

import base64
import json
from datetime import timedelta

import pytest
from django.conf import settings
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIClient

from apps.users.models import RefreshToken as RefreshTokenRecord
from apps.users.models import RevocationReason, Role, User, UserRole
from apps.users.services.auth import GENERIC_AUTH_MESSAGE

pytestmark = pytest.mark.django_db

LOGIN_URL = "/api/auth/login/"
REFRESH_URL = "/api/auth/refresh/"
LOGOUT_URL = "/api/auth/logout/"
ME_URL = "/api/auth/me/"
PASSWORD = "institucional-123"
COOKIE = settings.REFRESH_COOKIE_NAME


def make_user(**overrides):
    """Create an institutional account with defaults."""
    payload = {
        "institutional_id": "INST-1001",
        "username": "a.lopez",
        "email": "a.lopez@unl.edu.ec",
        "first_name": "Ana",
        "last_name": "López",
    }
    payload.update(overrides)
    return User.objects.create_user(password=PASSWORD, **payload)


def assign_roles(user: User, *codes: str) -> User:
    """Seed the role catalog and assign active roles."""
    call_command("seed_roles", verbosity=0)
    for code in codes:
        UserRole.objects.create(user=user, role=Role.objects.get(code=code))
    return user


def login_client(identifier: str = "INST-1001", password: str = PASSWORD):
    """Log in through the real endpoint and return the authenticated client."""
    client = APIClient()
    response = client.post(
        LOGIN_URL, {"identifier": identifier, "password": password}, format="json"
    )
    assert response.status_code == 200
    return client, response


def decode_payload(token: str) -> dict:
    """Decode the payload of a JWT without verifying the signature."""
    segment = token.split(".")[1]
    padded = segment + "=" * (-len(segment) % 4)
    return json.loads(base64.urlsafe_b64decode(padded))


class TestLogin:
    def test_login_returns_access_user_roles_and_sets_refresh_cookie(self) -> None:
        user = assign_roles(make_user(), "AUTHOR", "REVIEWER")
        client, response = login_client()
        body = response.json()

        assert body["access"]
        assert body["user"]["id"] == str(user.id)
        assert body["user"]["institutional_id"] == "INST-1001"
        assert body["user"]["full_name"] == "Ana López"
        assert body["roles"] == ["AUTHOR", "REVIEWER"]

        cookie = response.cookies[COOKIE]
        assert cookie["httponly"] is True
        assert cookie["samesite"] == "Strict"
        assert cookie["path"] == settings.REFRESH_COOKIE_PATH
        if settings.COOKIE_SECURE:
            assert cookie["secure"] is True

        assert (
            RefreshTokenRecord.objects.filter(
                user=user, revoked_at__isnull=True
            ).count()
            == 1
        )

    def test_identifier_accepts_institutional_id_username_and_email(self) -> None:
        user = assign_roles(make_user(), "AUTHOR")
        for identifier in ("INST-1001", "a.lopez", "A.LOPEZ@UNL.EDU.EC"):
            client, response = login_client(identifier=identifier)
            assert response.json()["user"]["id"] == str(user.id)

    def test_invalid_inactive_and_unknown_answer_the_same_generic_message(self) -> None:
        make_user()
        make_user(
            username="b.martinez",
            institutional_id="INST-1002",
            email="b.martinez@unl.edu.ec",
            is_active=False,
        )

        cases = (
            ("a.lopez", "contrasena-equivocada"),  # contraseña incorrecta
            ("b.martinez", PASSWORD),  # cuenta inactiva
            ("no.existe", PASSWORD),  # cuenta inexistente
        )
        messages = set()
        for identifier, password in cases:
            client = APIClient()
            response = client.post(
                LOGIN_URL,
                {"identifier": identifier, "password": password},
                format="json",
            )
            assert response.status_code == 401
            error = response.json()["error"]
            assert error["code"] == "AUTH_INVALID"
            assert error["request_id"]
            messages.add(error["message"])
        assert messages == {GENERIC_AUTH_MESSAGE}

    def test_login_without_payload_answers_400_envelope(self) -> None:
        client = APIClient()
        response = client.post(LOGIN_URL, {}, format="json")

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"


class TestRefresh:
    def test_refresh_rotates_the_token_on_every_use(self) -> None:
        user = assign_roles(make_user(), "AUTHOR")
        client, _ = login_client()
        first_token = client.cookies[COOKIE].value

        response = client.post(REFRESH_URL, format="json")
        assert response.status_code == 200
        assert response.json()["access"]

        second_token = client.cookies[COOKIE].value
        assert second_token != first_token

        # Tras la rotación queda exactamente un refresh vigente.
        assert (
            RefreshTokenRecord.objects.filter(
                user=user, revoked_at__isnull=True
            ).count()
            == 1
        )

        # El token rotado quedó revocado: reutilizarlo se rechaza.
        client.cookies[COOKIE] = first_token
        reused = client.post(REFRESH_URL, format="json")
        assert reused.status_code == 401
        assert reused.json()["error"]["code"] == "AUTH_INVALID"

        # La reutilización también revoca el reemplazo vigente (detección
        # de cadena): no queda ningún refresh vivo para esta sesión.
        assert (
            RefreshTokenRecord.objects.filter(
                user=user, revoked_at__isnull=True
            ).count()
            == 0
        )

    def test_reusing_a_rotated_token_revokes_its_replacement(self) -> None:
        assign_roles(make_user(), "AUTHOR")
        client, _ = login_client()
        old_token = client.cookies[COOKIE].value

        client.post(REFRESH_URL, format="json")
        replacement = client.cookies[COOKIE].value

        # Reutilización del token consumido: 401 y el reemplazo muere con él.
        client.cookies[COOKIE] = old_token
        assert client.post(REFRESH_URL, format="json").status_code == 401

        client.cookies[COOKIE] = replacement
        assert client.post(REFRESH_URL, format="json").status_code == 401
        assert (
            RefreshTokenRecord.objects.filter(
                revoked_reason=RevocationReason.REUSE
            ).count()
            == 1
        )

    def test_refresh_without_cookie_answers_401(self) -> None:
        client = APIClient()
        response = client.post(REFRESH_URL, format="json")

        assert response.status_code == 401
        assert response.json()["error"]["code"] == "AUTH_INVALID"

    def test_refresh_rejects_tokens_past_the_idle_window(self) -> None:
        assign_roles(make_user(), "AUTHOR")
        client, _ = login_client()

        record = RefreshTokenRecord.objects.get(revoked_at__isnull=True)
        idle = timedelta(minutes=settings.SESSION_IDLE_MINUTES)
        record.issued_at = timezone.now() - idle - timedelta(minutes=1)
        record.save(update_fields=["issued_at"])

        response = client.post(REFRESH_URL, format="json")
        assert response.status_code == 401
        record.refresh_from_db()
        assert record.revoked_reason == RevocationReason.IDLE_TIMEOUT

    def test_refresh_rejects_a_disabled_account_even_with_valid_cookie(self) -> None:
        user = assign_roles(make_user(), "AUTHOR")
        client, _ = login_client()

        user.is_active = False
        user.save(update_fields=["is_active"])

        response = client.post(REFRESH_URL, format="json")
        assert response.status_code == 401
        assert response.json()["error"]["message"] == GENERIC_AUTH_MESSAGE
        record = RefreshTokenRecord.objects.get(revoked_at__isnull=False)
        assert record.revoked_reason == RevocationReason.ACCOUNT_DISABLED

    def test_refresh_returns_roles_reread_from_the_database(self) -> None:
        user = assign_roles(make_user(), "AUTHOR", "REVIEWER")
        client, _ = login_client()

        UserRole.objects.filter(user=user, role__code="AUTHOR").update(
            is_active=False, revoked_at=timezone.now()
        )

        response = client.post(REFRESH_URL, format="json")
        assert response.status_code == 200
        assert response.json()["roles"] == ["REVIEWER"]


class TestLogout:
    def test_logout_revokes_the_current_refresh_and_clears_the_cookie(self) -> None:
        assign_roles(make_user(), "AUTHOR")
        client, login_response = login_client()
        access = login_response.json()["access"]
        live_token = client.cookies[COOKIE].value

        response = client.post(LOGOUT_URL, HTTP_AUTHORIZATION=f"Bearer {access}")
        assert response.status_code == 204
        assert response.cookies[COOKIE].value == ""

        jti = decode_payload(live_token)["jti"]
        record = RefreshTokenRecord.objects.get(jti=jti)
        assert record.revoked_reason == RevocationReason.LOGOUT

        # El token revocado ya no refresca.
        client.cookies[COOKIE] = live_token
        assert client.post(REFRESH_URL, format="json").status_code == 401

    def test_logout_requires_authentication(self) -> None:
        assign_roles(make_user(), "AUTHOR")
        client = APIClient()
        response = client.post(LOGOUT_URL, format="json")

        assert response.status_code == 401
        assert response.json()["error"]["code"] == "AUTH_INVALID"

    def test_logout_is_idempotent_and_keeps_the_first_reason(self) -> None:
        assign_roles(make_user(), "AUTHOR")
        client, login_response = login_client()
        access = login_response.json()["access"]

        first = client.post(LOGOUT_URL, HTTP_AUTHORIZATION=f"Bearer {access}")
        second = client.post(LOGOUT_URL, HTTP_AUTHORIZATION=f"Bearer {access}")
        assert first.status_code == 204
        assert second.status_code == 204

        record = RefreshTokenRecord.objects.get()
        assert record.revoked_reason == RevocationReason.LOGOUT


class TestMe:
    def test_me_returns_identity_roles_and_navigation(self) -> None:
        assign_roles(make_user(), "AUTHOR", "EDITOR")
        client, login_response = login_client()
        access = login_response.json()["access"]

        response = client.get(ME_URL, HTTP_AUTHORIZATION=f"Bearer {access}")
        assert response.status_code == 200
        body = response.json()

        assert body["user"]["institutional_id"] == "INST-1001"
        assert body["roles"] == ["AUTHOR", "EDITOR"]
        routes = {item["route"] for item in body["navigation"]}
        assert "/app/author/manuscripts" in routes
        assert "/app/editor/submissions" in routes
        assert all(item["role"] in body["roles"] for item in body["navigation"])

    def test_me_rereads_roles_from_the_database_not_from_the_claim(self) -> None:
        user = assign_roles(make_user(), "AUTHOR", "REVIEWER")
        client, login_response = login_client()
        access = login_response.json()["access"]

        # El claim del token aún dice ["AUTHOR", "REVIEWER"]...
        assert decode_payload(access)["roles"] == ["AUTHOR", "REVIEWER"]

        UserRole.objects.filter(user=user, is_active=True).update(
            is_active=False, revoked_at=timezone.now()
        )

        # ...pero /me/ lee PostgreSQL: el rol retirado ya no aparece.
        response = client.get(ME_URL, HTTP_AUTHORIZATION=f"Bearer {access}")
        assert response.status_code == 200
        body = response.json()
        assert body["roles"] == []
        assert body["navigation"] == []

    def test_me_rejects_a_session_whose_account_was_disabled(self) -> None:
        user = assign_roles(make_user(), "AUTHOR")
        client, login_response = login_client()
        access = login_response.json()["access"]

        user.is_active = False
        user.save(update_fields=["is_active"])

        response = client.get(ME_URL, HTTP_AUTHORIZATION=f"Bearer {access}")
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "AUTH_INVALID"

    def test_me_without_token_answers_401(self) -> None:
        client = APIClient()
        response = client.get(ME_URL)

        assert response.status_code == 401
        assert response.json()["error"]["code"] == "AUTH_INVALID"

    def test_me_with_a_tampered_token_answers_the_generic_401(self) -> None:
        assign_roles(make_user(), "AUTHOR")
        client = APIClient()
        response = client.get(ME_URL, HTTP_AUTHORIZATION="Bearer no-es-un-jwt")

        assert response.status_code == 401
        error = response.json()["error"]
        assert error["code"] == "AUTH_INVALID"
        assert error["message"] == GENERIC_AUTH_MESSAGE
        assert error["details"] == {}
