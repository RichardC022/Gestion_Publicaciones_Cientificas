"""Domain models for institutional users, roles and access attempts.

The account registry follows the implementation plan (sections 1.3-1.7):

* ``User`` is the institutional account (UUID PK, institutional id, unique
  case-insensitive email). Accounts are never physically deleted: they are
  disabled through ``is_active`` to preserve evaluation and audit history.
* ``Role`` is the fixed catalog: ``AUTHOR``, ``REVIEWER``, ``EDITOR`` and
  ``ADMIN``.
* ``UserRole`` keeps the historical role assignments. A user may hold
  several simultaneous active roles and keeps the history of revoked ones;
  the partial unique index allows at most one ACTIVE row per
  (user, role).
* ``ReviewerProfile`` declares expertise areas (GIN indexed) and the
  assignment capacity of a reviewer.
* ``LoginAttempt`` records failed/successful login attempts without ever
  storing passwords (consumed by the rate limit of TSK-20).
* ``RefreshToken`` is the server-side registry of refresh tokens (plan
  section 6.1): single-use rotation, logout revocation and idle-window
  enforcement. SimpleJWT only signs the tokens; this table decides whether
  a refresh is still valid.
"""

from __future__ import annotations

import uuid

from django.contrib.auth.models import AbstractUser
from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.indexes import GinIndex
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower
from django.utils import timezone


class User(AbstractUser):
    """Institutional account."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    institutional_id = models.CharField(max_length=50, unique=True)
    # El plan exige first_name/last_name NOT NULL (no opcionales).
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)

    class Meta:
        db_table = "users_user"
        constraints = [
            models.UniqueConstraint(
                Lower("email"),
                name="uq_user_email_lower",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.get_full_name()} <{self.email}>".strip()


class Role(models.Model):
    """Fixed role catalog."""

    class Code(models.TextChoices):
        AUTHOR = "AUTHOR", "Autor"
        REVIEWER = "REVIEWER", "Revisor"
        EDITOR = "EDITOR", "Editor"
        ADMIN = "ADMIN", "Administrador"

    id = models.SmallAutoField(primary_key=True)
    code = models.CharField(max_length=20, unique=True, choices=Code.choices)
    name = models.CharField(max_length=50)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "users_role"
        ordering = ("id",)

    def __str__(self) -> str:
        return self.name


class UserRole(models.Model):
    """Historical role assignment.

    One ACTIVE row per (user, role) is enforced by a partial unique index;
    revoked rows stay forever so the account keeps its role history.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    user = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="role_assignments",
    )
    role = models.ForeignKey(
        Role,
        on_delete=models.PROTECT,
        related_name="user_assignments",
    )
    is_active = models.BooleanField(default=True)
    assigned_at = models.DateTimeField(auto_now_add=True)
    assigned_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="role_assignments_granted",
    )
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="role_assignments_revoked",
    )

    class Meta:
        db_table = "users_user_role"
        constraints = [
            models.UniqueConstraint(
                fields=("user", "role"),
                condition=Q(is_active=True),
                name="uq_user_role_active",
            ),
        ]
        indexes = [
            models.Index(
                fields=("user", "role", "is_active"),
                name="idx_user_role_lookup",
            ),
        ]

    def __str__(self) -> str:
        state = "activa" if self.is_active else "retirada"
        return f"{self.user_id} · {self.role_id} ({state})"


class ReviewerProfile(models.Model):
    """Expertise areas and availability of a reviewer."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    user = models.OneToOneField(
        User,
        on_delete=models.PROTECT,
        related_name="reviewer_profile",
    )
    expertise_areas = ArrayField(
        models.CharField(max_length=120),
        default=list,
        blank=True,
    )
    is_available = models.BooleanField(default=True)
    max_active_assignments = models.PositiveSmallIntegerField(default=3)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "users_reviewer_profile"
        indexes = [
            GinIndex(
                fields=("expertise_areas",),
                name="idx_reviewer_expertise_areas",
            ),
        ]

    def __str__(self) -> str:
        return f"Perfil de revisor de {self.user_id}"


class LoginAttempt(models.Model):
    """Login attempt registry for the brute-force rate limit (TSK-20).

    The attempted identifier is preserved; passwords are never stored.
    """

    id = models.BigAutoField(primary_key=True)
    identifier = models.CharField(max_length=254)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    successful = models.BooleanField()
    attempted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "users_login_attempt"
        indexes = [
            models.Index(
                fields=("identifier", "-attempted_at"),
                name="idx_login_identifier_time",
            ),
        ]

    def __str__(self) -> str:
        result = "éxito" if self.successful else "fallo"
        return f"{self.identifier} ({result})"


class RevocationReason(models.TextChoices):
    """Why a refresh token stopped being valid."""

    LOGOUT = "LOGOUT", "Cierre de sesión"
    ROTATED = "ROTATED", "Rotado por un refresh nuevo"
    REUSE = "REUSE", "Reutilización de un token ya consumido"
    IDLE_TIMEOUT = "IDLE_TIMEOUT", "Inactividad institucional"
    ACCOUNT_DISABLED = "ACCOUNT_DISABLED", "Cuenta deshabilitada"


class RefreshToken(models.Model):
    """Server-side registry of refresh tokens (plan section 6.1).

    Every issued refresh token is a row here; the signed JWT is only the
    transport. The token is single-use: when it rotates, the row is revoked
    with ``replaced_by_jti`` pointing to its replacement, so reusing a
    consumed token is detected and the replacement chain dies with it.
    ``last_used_at`` feeds the institutional idle window.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    user = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="refresh_tokens",
    )
    # `jti` del JWT firmado: une el token transportado con esta fila.
    jti = models.CharField(max_length=64, unique=True)
    issued_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    last_used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_reason = models.CharField(
        max_length=20,
        choices=RevocationReason.choices,
        null=True,
        blank=True,
    )
    replaced_by_jti = models.CharField(max_length=64, null=True, blank=True)

    class Meta:
        db_table = "users_refresh_token"
        ordering = ("-issued_at",)
        indexes = [
            models.Index(
                fields=("user", "-issued_at"),
                name="idx_refresh_user_issued",
            ),
            models.Index(
                fields=("expires_at",),
                name="idx_refresh_expires",
            ),
        ]

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None

    def revoke(
        self,
        *,
        reason: str,
        replaced_by_jti: str | None = None,
        last_used_at=None,
    ) -> "RefreshToken":
        """Revoke this token; idempotent (the first reason is preserved)."""
        if self.revoked_at is not None:
            return self
        self.revoked_at = timezone.now()
        self.revoked_reason = reason
        if replaced_by_jti is not None:
            self.replaced_by_jti = replaced_by_jti
        if last_used_at is not None:
            self.last_used_at = last_used_at
        self.save(
            update_fields=(
                "revoked_at",
                "revoked_reason",
                "replaced_by_jti",
                "last_used_at",
            )
        )
        return self

    def __str__(self) -> str:
        state = "revocado" if self.revoked_at else "vigente"
        return f"{self.jti} · {self.user_id} ({state})"
