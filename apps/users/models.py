"""Custom user model and role helpers for ScientificPub UNL.

The domain needs institutional users that may hold one or several roles
(Author, Reviewer, Editor, Administrator). Authentication reuses Django's
``AbstractUser`` while authorization is driven by explicit role flags and a
single ``active_role`` used for role-switching flows (RF-12).
"""

from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models


class UserRole(models.TextChoices):
    """Enumerates the institutional roles available in the platform."""

    AUTHOR = "author", "Author"
    REVIEWER = "reviewer", "Reviewer"
    EDITOR = "editor", "Editor"
    ADMIN = "admin", "Administrator"


class User(AbstractUser):
    """Institutional user capable of performing one or several roles.

    Attributes:
        document_id: Optional institutional identification number.
        active_role: Role currently selected by the user for the session.
        is_reviewer_enabled: Marks a member who can act as a peer reviewer.
        is_author_enabled: Marks a member who can submit manuscripts.
        is_editor_enabled: Marks a member who can manage the editorial flow.
        is_admin_enabled: Marks a member who can administer the platform.
    """

    document_id = models.CharField(
        max_length=20,
        unique=True,
        null=True,
        blank=True,
        verbose_name="institutional document",
    )
    active_role = models.CharField(
        max_length=20,
        choices=UserRole.choices,
        default=UserRole.AUTHOR,
        verbose_name="active role",
    )
    is_author_enabled = models.BooleanField(default=True)
    is_reviewer_enabled = models.BooleanField(default=False)
    is_editor_enabled = models.BooleanField(default=False)
    is_admin_enabled = models.BooleanField(default=False)

    class Meta:
        """Metadata and indexes for the user model."""

        db_table = "users_user"
        verbose_name = "user"
        verbose_name_plural = "users"
        indexes = [
            models.Index(fields=["active_role"], name="users_role_idx"),
            models.Index(fields=["is_reviewer_enabled"], name="users_reviewer_idx"),
        ]

    @property
    def roles(self) -> list[str]:
        """Return the list of role identifiers enabled for this user."""
        enabled = []
        if self.is_author_enabled:
            enabled.append(UserRole.AUTHOR)
        if self.is_reviewer_enabled:
            enabled.append(UserRole.REVIEWER)
        if self.is_editor_enabled:
            enabled.append(UserRole.EDITOR)
        if self.is_admin_enabled or self.is_superuser:
            enabled.append(UserRole.ADMIN)
        return enabled

    @property
    def display_name(self) -> str:
        """Return the full name or username, preferring the full name."""
        return self.get_full_name() or self.username

    def can_switch_to(self, role: str) -> bool:
        """Return whether the user is allowed to adopt ``role``."""
        return role in self.roles

    def switch_role(self, role: str) -> None:
        """Set the active role after validating it is enabled.

        Args:
            role: Identifier of the role (``UserRole`` value) to activate.

        Raises:
            ValidationError: If the role is not enabled for the user.
        """
        if not self.can_switch_to(role):
            raise ValidationError(f"Role '{role}' is not enabled for this user.")
        self.active_role = role

    def has_role(self, role: str) -> bool:
        """Return whether the user currently holds ``role``."""
        return role in self.roles
