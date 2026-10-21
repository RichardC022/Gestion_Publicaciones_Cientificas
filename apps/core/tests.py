"""Smoke tests for the shared core app (audit trail immutability)."""

from django.test import TestCase

from apps.core.models import AuditLog
from apps.users.models import User


class AuditLogImmutabilityTests(TestCase):
    """Verify that audit entries are append-only."""

    def setUp(self) -> None:
        """Create an actor and a stored audit entry."""
        self.actor = User.objects.create_user(username="admin", password="pass12345")
        self.entry = AuditLog.objects.create(
            actor=self.actor,
            action="manuscript.status_changed",
            entity_type="Manuscript",
            entity_id="1",
            description="Status changed to received.",
        )

    def test_audit_entry_is_created(self) -> None:
        """A new audit entry is persisted with its payload."""
        self.assertEqual(AuditLog.objects.count(), 1)
        self.assertEqual(self.entry.entity_type, "Manuscript")

    def test_audit_entry_cannot_be_updated(self) -> None:
        """Updating a stored entry raises ``ValueError``."""
        self.entry.description = "tampered"
        with self.assertRaises(ValueError):
            self.entry.save()

    def test_audit_entry_cannot_be_deleted(self) -> None:
        """Deleting a stored entry raises ``ValueError``."""
        with self.assertRaises(ValueError):
            self.entry.delete()
