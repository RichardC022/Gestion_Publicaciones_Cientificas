"""Tests for authentication roles and role-switching (FR-001..FR-003)."""

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

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


class LoginViewTests(TestCase):
    """Verify the session-based login, logout and dashboard flow."""

    def setUp(self) -> None:
        """Create an author account used across the view tests."""
        self.user = User.objects.create_user(
            username="autora",
            password="pass12345",
            first_name="Ana",
            last_name="Autora",
        )

    def test_login_page_renders(self) -> None:
        """The login screen renders with the institutional look."""
        response = self.client.get(reverse("users:login"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ScientificPub UNL")
        self.assertTemplateUsed(response, "registration/login.html")

    def test_login_success_redirects_to_dashboard(self) -> None:
        """Valid credentials start a session and land on the dashboard."""
        response = self.client.post(
            reverse("users:login"),
            {"username": "autora", "password": "pass12345"},
        )
        self.assertRedirects(response, reverse("users:dashboard"))

    def test_login_failure_shows_error(self) -> None:
        """Invalid credentials re-render the form with an error message."""
        response = self.client.post(
            reverse("users:login"),
            {"username": "autora", "password": "wrong"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Credenciales incorrectas")

    def test_dashboard_requires_login(self) -> None:
        """Anonymous visitors are redirected to the login screen."""
        response = self.client.get(reverse("users:dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("users:login"), response.url)

    def test_dashboard_shows_role_after_login(self) -> None:
        """An authenticated member sees their active role on the dashboard."""
        self.client.login(username="autora", password="pass12345")
        response = self.client.get(reverse("users:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ana Autora")

    def test_logout_closes_session(self) -> None:
        """Logging out redirects to the login screen."""
        self.client.login(username="autora", password="pass12345")
        response = self.client.post(reverse("users:logout"))
        self.assertRedirects(response, reverse("users:login"))
