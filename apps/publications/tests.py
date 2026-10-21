"""Tests for manuscript lifecycle, versioning and authorship (FR-004, FR-005)."""

from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase

from apps.publications.models import (
    Author,
    Manuscript,
    ManuscriptStatus,
    ManuscriptVersion,
    ResearchArea,
)
from apps.users.models import User


class ManuscriptLifecycleTests(TestCase):
    """Verify editable states and version-upload rules."""

    def setUp(self) -> None:
        """Create an author and a base manuscript."""
        self.author = User.objects.create_user(username="author", password="pass12345")
        self.area = ResearchArea.objects.create(name="Computing", code="COMP")
        self.manuscript = Manuscript.objects.create(
            title="A study",
            abstract="Abstract",
            keywords="a,b",
            author=self.author,
            research_area=self.area,
        )

    def test_default_status_is_draft_and_editable(self) -> None:
        """A new manuscript starts as draft and is editable."""
        self.assertEqual(self.manuscript.status, ManuscriptStatus.DRAFT)
        self.assertTrue(self.manuscript.is_editable)

    def test_received_manuscript_is_not_editable(self) -> None:
        """A submitted manuscript cannot be edited (RF-21)."""
        self.manuscript.status = ManuscriptStatus.RECEIVED
        self.assertFalse(self.manuscript.is_editable)

    def test_version_only_allowed_when_changes_requested(self) -> None:
        """New versions are only accepted in 'Requires Correcciones' (RF-06)."""
        self.assertFalse(self.manuscript.can_accept_new_version())
        self.manuscript.status = ManuscriptStatus.REQUIRES_CHANGES
        self.assertTrue(self.manuscript.can_accept_new_version())

    def test_current_version_returns_latest(self) -> None:
        """``current_version`` returns the highest version number."""
        ManuscriptVersion.objects.create(
            manuscript=self.manuscript, version_number=1, file="a.pdf"
        )
        ManuscriptVersion.objects.create(
            manuscript=self.manuscript, version_number=2, file="b.pdf"
        )
        self.assertEqual(self.manuscript.current_version().version_number, 2)

    def test_version_number_is_unique_per_manuscript(self) -> None:
        """Duplicated version numbers are rejected (RNF-05)."""
        ManuscriptVersion.objects.create(
            manuscript=self.manuscript, version_number=1, file="a.pdf"
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            ManuscriptVersion.objects.create(
                manuscript=self.manuscript, version_number=1, file="b.pdf"
            )


class AuthorshipTests(TestCase):
    """Verify authorship metadata constraints."""

    def setUp(self) -> None:
        """Create a manuscript to attach authors to."""
        author = User.objects.create_user(username="author", password="pass12345")
        area = ResearchArea.objects.create(name="Computing", code="COMP")
        self.manuscript = Manuscript.objects.create(
            title="A study",
            abstract="Abstract",
            keywords="a,b",
            author=author,
            research_area=area,
        )

    def test_author_order_is_unique_per_manuscript(self) -> None:
        """Two authors cannot share the same position in the list."""
        Author.objects.create(manuscript=self.manuscript, full_name="A", order=1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Author.objects.create(manuscript=self.manuscript, full_name="B", order=1)

    def test_manuscript_cannot_be_deleted_while_versions_exist(self) -> None:
        """Protected relations block accidental cascading deletes (FR-012)."""
        ManuscriptVersion.objects.create(
            manuscript=self.manuscript, version_number=1, file="a.pdf"
        )
        with self.assertRaises(ProtectedError), transaction.atomic():
            self.manuscript.delete()
