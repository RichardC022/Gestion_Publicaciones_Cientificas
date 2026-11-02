"""Alta de cuentas sin Django Admin: servicio y comandos (D-31)."""

from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import CommandError, call_command
from rest_framework.test import APIClient

from apps.users.models import ReviewerProfile, User, UserRole
from apps.users.services.provisioning import ProvisioningError, provision_user

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def roles(db) -> None:
    call_command("seed_roles", verbosity=0)


def create(**overrides) -> str:
    out = StringIO()
    options = {"first_name": "Ana", "last_name": "Autora", "email": "ana@unl.edu.ec", "roles": ["AUTHOR"], **overrides}
    call_command("create_user", options.pop("identifier", "ana"), stdout=out, **options)
    return out.getvalue()


def login(identifier: str, password: str):
    return APIClient().post("/api/auth/login/", {"identifier": identifier, "password": password}, format="json")


class TestProvisionUser:
    def test_creates_the_account_with_a_generated_password_that_logs_in(self) -> None:
        result = provision_user(institutional_id="ana", first_name="Ana", last_name="Autora",
                                email="ana@unl.edu.ec", roles=["author"])

        assert result.created and result.password and result.roles_added == ("AUTHOR",)
        assert login("ana", result.password).status_code == 200

    def test_repeating_it_neither_duplicates_nor_changes_the_password(self) -> None:
        first = provision_user(institutional_id="ana", first_name="Ana", last_name="A",
                               email="ana@unl.edu.ec", roles=["AUTHOR"])
        again = provision_user(institutional_id="ana", first_name="Ana", last_name="A",
                               email="ana@unl.edu.ec", roles=["AUTHOR", "EDITOR"])

        assert not again.created and again.password is None and again.roles_added == ("EDITOR",)
        assert User.objects.count() == 1
        assert UserRole.objects.filter(user=first.user, is_active=True).count() == 2
        assert login("ana", first.password).status_code == 200

    def test_a_reviewer_gets_a_profile_with_the_areas(self) -> None:
        result = provision_user(institutional_id="rosa", first_name="Rosa", last_name="R",
                                email="rosa@unl.edu.ec", roles=["REVIEWER"], expertise_areas=["Agronomía"])

        profile = ReviewerProfile.objects.get(user=result.user)
        assert profile.expertise_areas == ["Agronomía"] and profile.is_available

    @pytest.mark.parametrize("bad", [["JEFE"], []])
    def test_rejects_unknown_or_missing_roles(self, bad) -> None:
        with pytest.raises(ProvisioningError):
            provision_user(institutional_id="x", first_name="X", last_name="X", email="x@unl.edu.ec", roles=bad)
        assert not User.objects.exists()

    def test_rejects_an_email_that_belongs_to_someone_else(self) -> None:
        provision_user(institutional_id="ana", first_name="Ana", last_name="A", email="ana@unl.edu.ec", roles=["AUTHOR"])

        with pytest.raises(ProvisioningError, match="ya pertenece"):
            provision_user(institutional_id="otra", first_name="O", last_name="O",
                           email="ANA@unl.edu.ec", roles=["AUTHOR"])

    def test_fails_clearly_when_the_roles_were_never_seeded(self) -> None:
        from apps.users.models import Role

        UserRole.objects.all().delete()
        Role.objects.all().delete()
        with pytest.raises(ProvisioningError, match="seed_roles"):
            provision_user(institutional_id="x", first_name="X", last_name="X", email="x@unl.edu.ec", roles=["AUTHOR"])


class TestCreateUserCommand:
    def test_prints_the_generated_password_once_and_it_works(self) -> None:
        text = create()

        assert "Cuenta creada: ana" in text and "Contraseña inicial" in text
        password = text.rsplit(": ", 1)[1].strip()
        assert login("ana", password).status_code == 200

    def test_with_an_explicit_password_it_does_not_print_it(self) -> None:
        text = create(password="una-clave-larga-123")

        assert "Contraseña inicial" not in text
        assert login("ana", "una-clave-larga-123").status_code == 200

    def test_reports_a_domain_error_as_a_command_error(self) -> None:
        with pytest.raises(CommandError, match="Roles no válidos"):
            create(roles=["JEFE"])


class TestSeedDevUsers:
    def test_refuses_to_run_without_the_guard(self, settings, monkeypatch) -> None:
        settings.DEBUG = False
        monkeypatch.delenv("ALLOW_DEV_USERS", raising=False)

        with pytest.raises(CommandError, match="ALLOW_DEV_USERS=1"):
            call_command("seed_dev_users", stdout=StringIO())
        assert not User.objects.exists()

    def test_creates_one_account_per_role_that_can_log_in(self, settings, monkeypatch) -> None:
        settings.DEBUG = False
        monkeypatch.setenv("ALLOW_DEV_USERS", "1")
        call_command("seed_dev_users", stdout=StringIO())

        for identifier, role in (("autor", "AUTHOR"), ("editor", "EDITOR"), ("revisor", "REVIEWER"), ("admin", "ADMIN")):
            body = login(identifier, "Gpc-dev-2026").json()
            assert "access" in body and role in APIClient().get(
                "/api/auth/me/", HTTP_AUTHORIZATION=f"Bearer {body['access']}").json()["roles"]
        multi = login("autor.revisor", "Gpc-dev-2026").json()["access"]
        roles = APIClient().get("/api/auth/me/", HTTP_AUTHORIZATION=f"Bearer {multi}").json()["roles"]
        assert set(roles) == {"AUTHOR", "REVIEWER"}
        assert ReviewerProfile.objects.filter(user__institutional_id="revisor").exists()

    def test_repeating_it_resets_the_password_without_duplicating(self, monkeypatch) -> None:
        monkeypatch.setenv("ALLOW_DEV_USERS", "1")
        call_command("seed_dev_users", stdout=StringIO())
        call_command("seed_dev_users", "--password", "Otra-clave-9", stdout=StringIO())

        assert User.objects.count() == 7
        assert login("autor", "Gpc-dev-2026").status_code == 401
        assert login("autor", "Otra-clave-9").status_code == 200


class TestSupportOperationsDocumentedInTheRunbook:
    """Las dos órdenes de `manage.py shell -c` del runbook §11.2 hacen lo que dicen."""

    def test_deactivating_an_account_blocks_the_login(self) -> None:
        result = provision_user(institutional_id="ana", first_name="Ana", last_name="A",
                                email="ana@unl.edu.ec", roles=["AUTHOR"])
        assert login("ana", result.password).status_code == 200

        User.objects.filter(institutional_id="ana").update(is_active=False)

        assert login("ana", result.password).status_code == 401

    def test_retiring_a_role_removes_it_from_the_next_request_and_keeps_the_history(self) -> None:
        from django.utils import timezone

        result = provision_user(institutional_id="ana", first_name="Ana", last_name="A",
                                email="ana@unl.edu.ec", roles=["AUTHOR", "EDITOR"])
        UserRole.objects.filter(
            user__institutional_id="ana", role__code="EDITOR", is_active=True
        ).update(is_active=False, revoked_at=timezone.now())

        token = login("ana", result.password).json()["access"]
        me = APIClient().get("/api/auth/me/", HTTP_AUTHORIZATION=f"Bearer {token}").json()
        assert me["roles"] == ["AUTHOR"]
        assert UserRole.objects.filter(user=result.user, role__code="EDITOR", is_active=False).count() == 1
