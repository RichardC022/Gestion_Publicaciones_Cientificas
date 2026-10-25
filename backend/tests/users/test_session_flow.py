"""Integration scenarios of the institutional session (TSK-23).

End-to-end walks over the real API with ``APIClient`` and ``factory_boy``
against the PostgreSQL test database (plan section 7.1). The per-detail
units live in the module suites (``test_auth``, ``test_rate_limit``,
``test_permissions``, ``test_dashboard``); these scenarios verify the
criteria TOGETHER as coherent flows:

* five failed attempts, inactive account, revoked role and revoked
  refresh;
* the multirrole panel renders simultaneous sections and tolerates the
  failure of one section without cancelling the others.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.conf import settings
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIClient

from apps.users.models import LoginAttempt, Role, UserRole
from apps.users.services.dashboard import (
    SECTION_BUILDERS,
    SECTION_ERROR_MESSAGE,
)
from tests.factories import FACTORY_PASSWORD, UserFactory, UserRoleFactory

pytestmark = pytest.mark.django_db

LOGIN_URL = "/api/auth/login/"
REFRESH_URL = "/api/auth/refresh/"
LOGOUT_URL = "/api/auth/logout/"
ME_URL = "/api/auth/me/"
DASHBOARD_URL = "/api/dashboard/"
COOKIE = settings.REFRESH_COOKIE_NAME
WRONG_PASSWORD = "secreto-equivocado"


def with_roles(user, *codes):
    """Seed the catalog and attach active roles to a factory account."""
    call_command("seed_roles", verbosity=0)
    for code in codes:
        UserRoleFactory(user=user, role_code=code)
    return user


def login(identifier: str, password: str = FACTORY_PASSWORD):
    """One login request through the real endpoint."""
    client = APIClient()
    response = client.post(
        LOGIN_URL, {"identifier": identifier, "password": password}, format="json"
    )
    return client, response


class TestLockoutScenario:
    def test_five_failures_block_until_the_window_expires(self) -> None:
        user = with_roles(UserFactory(), "AUTHOR")
        client = APIClient()

        for _ in range(5):
            failed = client.post(
                LOGIN_URL,
                {"identifier": user.institutional_id, "password": WRONG_PASSWORD},
                format="json",
            )
            assert failed.status_code == 401
        assert LoginAttempt.objects.count() == 5

        # Sexto intento, incluso con la contraseña correcta: bloqueado.
        blocked = client.post(
            LOGIN_URL,
            {"identifier": user.institutional_id, "password": FACTORY_PASSWORD},
            format="json",
        )
        assert blocked.status_code == 429
        assert 0 < int(blocked.headers["Retry-After"]) <= 15 * 60

        # La ventana vence y el identificador vuelve a aceptar el acceso.
        LoginAttempt.objects.update(
            attempted_at=timezone.now() - timedelta(minutes=16)
        )
        _, response = login(user.institutional_id)
        assert response.status_code == 200


class TestInactiveAccountScenario:
    def test_inactive_account_answers_exactly_like_a_wrong_password(self) -> None:
        inactive = with_roles(UserFactory(is_active=False), "AUTHOR")
        active = with_roles(UserFactory(), "AUTHOR")

        _, inactive_response = login(inactive.institutional_id)
        _, wrong_response = login(active.institutional_id, password=WRONG_PASSWORD)

        assert inactive_response.status_code == wrong_response.status_code == 401
        error_inactive = inactive_response.json()["error"]
        error_wrong = wrong_response.json()["error"]
        assert error_inactive["code"] == error_wrong["code"] == "AUTH_INVALID"
        assert error_inactive["message"] == error_wrong["message"]


class TestRevokedRoleScenario:
    def test_revoked_role_disappears_from_the_valid_session(self) -> None:
        user = with_roles(UserFactory(), "AUTHOR", "EDITOR")
        client, response = login(user.institutional_id)
        access = response.json()["access"]
        assert response.json()["roles"] == ["AUTHOR", "EDITOR"]

        UserRole.objects.filter(user=user, role__code="AUTHOR").update(
            is_active=False, revoked_at=timezone.now()
        )

        me = client.get(ME_URL, HTTP_AUTHORIZATION=f"Bearer {access}").json()
        assert me["roles"] == ["EDITOR"]

        dashboard = client.get(
            DASHBOARD_URL, HTTP_AUTHORIZATION=f"Bearer {access}"
        ).json()
        assert set(dashboard["sections"]) == {"editor"}


class TestRevokedRefreshScenario:
    def test_logout_revokes_the_refresh_and_it_never_rotates_again(self) -> None:
        user = with_roles(UserFactory(), "REVIEWER")
        client, response = login(user.institutional_id)
        access = response.json()["access"]
        live_cookie = client.cookies[COOKIE].value

        logout = client.post(LOGOUT_URL, HTTP_AUTHORIZATION=f"Bearer {access}")
        assert logout.status_code == 204

        client.cookies[COOKIE] = live_cookie
        denied = client.post(REFRESH_URL, format="json")
        assert denied.status_code == 401
        assert denied.json()["error"]["code"] == "AUTH_INVALID"


class TestMultirrolePanelScenario:
    def test_simultaneous_sections_survive_a_partial_failure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        user = with_roles(UserFactory(), "AUTHOR", "REVIEWER", "EDITOR", "ADMIN")
        client, response = login(user.institutional_id)
        access = response.json()["access"]

        body = client.get(DASHBOARD_URL, HTTP_AUTHORIZATION=f"Bearer {access}").json()
        assert body["roles"] == ["AUTHOR", "REVIEWER", "EDITOR", "ADMIN"]
        assert set(body["sections"]) == {"author", "reviewer", "editor", "admin"}
        assert all(section["status"] == "ok" for section in body["sections"].values())

        def broken_section(user_arg):
            raise RuntimeError("simulated section failure")

        monkeypatch.setitem(SECTION_BUILDERS, Role.Code.REVIEWER, broken_section)

        body = client.get(DASHBOARD_URL, HTTP_AUTHORIZATION=f"Bearer {access}").json()
        assert body["sections"]["reviewer"]["status"] == "error"
        assert body["sections"]["reviewer"]["message"] == SECTION_ERROR_MESSAGE
        assert body["sections"]["author"]["status"] == "ok"
        assert body["sections"]["editor"]["status"] == "ok"
        assert body["sections"]["admin"]["status"] == "ok"
