"""Tests for the integrity layer of the publications schema (TSK-31).

Covers the acceptance criteria: the migrations apply on an empty
PostgreSQL database (the test database is built from them); ``DELETE``
over manuscripts and ``UPDATE``/``DELETE`` over versions and status
events fail in the database; only one corresponding author and one
``author_order`` can exist per manuscript. Also checks the indexes and
the generated ``search_vector`` column of the plan.

The triggers are exercised with queryset operations and raw SQL: the
ORM guards of the models would otherwise answer first.
"""

from __future__ import annotations

import pytest
from django.contrib.postgres.search import SearchQuery
from django.db import IntegrityError, connection, transaction
from django.db.utils import DatabaseError

from apps.publications.models import (
    Manuscript,
    ManuscriptAuthor,
    ManuscriptVersion,
    StatusEvent,
)
from tests.factories import UserFactory
from tests.publications.test_models import make_manuscript, make_version


@pytest.fixture
def owner(db):
    return UserFactory()


def table_indexes(table: str) -> dict[str, str]:
    """Map index name to its ``CREATE INDEX`` definition."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT indexname, indexdef FROM pg_indexes WHERE tablename = %s",
            [table],
        )
        return dict(cursor.fetchall())


@pytest.mark.django_db
class TestTriggers:
    def test_delete_over_a_manuscript_fails_in_the_database(self, owner) -> None:
        manuscript = make_manuscript(owner)

        with pytest.raises(DatabaseError, match="solo admiten baja lógica"):
            with transaction.atomic():
                Manuscript.objects.filter(pk=manuscript.pk).delete()

        assert Manuscript.objects.filter(pk=manuscript.pk).exists()

    def test_raw_delete_over_a_manuscript_also_fails(self, owner) -> None:
        manuscript = make_manuscript(owner)

        with pytest.raises(DatabaseError, match="solo admiten baja lógica"):
            with transaction.atomic(), connection.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM publications_manuscript WHERE id = %s",
                    [manuscript.pk],
                )

    def test_logical_withdrawal_is_still_allowed(self, owner) -> None:
        from django.utils import timezone

        manuscript = make_manuscript(owner)

        updated = Manuscript.objects.filter(pk=manuscript.pk).update(
            is_active=False, withdrawn_at=timezone.now()
        )

        assert updated == 1

    def test_version_cannot_be_updated_or_deleted(self, owner) -> None:
        version = make_version(make_manuscript(owner), owner)

        with pytest.raises(DatabaseError, match="inmutables"):
            with transaction.atomic():
                ManuscriptVersion.objects.filter(pk=version.pk).update(
                    original_sha256="b" * 64
                )
        with pytest.raises(DatabaseError, match="inmutables"):
            with transaction.atomic():
                ManuscriptVersion.objects.filter(pk=version.pk).delete()

        version.refresh_from_db()
        assert version.original_sha256 == "a" * 64

    def test_status_event_cannot_be_updated_or_deleted(self, owner) -> None:
        event = StatusEvent.objects.create(
            manuscript=make_manuscript(owner), to_status="DRAFT"
        )

        with pytest.raises(DatabaseError, match="append-only"):
            with transaction.atomic():
                StatusEvent.objects.filter(pk=event.pk).update(to_status="ACCEPTED")
        with pytest.raises(DatabaseError, match="append-only"):
            with transaction.atomic():
                StatusEvent.objects.filter(pk=event.pk).delete()

        event.refresh_from_db()
        assert event.to_status == "DRAFT"


@pytest.mark.django_db
class TestCorrespondingAuthor:
    @staticmethod
    def add_author(manuscript, order: int, *, corresponding: bool):
        return ManuscriptAuthor.objects.create(
            manuscript=manuscript,
            full_name=f"Autor {order}",
            email=f"autor{order}@unl.edu.ec",
            affiliation="UNL",
            author_order=order,
            is_corresponding=corresponding,
        )

    def test_only_one_corresponding_author_per_manuscript(self, owner) -> None:
        manuscript = make_manuscript(owner)
        self.add_author(manuscript, 1, corresponding=True)

        with pytest.raises(IntegrityError), transaction.atomic():
            self.add_author(manuscript, 2, corresponding=True)

        assert self.add_author(manuscript, 2, corresponding=False)

    def test_each_manuscript_has_its_own_corresponding_author(self, owner) -> None:
        self.add_author(make_manuscript(owner), 1, corresponding=True)

        assert self.add_author(make_manuscript(owner), 1, corresponding=True)

    def test_author_order_is_unique_per_manuscript(self, owner) -> None:
        manuscript = make_manuscript(owner)
        self.add_author(manuscript, 1, corresponding=False)

        with pytest.raises(IntegrityError), transaction.atomic():
            self.add_author(manuscript, 1, corresponding=False)


@pytest.mark.django_db
class TestIndexes:
    def test_manuscript_indexes_exist_with_the_planned_method(self) -> None:
        indexes = table_indexes("publications_manuscript")

        for name in (
            "idx_manuscript_status_active",
            "idx_manuscript_owner_active",
            "idx_manuscript_area",
        ):
            assert "USING btree" in indexes[name]
        assert "USING gin (search_vector)" in indexes["idx_manuscript_search"]

    def test_version_event_and_author_indexes_exist(self) -> None:
        assert "idx_version_manuscript_date" in table_indexes(
            "publications_manuscript_version"
        )
        assert "idx_status_event_manuscript" in table_indexes(
            "publications_status_event"
        )
        corresponding = table_indexes("publications_manuscript_author")[
            "uq_manuscript_corresponding"
        ]
        assert "UNIQUE" in corresponding and "is_corresponding" in corresponding


@pytest.mark.django_db
class TestSearchVector:
    def search(self, text: str):
        return Manuscript.objects.filter(
            search_vector=SearchQuery(text, config="spanish")
        )

    def test_vector_covers_title_abstract_and_keywords(self, owner) -> None:
        manuscript = make_manuscript(
            owner,
            title="Biodiversidad amazónica",
            abstract="Muestreo de anfibios en transectos.",
            keywords=["ranas", "conservación"],
        )

        for term in ("biodiversidad", "anfibios", "ranas"):
            assert list(self.search(term)) == [manuscript]
        assert not self.search("astronomía").exists()

    def test_vector_follows_updates_without_application_code(self, owner) -> None:
        manuscript = make_manuscript(owner, title="Hidrología andina")
        assert self.search("hidrología").exists()

        manuscript.title = "Glaciología tropical"
        manuscript.save()

        assert not self.search("hidrología").exists()
        assert self.search("glaciología").exists()

    def test_vector_is_stemmed_with_the_spanish_configuration(self, owner) -> None:
        make_manuscript(owner, title="Cultivos orgánicos")

        assert self.search("cultivo").exists()

    def test_vector_is_read_only_in_the_database(self, owner) -> None:
        manuscript = make_manuscript(owner)

        with pytest.raises(DatabaseError):
            with transaction.atomic(), connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE publications_manuscript "
                    "SET search_vector = to_tsvector('spanish', 'x') WHERE id = %s",
                    [manuscript.pk],
                )
