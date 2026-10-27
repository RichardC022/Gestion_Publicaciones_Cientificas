"""Tests for the verdict and catalog entry models (TSK-50).

Covers the acceptance criteria: ``REJECTED`` requires a justification and
``REQUIRES_CORRECTIONS`` requires observations; the round keeps the
reference to the verdict that opened it; the verdict is append-only (no
``UPDATE`` nor ``DELETE``); and a manuscript has at most one active
catalog entry whose public copy never points to the private original.

The constraints and triggers are exercised with queryset operations and
raw SQL, so the database answers and not a guard of the models.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from django.db import IntegrityError, connection, transaction
from django.db.models import ProtectedError
from django.db.utils import DatabaseError
from django.utils import timezone

from apps.publications.models import CatalogEntry, CorrectionRound, Verdict
from apps.reviews.models import Assignment
from tests.factories import CorrectionRoundFactory, ManuscriptVersionFactory
from tests.reviews.test_models import Scenario

pytestmark = pytest.mark.django_db


@pytest.fixture
def scenario(db) -> Scenario:
    return Scenario()


def make_verdict(scenario: Scenario, evaluation, **overrides) -> Verdict:
    values = {
        "manuscript": evaluation.manuscript,
        "version": evaluation.version,
        "evaluation": evaluation,
        "editor": scenario.editor,
        "decision": Verdict.Decision.ACCEPTED,
        **overrides,
    }
    return Verdict.objects.create(**values)


@pytest.fixture
def evaluation(scenario):
    return scenario.final_evaluation(scenario.assignment())


class TestVerdictRequirements:
    def test_an_accepted_verdict_needs_no_text(self, scenario, evaluation) -> None:
        verdict = make_verdict(scenario, evaluation)

        assert verdict.justification is None and verdict.observations is None
        assert verdict.previous_verdict is None

    def test_a_rejection_requires_a_justification(self, scenario, evaluation) -> None:
        with pytest.raises(IntegrityError, match="ck_verdict_rejected_justification"):
            with transaction.atomic():
                make_verdict(scenario, evaluation, decision="REJECTED")

        verdict = make_verdict(
            scenario, evaluation, decision="REJECTED", justification="Metodología inválida."
        )
        assert verdict.justification == "Metodología inválida."

    def test_a_correction_request_requires_observations(self, scenario, evaluation) -> None:
        with pytest.raises(IntegrityError, match="ck_verdict_corrections_observations"):
            with transaction.atomic():
                make_verdict(scenario, evaluation, decision="REQUIRES_CORRECTIONS")

        verdict = make_verdict(
            scenario, evaluation, decision="REQUIRES_CORRECTIONS", observations="Ampliar la sección 3."
        )
        assert verdict.observations == "Ampliar la sección 3."

    def test_an_unknown_decision_is_rejected(self, scenario, evaluation) -> None:
        with pytest.raises(IntegrityError, match="ck_verdict_decision"):
            with transaction.atomic():
                make_verdict(
                    scenario, evaluation, decision="MAYBE", justification="x", observations="x"
                )


class TestOneVerdictPerVersion:
    def test_a_second_normal_verdict_for_the_same_version_is_rejected(
        self, scenario, evaluation
    ) -> None:
        make_verdict(scenario, evaluation)

        with pytest.raises(IntegrityError, match="uq_verdict_normal_per_version"):
            with transaction.atomic():
                make_verdict(scenario, evaluation, decision="REJECTED", justification="x")

    def test_a_correction_links_to_the_verdict_it_replaces(self, scenario, evaluation) -> None:
        original = make_verdict(scenario, evaluation)

        replacement = make_verdict(
            scenario, evaluation, decision="REJECTED", justification="Revisado.",
            previous_verdict=original,
        )

        assert replacement.previous_verdict == original
        assert list(original.corrections.all()) == [replacement]
        original.refresh_from_db()
        assert original.decision == "ACCEPTED"

    def test_every_version_has_its_own_verdict(self, scenario, evaluation) -> None:
        make_verdict(scenario, evaluation)
        # La primera asignación se completó: solo puede haber una activa.
        Assignment.objects.filter(pk=evaluation.assignment_id).update(status="COMPLETED")
        second_version = ManuscriptVersionFactory(
            manuscript=scenario.manuscript,
            submitted_by=scenario.author,
            version_number=2,
            round_number=1,
        )
        second = scenario.final_evaluation(scenario.assignment(version=second_version))

        verdict = make_verdict(scenario, second, decision="ACCEPTED")

        assert Verdict.objects.filter(manuscript=scenario.manuscript).count() == 2
        assert verdict.version == second_version

    def test_the_history_is_ordered_by_creation(self, scenario, evaluation) -> None:
        first = make_verdict(scenario, evaluation)
        second = make_verdict(
            scenario, evaluation, decision="REJECTED", justification="x", previous_verdict=first
        )

        assert list(scenario.manuscript.verdicts.all()) == [first, second]


class TestVerdictIsAppendOnly:
    def test_the_orm_rejects_modifying_or_deleting_a_saved_verdict(
        self, scenario, evaluation
    ) -> None:
        verdict = make_verdict(scenario, evaluation)
        verdict.decision = "REJECTED"

        with pytest.raises(ValueError, match="inmutable"):
            verdict.save()
        with pytest.raises(ValueError, match="inmutable"):
            verdict.delete()

    def test_update_over_a_verdict_fails_in_the_database(self, scenario, evaluation) -> None:
        verdict = make_verdict(scenario, evaluation)

        with pytest.raises(DatabaseError, match="append-only"):
            with transaction.atomic():
                Verdict.objects.filter(pk=verdict.pk).update(decision="REJECTED")

        verdict.refresh_from_db()
        assert verdict.decision == "ACCEPTED"

    def test_raw_update_and_delete_also_fail(self, scenario, evaluation) -> None:
        verdict = make_verdict(scenario, evaluation)

        for sql in (
            "UPDATE publications_verdict SET observations = 'x' WHERE id = %s",
            "DELETE FROM publications_verdict WHERE id = %s",
        ):
            with pytest.raises(DatabaseError, match="append-only"):
                with transaction.atomic(), connection.cursor() as cursor:
                    cursor.execute(sql, [verdict.pk])

        assert Verdict.objects.filter(pk=verdict.pk).exists()

    def test_a_referenced_verdict_cannot_be_deleted_even_by_queryset(
        self, scenario, evaluation
    ) -> None:
        verdict = make_verdict(
            scenario, evaluation, decision="REQUIRES_CORRECTIONS", observations="Corregir."
        )
        CorrectionRoundFactory(
            manuscript=scenario.manuscript, round_number=1, opened_by_verdict=verdict
        )

        with pytest.raises(ProtectedError):
            Verdict.objects.filter(pk=verdict.pk).delete()


class TestRoundKeepsItsVerdict:
    def test_the_round_opened_by_a_verdict_conserves_the_reference(
        self, scenario, evaluation
    ) -> None:
        verdict = make_verdict(
            scenario, evaluation, decision="REQUIRES_CORRECTIONS", observations="Corregir."
        )
        round_one = CorrectionRoundFactory(
            manuscript=scenario.manuscript, round_number=1, opened_by_verdict=verdict
        )

        round_one.refresh_from_db()
        assert round_one.opened_by_verdict == verdict
        assert list(verdict.opened_rounds.all()) == [round_one]

    def test_round_zero_has_no_verdict(self, scenario) -> None:
        round_zero = CorrectionRoundFactory(manuscript=scenario.manuscript, round_number=0)

        assert round_zero.opened_by_verdict is None

    def test_the_foreign_key_is_deferrable_initially_deferred(self) -> None:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT condeferrable, condeferred FROM pg_constraint "
                "WHERE conrelid = 'publications_correction_round'::regclass "
                "AND confrelid = 'publications_verdict'::regclass AND contype = 'f'"
            )
            assert cursor.fetchall() == [(True, True)]

    def test_a_dangling_reference_is_only_rejected_when_constraints_are_checked(
        self, scenario
    ) -> None:
        """Round and verdict may be written in either order within a transaction."""
        CorrectionRound.objects.create(
            manuscript=scenario.manuscript, round_number=1, opened_by_verdict_id=uuid.uuid4()
        )

        with pytest.raises(IntegrityError):
            connection.check_constraints()


class TestCatalogEntry:
    def entry(self, scenario: Scenario, **overrides) -> CatalogEntry:
        values = {
            "manuscript": scenario.manuscript,
            "version": scenario.version,
            "public_file_path": f"{scenario.manuscript.pk}/{scenario.version.pk}.pdf",
            **overrides,
        }
        return CatalogEntry.objects.create(**values)

    def test_a_new_entry_is_active_and_published_now(self, scenario) -> None:
        entry = self.entry(scenario)

        assert entry.is_active is True and entry.unpublished_at is None
        assert abs(timezone.now() - entry.published_at) < timedelta(minutes=1)

    def test_a_manuscript_has_at_most_one_active_entry(self, scenario) -> None:
        self.entry(scenario)

        with pytest.raises(IntegrityError, match="uq_catalog_active"):
            with transaction.atomic():
                self.entry(scenario, public_file_path="otra/copia.pdf")

    def test_retired_entries_coexist_with_an_active_one(self, scenario) -> None:
        now = timezone.now()
        self.entry(scenario, is_active=False, unpublished_at=now)
        self.entry(scenario, public_file_path="x/segunda.pdf", is_active=False, unpublished_at=now)

        active = self.entry(scenario, public_file_path="x/tercera.pdf")

        assert scenario.manuscript.catalog_entries.filter(is_active=True).get() == active
        assert scenario.manuscript.catalog_entries.count() == 3

    def test_two_manuscripts_can_each_have_an_active_entry(self, scenario) -> None:
        other = Scenario()
        self.entry(scenario)

        self.entry(other, manuscript=other.manuscript, version=other.version)

        assert CatalogEntry.objects.filter(is_active=True).count() == 2

    def test_deactivating_requires_the_retirement_date_and_viceversa(self, scenario) -> None:
        entry = self.entry(scenario)

        with pytest.raises(IntegrityError, match="ck_catalog_unpublish"):
            with transaction.atomic():
                CatalogEntry.objects.filter(pk=entry.pk).update(is_active=False)
        with pytest.raises(IntegrityError, match="ck_catalog_unpublish"):
            with transaction.atomic():
                CatalogEntry.objects.filter(pk=entry.pk).update(unpublished_at=timezone.now())

        CatalogEntry.objects.filter(pk=entry.pk).update(
            is_active=False, unpublished_at=timezone.now()
        )
        entry.refresh_from_db()
        assert entry.is_active is False and entry.unpublished_at is not None

    @pytest.mark.parametrize(
        "path",
        [
            "",
            "/data/media/public/catalog/x.pdf",
            "manuscripts/abc/v0001/original.pdf",
            "../private/original.pdf",
            "abc/../../original.pdf",
        ],
    )
    def test_the_public_copy_never_points_to_the_private_tree(self, scenario, path) -> None:
        with pytest.raises(IntegrityError, match="ck_catalog_public_path"):
            with transaction.atomic():
                self.entry(scenario, public_file_path=path)

    def test_the_public_path_is_distinct_from_the_original(self, scenario) -> None:
        entry = self.entry(scenario)

        assert entry.public_file_path != scenario.version.original_file_path
        assert entry.public_file_path != scenario.version.sanitized_file_path
