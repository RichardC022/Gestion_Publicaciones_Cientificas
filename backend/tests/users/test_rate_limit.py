"""Tests for the login attempt limit and login audit (TSK-20).

Covers the acceptance criteria:

1. The sixth attempt inside the fifteen-minute window answers ``429``
   with ``Retry-After`` and does not reveal whether the account exists.
2. The block expires by itself once the window has passed.
3. The audit keeps the attempted identifier, the IP and the result of
   success, failure and block — never the password.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.db.utils import IntegrityError
from django.utils import timezone
from rest_framework.test import APIClient

from apps.audit.models import AuditLog
from apps.users.models import LoginAttempt
from apps.users.models import RefreshToken as RefreshTokenRecord
from apps.users.models import User
from apps.users.services.auth import (
    GENERIC_AUTH_MESSAGE,
    LOCKED_MESSAGE,
    LOCKOUT_WINDOW,
)

pytestmark = pytest.mark.django_db

LOGIN_URL = "/api/auth/login/"
CORRECT_PASSWORD = "institucional-123"
WRONG_PASSWORD = "secreto-equivocado-XYZ"


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
    return User.objects.create_user(password=CORRECT_PASSWORD, **payload)


def attempt(client, identifier, password, **extra):
    """One login request through the real endpoint."""
    return client.post(
        LOGIN_URL,
        {"identifier": identifier, "password": password},
        format="json",
        **extra,
    )


class TestLoginRateLimit:
    def test_five_failures_answer_401_then_the_sixth_answers_429(self) -> None:
        make_user()
        client = APIClient()

        for _ in range(5):
            response = attempt(client, "INST-1001", WRONG_PASSWORD)
            assert response.status_code == 401
            assert response.json()["error"]["message"] == GENERIC_AUTH_MESSAGE

        # Sexto intento dentro de la ventana: bloqueado con 429.
        sixth = attempt(client, "INST-1001", CORRECT_PASSWORD)
        assert sixth.status_code == 429
        error = sixth.json()["error"]
        assert error["code"] == "AUTH_LOCKED"
        assert error["message"] == LOCKED_MESSAGE
        retry_after = int(sixth.headers["Retry-After"])
        assert 0 < retry_after <= int(LOCKOUT_WINDOW.total_seconds())

    def test_blocked_identifier_does_not_reveal_whether_the_account_exists(self) -> None:
        # Cuenta real bloqueada: 429 incluso con la contraseña CORRECTA,
        # porque el bloqueo se comprueba antes de validar credenciales.
        make_user()
        client = APIClient()
        for _ in range(5):
            attempt(client, "INST-1001", WRONG_PASSWORD)
        real = attempt(client, "INST-1001", CORRECT_PASSWORD)
        assert real.status_code == 429

        # Identificador inexistente golpeado igual: misma respuesta.
        ghost_client = APIClient()
        for _ in range(5):
            attempt(ghost_client, "cuenta.fantasma", WRONG_PASSWORD)
        ghost = attempt(ghost_client, "cuenta.fantasma", CORRECT_PASSWORD)
        assert ghost.status_code == 429
        assert ghost.json()["error"]["code"] == real.json()["error"]["code"]
        assert ghost.json()["error"]["message"] == real.json()["error"]["message"]

    def test_the_lock_expires_by_itself_when_the_window_passes(self) -> None:
        user = make_user()
        client = APIClient()
        for _ in range(5):
            attempt(client, "INST-1001", WRONG_PASSWORD)
        assert attempt(client, "INST-1001", CORRECT_PASSWORD).status_code == 429

        # La ventana vence: los cinco fallos quedan fuera de los quince
        # minutos y el identificador vuelve a aceptar el acceso sin que
        # exista ninguna limpieza programada.
        LoginAttempt.objects.update(
            attempted_at=timezone.now() - LOCKOUT_WINDOW - timedelta(minutes=1)
        )
        response = attempt(client, "INST-1001", CORRECT_PASSWORD)
        assert response.status_code == 200
        assert response.json()["user"]["id"] == str(user.id)

    def test_blocked_attempts_do_not_extend_the_lock(self) -> None:
        make_user()
        client = APIClient()
        for _ in range(5):
            attempt(client, "INST-1001", WRONG_PASSWORD)
        for _ in range(3):
            assert attempt(client, "INST-1001", CORRECT_PASSWORD).status_code == 429

        # Los intentos rechazados por el bloqueo no cuentan como fallos
        # nuevos: el candado caduca exactamente con la ventana.
        assert LoginAttempt.objects.count() == 5

    def test_the_limit_counts_identifiers_case_insensitively(self) -> None:
        make_user()
        client = APIClient()
        statuses = []
        for identifier in ("INST-1001", "inst-1001", "INST-1001"):
            statuses.append(attempt(client, identifier, WRONG_PASSWORD).status_code)
        for identifier in ("inst-1001", "INST-1001", "inst-1001"):
            statuses.append(attempt(client, identifier, WRONG_PASSWORD).status_code)

        assert statuses == [401, 401, 401, 401, 401, 429]


class TestLoginAudit:
    def test_success_failure_and_block_are_audited_with_ip_and_result(self) -> None:
        user = make_user()
        client = APIClient()
        extra = {
            "HTTP_X_FORWARDED_FOR": "192.0.2.9",
            "HTTP_USER_AGENT": "pytest-agent",
        }

        attempt(client, "INST-1001", WRONG_PASSWORD, **extra)  # FAILURE
        attempt(client, "INST-1001", CORRECT_PASSWORD, **extra)  # SUCCESS
        for _ in range(4):
            attempt(client, "INST-1001", WRONG_PASSWORD, **extra)  # 4 FAILURE
        blocked = attempt(client, "INST-1001", CORRECT_PASSWORD, **extra)
        assert blocked.status_code == 429

        successes = AuditLog.objects.filter(
            action="LOGIN", result=AuditLog.Result.SUCCESS
        )
        failures = AuditLog.objects.filter(
            action="LOGIN", result=AuditLog.Result.FAILURE
        )
        denials = AuditLog.objects.filter(
            action="LOGIN", result=AuditLog.Result.DENIED
        )

        assert successes.count() == 1
        assert successes.first().actor_id == user.id
        assert failures.count() == 5
        assert denials.count() == 1
        assert "Límite de intentos" in denials.first().reason

        for entry in AuditLog.objects.filter(action="LOGIN"):
            assert entry.details["identifier"] == "inst-1001"
            assert entry.ip_address == "192.0.2.9"
            assert entry.user_agent == "pytest-agent"
            assert entry.request_id

    def test_attempts_and_audit_never_store_the_password(self) -> None:
        make_user()
        client = APIClient()
        attempt(client, "INST-1001", WRONG_PASSWORD)
        attempt(client, "INST-1001", CORRECT_PASSWORD)

        assert LoginAttempt.objects.count() == 2
        for row in LoginAttempt.objects.all():
            values = [
                str(getattr(row, field.name) or "")
                for field in LoginAttempt._meta.fields
            ]
            for value in values:
                assert CORRECT_PASSWORD not in value
                assert WRONG_PASSWORD not in value

        for entry in AuditLog.objects.all():
            blob = str(entry.details) + (entry.reason or "") + (entry.user_agent or "")
            assert CORRECT_PASSWORD not in blob
            assert WRONG_PASSWORD not in blob

    def test_attempt_registry_keeps_identifier_and_result(self) -> None:
        make_user()
        client = APIClient()
        attempt(client, "INST-1001", WRONG_PASSWORD, HTTP_X_FORWARDED_FOR="203.0.113.5")
        attempt(client, "INST-1001", CORRECT_PASSWORD)

        failed, ok = LoginAttempt.objects.order_by("id")
        assert failed.identifier == "inst-1001"  # clave normalizada
        assert failed.successful is False
        assert failed.ip_address == "203.0.113.5"
        assert ok.successful is True

    def test_audit_unavailable_answers_503_and_issues_no_session(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        make_user()

        def broken_save(*args, **kwargs):
            raise IntegrityError("simulated audit write failure")

        monkeypatch.setattr(AuditLog, "save", broken_save)

        client = APIClient()
        response = attempt(client, "INST-1001", CORRECT_PASSWORD)

        assert response.status_code == 503
        assert response.json()["error"]["code"] == "AUDIT_UNAVAILABLE"
        # Falla cerrado: la transacción se revierte por completo.
        assert RefreshTokenRecord.objects.count() == 0
        assert LoginAttempt.objects.count() == 0
