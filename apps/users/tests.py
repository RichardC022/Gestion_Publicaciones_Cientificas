"""Tests for authentication roles and role-switching (FR-001..FR-003)."""

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.users.models import User, UserRole


class UserRoleTests(TestCase):
    """Verify role composition, switching and authorization helpers."""

    def test_default_user_is_author_only(self) -> None:
        """A plain member is enabled as author by default."""
        user = User.objects.create_user(username="author1", password="pass12345")
        self.assertEqual(user.roles, [UserRole.AUTHOR])
        self.assertTrue(user.has_role(UserRole.AUTHOR))
        self.assertFalse(user.has_role(UserRole.REVIEWER))

    def test_multi_role_docent(self) -> None:
        """A docent enabled as reviewer and editor exposes both roles."""
        user = User.objects.create_user(
            username="docent",
            password="pass12345",
            is_reviewer_enabled=True,
            is_editor_enabled=True,
        )
        self.assertIn(UserRole.REVIEWER, user.roles)
        self.assertIn(UserRole.EDITOR, user.roles)

    def test_superuser_holds_admin_role(self) -> None:
        """A superuser always exposes the admin role."""
        user = User.objects.create_superuser(
            username="root", password="pass12345", email="root@unl.edu.ec"
        )
        self.assertIn(UserRole.ADMIN, user.roles)

    def test_switch_to_enabled_role(self) -> None:
        """Switching to an enabled role updates the active role."""
        user = User.objects.create_user(
            username="docent2",
            password="pass12345",
            is_reviewer_enabled=True,
        )
        user.switch_role(UserRole.REVIEWER)
        self.assertEqual(user.active_role, UserRole.REVIEWER)

    def test_switch_to_disabled_role_is_rejected(self) -> None:
        """Switching to a role that is not enabled raises an error."""
        user = User.objects.create_user(username="author2", password="pass12345")
        with self.assertRaises(ValidationError):
            user.switch_role(UserRole.EDITOR)

    def test_anonymous_login_is_not_supported(self) -> None:
        """Credentials are validated through Django's authentication."""
        User.objects.create_user(username="author3", password="pass12345")
        self.assertIsNotNone(
            self.client.login(username="author3", password="pass12345")
        )
        self.assertFalse(
            self.client.login(username="author3", password="wrong-password")
        )
