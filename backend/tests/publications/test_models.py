"""Tests for manuscript, author, version, round and event models (TSK-30).

Covers the acceptance criteria: ``code`` is unique with the
``GPC-AAAA-######`` format; ``(manuscript, version_number)`` and
``(manuscript, round_number)`` are unique; the logical withdrawal keeps
``status`` and requires ``is_active=false`` together with ``withdrawn_at``;
and ``metadata_snapshot`` plus the hashes are mandatory in every version
and never overwritten.
"""

from __future__ import annotations

import re

import pytest
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.utils import timezone

from apps.publications.models import (
    CorrectionRound,
    Manuscript,
    ManuscriptAuthor,
    ManuscriptVersion,
    StatusEvent,
)
from tests.factories import ManuscriptFactory, ManuscriptVersionFactory, UserFactory

CODE_FORMAT = re.compile(r"^GPC-\d{4}-\d{6}$")
SHA = "a" * 64


def make_manuscript(owner, **overrides) -> Manuscript:
    """Create a draft manuscript with the factory defaults."""
    return ManuscriptFactory(created_by=owner, **overrides)


def make_version(manuscript, submitted_by, **overrides) -> ManuscriptVersion:
    """Create a formal version with valid hashes and snapshot."""
    return ManuscriptVersionFactory(
        manuscript=manuscript, submitted_by=submitted_by, **overrides
    )


@pytest.fixture
def owner(db):
    return UserFactory()


@pytest.mark.django_db
class TestManuscriptCode:
    def test_code_follows_the_institutional_format(self, owner) -> None:
        manuscript = make_manuscript(owner)

        assert CODE_FORMAT.match(manuscript.code)
        assert manuscript.code.startswith(f"GPC-{timezone.localdate().year}-")

    def test_codes_are_consecutive_and_unique(self, owner) -> None:
        first = make_manuscript(owner)
        second = make_manuscript(owner)

        assert first.code != second.code
        assert int(second.code[-6:]) == int(first.code[-6:]) + 1

    def test_code_is_not_reused_after_a_rollback(self, owner) -> None:
        discarded = []
        with pytest.raises(RuntimeError), transaction.atomic():
            discarded.append(make_manuscript(owner).code)
            raise RuntimeError("rollback")

        assert make_manuscript(owner).code != discarded[0]
        assert int(make_manuscript(owner).code[-6:]) > int(discarded[0][-6:])

    def test_database_rejects_a_duplicate_code(self, owner) -> None:
        manuscript = make_manuscript(owner)

        with pytest.raises(IntegrityError), transaction.atomic():
            Manuscript.objects.bulk_create(
                [
                    Manuscript(
                        code=manuscript.code,
                        title="Otro",
                        abstract="x",
                        keywords=["x"],
                        area="x",
                        language="es",
                        created_by=owner,
                    )
                ]
            )

    def test_database_rejects_a_malformed_code(self, owner) -> None:
        with pytest.raises(IntegrityError), transaction.atomic():
            make_manuscript(owner, code="MAL-0001")

    def test_new_manuscript_starts_as_an_active_draft(self, owner) -> None:
        manuscript = make_manuscript(owner)

        assert manuscript.status == Manuscript.Status.DRAFT
        assert manuscript.is_active is True
        assert (manuscript.current_round, manuscript.current_version) == (0, 0)
        assert manuscript.lock_version == 0


@pytest.mark.django_db
class TestManuscriptWithdrawal:
    def test_withdrawal_keeps_status_and_records_the_timestamp(self, owner) -> None:
        manuscript = make_manuscript(owner, status=Manuscript.Status.UNDER_REVIEW)

        manuscript.is_active = False
        manuscript.withdrawn_at = timezone.now()
        manuscript.withdrawn_by = owner
        manuscript.withdrawal_reason = "Retiro solicitado por el autor"
        manuscript.save()
        manuscript.refresh_from_db()

        assert manuscript.status == Manuscript.Status.UNDER_REVIEW
        assert manuscript.is_active is False
        assert manuscript.withdrawn_at is not None

    def test_inactive_without_withdrawn_at_is_rejected(self, owner) -> None:
        manuscript = make_manuscript(owner)

        manuscript.is_active = False
        with pytest.raises(IntegrityError), transaction.atomic():
            manuscript.save()

    def test_active_with_withdrawn_at_is_rejected(self, owner) -> None:
        manuscript = make_manuscript(owner)

        manuscript.withdrawn_at = timezone.now()
        with pytest.raises(IntegrityError), transaction.atomic():
            manuscript.save()

    def test_unknown_status_is_rejected(self, owner) -> None:
        with pytest.raises(IntegrityError), transaction.atomic():
            make_manuscript(owner, status="WITHDRAWN")


@pytest.mark.django_db
class TestManuscriptAuthor:
    def test_author_order_and_email_are_unique_per_manuscript(self, owner) -> None:
        manuscript = make_manuscript(owner)
        ManuscriptAuthor.objects.create(
            manuscript=manuscript,
            full_name="Ana López",
            email="ana@unl.edu.ec",
            affiliation="UNL",
            author_order=1,
            is_corresponding=True,
        )

        with pytest.raises(IntegrityError), transaction.atomic():
            ManuscriptAuthor.objects.create(
                manuscript=manuscript,
                full_name="Luis Pérez",
                email="luis@unl.edu.ec",
                affiliation="UNL",
                author_order=1,
            )
        with pytest.raises(IntegrityError), transaction.atomic():
            ManuscriptAuthor.objects.create(
                manuscript=manuscript,
                full_name="Ana Duplicada",
                email="ana@unl.edu.ec",
                affiliation="UNL",
                author_order=2,
            )

    def test_author_order_must_be_positive(self, owner) -> None:
        manuscript = make_manuscript(owner)

        with pytest.raises(IntegrityError), transaction.atomic():
            ManuscriptAuthor.objects.create(
                manuscript=manuscript,
                full_name="Ana López",
                email="ana@unl.edu.ec",
                affiliation="UNL",
                author_order=0,
            )


@pytest.mark.django_db
class TestManuscriptVersion:
    def test_version_number_is_unique_per_manuscript(self, owner) -> None:
        manuscript = make_manuscript(owner)
        make_version(manuscript, owner)

        with pytest.raises(IntegrityError), transaction.atomic():
            make_version(manuscript, owner)

        assert make_version(manuscript, owner, version_number=2).version_number == 2

    @pytest.mark.parametrize(
        "field", ["original_sha256", "sanitized_sha256", "metadata_sha256"]
    )
    def test_hashes_must_be_64_characters(self, owner, field) -> None:
        manuscript = make_manuscript(owner)

        with pytest.raises(IntegrityError), transaction.atomic():
            make_version(manuscript, owner, **{field: "abc"})

    def test_metadata_snapshot_is_mandatory(self, owner) -> None:
        manuscript = make_manuscript(owner)

        with pytest.raises(IntegrityError), transaction.atomic():
            make_version(manuscript, owner, metadata_snapshot=None)

    def test_version_number_and_size_must_be_positive(self, owner) -> None:
        manuscript = make_manuscript(owner)

        with pytest.raises(IntegrityError), transaction.atomic():
            make_version(manuscript, owner, version_number=0)
        with pytest.raises(IntegrityError), transaction.atomic():
            make_version(manuscript, owner, original_size_bytes=0)

    def test_saved_version_is_never_overwritten_or_deleted(self, owner) -> None:
        version = make_version(make_manuscript(owner), owner)

        version.original_sha256 = "b" * 64
        with pytest.raises(ValueError):
            version.save()
        with pytest.raises(ValueError):
            version.delete()

        version.refresh_from_db()
        assert version.original_sha256 == SHA


@pytest.mark.django_db
class TestCorrectionRound:
    def test_round_number_is_unique_per_manuscript(self, owner) -> None:
        manuscript = make_manuscript(owner)
        CorrectionRound.objects.create(manuscript=manuscript, round_number=0)

        with pytest.raises(IntegrityError), transaction.atomic():
            CorrectionRound.objects.create(manuscript=manuscript, round_number=0)

        assert CorrectionRound.objects.create(manuscript=manuscript, round_number=1)

    def test_round_closes_with_the_version_that_answers_it(self, owner) -> None:
        manuscript = make_manuscript(owner)
        version = make_version(manuscript, owner)

        closed = CorrectionRound.objects.create(
            manuscript=manuscript,
            round_number=0,
            closed_by_version=version,
            closed_at=timezone.now(),
        )

        assert closed.closed_by_version_id == version.id


@pytest.mark.django_db
class TestStatusEvent:
    def test_initial_event_has_no_previous_status(self, owner) -> None:
        manuscript = make_manuscript(owner)

        event = StatusEvent.objects.create(
            manuscript=manuscript, to_status="DRAFT", actor=owner
        )

        assert event.from_status is None
        assert event.metadata == {}

    def test_event_is_append_only(self, owner) -> None:
        event = StatusEvent.objects.create(
            manuscript=make_manuscript(owner), to_status="DRAFT"
        )

        event.to_status = "ACCEPTED"
        with pytest.raises(ValueError):
            event.save()
        with pytest.raises(ValueError):
            event.delete()


@pytest.mark.django_db
class TestPhysicalDeletionIsBlocked:
    def test_manuscript_with_history_is_protected_from_deletion(self, owner) -> None:
        manuscript = make_manuscript(owner)
        make_version(manuscript, owner)

        with pytest.raises(ProtectedError):
            manuscript.delete()
