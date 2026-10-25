"""Tests for users, roles, profiles and access attempts (TSK-17).

Covers the acceptance criteria: the seeded roles are exactly AUTHOR,
REVIEWER, EDITOR and ADMIN and the command is idempotent; a user keeps the
history of revoked roles and cannot hold two active rows of the same role;
``is_active=false`` prevents authentication and a deactivated account with
history is never physically deleted.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import authenticate
from django.db import IntegrityError

from apps.users.models import LoginAttempt, Role, User, UserRole

EXPECTED_ROLES = {"AUTHOR", "REVIEWER", "EDITOR", "ADMIN"}


def make_user(**overrides):
    """Create an institutional account with defaults."""
    payload = {
        "institutional_id": "INST-0001",
        "username": "a.lopez",
        "email": "a.lopez@unl.edu.ec",
        "first_name": "Ana",
        "last_name": "López",
    }
    payload.update(overrides)
    return User.objects.create_user(password="institucional-123", **payload)


@pytest.fixture
def seeded_roles(django_db_setup) -> None:
    """Seed the role catalog once per test."""
    from django.core.management import call_command

    call_command("seed_roles", verbosity=0)


def call_seed() -> None:
    from django.core.management import call_command

    call_command("seed_roles", verbosity=0)


@pytest.mark.django_db
class TestSeedRoles:
    def test_seeded_roles_are_exactly_the_institutional_catalog(self) -> None:
        call_seed()

        codes = set(Role.objects.values_list("code", flat=True))
        assert codes == EXPECTED_ROLES
        assert Role.objects.count() == 4

    def test_seed_command_is_idempotent(self) -> None:
        call_seed()
        call_seed()
        call_seed()

        assert Role.objects.count() == 4
        assert User.objects.count() == 0  # el comando no toca cuentas


@pytest.mark.django_db
class TestUserRoleHistory:
    def test_user_cannot_hold_two_active_rows_of_the_same_role(self) -> None:
        call_seed()
        user = make_user()
        role = Role.objects.get(code="AUTHOR")

        UserRole.objects.create(user=user, role=role)

        with pytest.raises(IntegrityError):
            UserRole.objects.create(user=user, role=role)

    def test_user_keeps_history_of_revoked_roles_and_can_be_reassigned(self) -> None:
        call_seed()
        user = make_user()
        role = Role.objects.get(code="REVIEWER")

        revoked = UserRole.objects.create(user=user, role=role)
        revoked.is_active = False
        revoked.save(update_fields=["is_active"])

        # La reasignación crea una fila nueva; la retirada se conserva.
        active = UserRole.objects.create(user=user, role=role)
        assert active.is_active is True

        assignments = UserRole.objects.filter(user=user, role=role)
        assert assignments.count() == 2
        assert assignments.filter(is_active=True).count() == 1
        assert assignments.filter(is_active=False).count() == 1

    def test_user_can_hold_multiple_simultaneous_active_roles(self) -> None:
        call_seed()
        user = make_user()

        for code in ("AUTHOR", "REVIEWER"):
            UserRole.objects.create(user=user, role=Role.objects.get(code=code))

        active_codes = set(
            UserRole.objects.filter(user=user, is_active=True).values_list(
                "role__code", flat=True
            )
        )
        assert active_codes == {"AUTHOR", "REVIEWER"}


@pytest.mark.django_db
class TestInstitutionalAccount:
    def test_inactive_account_cannot_authenticate(self) -> None:
        user = make_user(username="b.martinez", institutional_id="INST-0002")
        assert authenticate(username="b.martinez", password="institucional-123") == user

        user.is_active = False
        user.save(update_fields=["is_active"])

        assert authenticate(username="b.martinez", password="institucional-123") is None

    def test_deactivated_account_with_history_is_never_deleted(self) -> None:
        call_seed()
        user = make_user(username="c.perez", institutional_id="INST-0003")
        UserRole.objects.create(user=user, role=Role.objects.get(code="EDITOR"))

        user.is_active = False
        user.save(update_fields=["is_active"])

        # La cuenta se desactiva, no se elimina: el historial permanece.
        assert User.objects.filter(username="c.perez").exists()
        assert UserRole.objects.filter(user=user, is_active=True).count() == 1

    def test_email_is_unique_case_insensitive(self) -> None:
        make_user(email="ana@unl.edu.ec")
        with pytest.raises(IntegrityError):
            make_user(
                username="d.duplicado",
                institutional_id="INST-0004",
                email="ANA@UNL.EDU.EC",
            )

    def test_roles_are_protected_against_cascade_deletion(self) -> None:
        call_seed()
        user = make_user(username="e.protegido", institutional_id="INST-0005")
        UserRole.objects.create(user=user, role=Role.objects.get(code="ADMIN"))

        with pytest.raises(IntegrityError):
            user.delete()


@pytest.mark.django_db
class TestReviewerProfileAndLoginAttempts:
    def test_reviewer_profile_defaults(self) -> None:
        from apps.users.models import ReviewerProfile

        call_seed()
        user = make_user(username="f.revisor", institutional_id="INST-0006")
        UserRole.objects.create(user=user, role=Role.objects.get(code="REVIEWER"))

        profile = ReviewerProfile.objects.create(user=user)

        assert profile.is_available is True
        assert profile.max_active_assignments == 3
        assert profile.expertise_areas == []
        assert ReviewerProfile.objects.filter(user=user).count() == 1

    def test_login_attempt_never_stores_passwords(self) -> None:
        attempt = LoginAttempt.objects.create(
            identifier="b.martinez",
            successful=False,
            ip_address="192.0.2.10",
        )

        assert attempt.successful is False
        assert attempt.pk is not None
        # El modelo no tiene ningún campo de contraseña.
        assert not any(
            "password" in field.name
            for field in LoginAttempt._meta.get_fields()
        )
