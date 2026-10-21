"""Shared models: audit base class and the immutable audit log.

Every business model must inherit from :class:`BaseModel` to guarantee a unique
identifier and audit timestamps, as mandated by the project constitution. The
:class:`AuditLog` records critical actions and is protected against tampering.
"""

from django.conf import settings
from django.db import models


class BaseModel(models.Model):
    """Abstract model providing identity and audit timestamps.

    Attributes:
        created_at: Timestamp automatically set when the row is first created.
        updated_at: Timestamp automatically refreshed on every save.
    """

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        """Metadata for the abstract base model."""

        abstract = True
        ordering = ["-created_at"]


class AuditLog(models.Model):
    """Immutable record of a critical action performed on the platform.

    Records are append-only: updates and deletions are rejected so the audit
    trail cannot be altered by ordinary users (RF-08, RNF-08).

    Attributes:
        actor: User who triggered the action.
        action: Short identifier of the action (e.g. ``manuscript.status_changed``).
        entity_type: Label of the affected entity (e.g. ``Manuscript``).
        entity_id: Identifier of the affected entity.
        description: Human-readable summary of the event.
        metadata: Optional structured payload with additional context.
        created_at: Timestamp when the event was recorded.
    """

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    action = models.CharField(max_length=100, db_index=True)
    entity_type = models.CharField(max_length=100)
    entity_id = models.CharField(max_length=64, blank=True)
    description = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        """Metadata and indexes for the audit log model."""

        db_table = "core_audit_log"
        verbose_name = "audit log"
        verbose_name_plural = "audit logs"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["entity_type", "entity_id"], name="audit_entity_idx"),
            models.Index(fields=["action", "created_at"], name="audit_action_idx"),
        ]
        default_permissions = ("add", "view")

    def __str__(self) -> str:
        """Return a label identifying the audit entry."""
        return f"{self.action} on {self.entity_type}#{self.entity_id}"

    def save(self, *args, **kwargs) -> None:
        """Persist the entry, forbidding updates of existing rows.

        Raises:
            ValueError: If an attempt is made to modify a stored audit entry.
        """
        if self.pk is not None:
            raise ValueError("AuditLog entries are immutable and cannot be updated.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs) -> None:
        """Block deletion to preserve the audit trail.

        Raises:
            ValueError: Always, since audit entries cannot be deleted.
        """
        raise ValueError("AuditLog entries are immutable and cannot be deleted.")
