"""Tests for the public catalog (TSK-74, plan sections 2.6 and 4.7).

Acceptance criteria: without authentication the catalog shows no
manuscript in review, rejected or withdrawn, and no evaluations, reviewers,
history or audit; the search covers title, authors, keywords, area and
abstract with pagination and filters; a non-accepted article answers
``404``, a retired PDF ``410``, and every download is audited.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIClient

from apps.audit.models import AuditLog
from apps.audit.services import AuditUnavailable
from apps.publications.models import CatalogEntry, Manuscript
from apps.publications.services.storage import catalog_path
from tests.factories import (
    CatalogEntryFactory,
    ManuscriptAuthorFactory,
    ManuscriptFactory,
    ManuscriptVersionFactory,
    UserFactory,
)
from tests.publications.test_manuscript_api import actor, client_for

pytestmark = pytest.mark.django_db

LIST_URL = "/api/catalog/"


@pytest.fixture(autouse=True)
def media_root(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    return tmp_path


@pytest.fixture
def anonymous() -> APIClient:
    return APIClient()


def published(*, with_file: bool = True, **manuscript_overrides) -> CatalogEntry:
    """An accepted, active manuscript with an active entry and its public copy."""
    manuscript = ManuscriptFactory(status=Manuscript.Status.ACCEPTED, **manuscript_overrides)
    ManuscriptAuthorFactory(
        manuscript=manuscript,
        full_name="Ana Lucía Torres",
        email="ana.privada@unl.edu.ec",
        affiliation="Universidad Nacional de Loja",
        author_order=1,
        is_corresponding=True,
    )
    version = ManuscriptVersionFactory(manuscript=manuscript, submitted_by=manuscript.created_by)
    entry = CatalogEntryFactory(manuscript=manuscript, version=version)
    if with_file:
        path = catalog_path(entry.public_file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"%PDF-1.7 publico")
    return entry


def codes(response) -> list[str]:
    return [row["code"] for row in response.json()["results"]]


class TestVisibility:
    def test_anonymous_sees_published_articles(self, anonymous) -> None:
        entry = published()

        response = anonymous.get(LIST_URL)

        assert response.status_code == 200
        assert codes(response) == [entry.manuscript.code]

    def test_only_accepted_active_and_published_articles_are_listed(self, anonymous) -> None:
        visible = published()
        for status in ("DRAFT", "SUBMITTED", "UNDER_REVIEW", "REQUIRES_CORRECTIONS", "REJECTED"):
            manuscript = ManuscriptFactory(status=status)
            version = ManuscriptVersionFactory(manuscript=manuscript, submitted_by=manuscript.created_by)
            CatalogEntry.objects.create(
                manuscript=manuscript, version=version, public_file_path=f"{manuscript.pk}/x.pdf"
            )
        ManuscriptFactory(status="ACCEPTED")  # aceptado pero sin entrada
        withdrawn = published()
        Manuscript.objects.filter(pk=withdrawn.manuscript_id).update(
            is_active=False, withdrawn_at=timezone.now()
        )
        inactive_entry = published()
        CatalogEntry.objects.filter(pk=inactive_entry.pk).update(
            is_active=False, unpublished_at=timezone.now()
        )

        assert codes(anonymous.get(LIST_URL)) == [visible.manuscript.code]

    def test_a_bad_token_does_not_break_a_public_page(self, anonymous) -> None:
        published()
        anonymous.credentials(HTTP_AUTHORIZATION="Bearer token-invalido")

        assert anonymous.get(LIST_URL).status_code == 200

    def test_only_safe_methods_are_open(self, anonymous) -> None:
        entry = published()

        assert anonymous.post(LIST_URL, {}, format="json").status_code in (401, 403, 405)
        assert anonymous.delete(f"{LIST_URL}{entry.manuscript.code}/").status_code in (401, 403, 405)


class TestMinimization:
    def test_response_has_only_public_data(self, anonymous) -> None:
        entry = published(title="Cultivos andinos", abstract="Resumen público.")

        response = anonymous.get(f"{LIST_URL}{entry.manuscript.code}/")
        body = response.json()

        assert set(body) == {
            "code", "title", "authors", "abstract", "keywords", "area",
            "language", "published_at", "version_number", "document_url",
        }
        assert body["authors"] == [
            {"full_name": "Ana Lucía Torres", "affiliation": "Universidad Nacional de Loja"}
        ]
        assert body["document_url"] == f"/api/catalog/{entry.manuscript.code}/document/"
        text = response.content.decode()
        for forbidden in ("ana.privada", "created_by", "original_filename", "sha256", "reviewer", "evaluation"):
            assert forbidden not in text

    def test_no_internal_ids_leak(self, anonymous) -> None:
        entry = published()

        text = anonymous.get(LIST_URL).content.decode() + anonymous.get(
            f"{LIST_URL}{entry.manuscript.code}/"
        ).content.decode()

        for internal in (str(entry.manuscript_id), str(entry.version_id), str(entry.pk), str(entry.manuscript.created_by_id)):
            assert internal not in text

    def test_authors_come_in_their_listed_order(self, anonymous) -> None:
        entry = published()
        ManuscriptAuthorFactory(
            manuscript=entry.manuscript, full_name="Bruno Díaz", author_order=2, affiliation="UTPL"
        )

        authors = anonymous.get(f"{LIST_URL}{entry.manuscript.code}/").json()["authors"]

        assert [a["full_name"] for a in authors] == ["Ana Lucía Torres", "Bruno Díaz"]


class TestDetail:
    def test_published_article_page(self, anonymous) -> None:
        entry = published()

        response = anonymous.get(f"{LIST_URL}{entry.manuscript.code}/")

        assert response.status_code == 200
        assert response.json()["version_number"] == entry.version.version_number

    @pytest.mark.parametrize("status", ["UNDER_REVIEW", "REJECTED", "SUBMITTED", "DRAFT"])
    def test_non_accepted_article_answers_404(self, anonymous, status) -> None:
        manuscript = ManuscriptFactory(status=status)

        assert anonymous.get(f"{LIST_URL}{manuscript.code}/").status_code == 404

    def test_unknown_code_answers_404(self, anonymous) -> None:
        assert anonymous.get(f"{LIST_URL}GPC-2026-999999/").status_code == 404

    def test_withdrawn_article_page_answers_404(self, anonymous) -> None:
        entry = published()
        Manuscript.objects.filter(pk=entry.manuscript_id).update(
            is_active=False, withdrawn_at=timezone.now()
        )

        assert anonymous.get(f"{LIST_URL}{entry.manuscript.code}/").status_code == 404


class TestSearchAndFilters:
    def test_search_covers_title_authors_keywords_area_and_abstract(self, anonymous) -> None:
        by_title = published(title="Glaciares tropicales")
        by_abstract = published(abstract="Estudio sobre la quinua orgánica en suelos áridos.")
        by_keyword = published(keywords=["hidroponía", "lechuga"])
        by_area = published(area="Oceanografía")
        by_author = published()
        ManuscriptAuthorFactory(
            manuscript=by_author.manuscript, full_name="Yolanda Zambrano", affiliation="ESPOL", author_order=2
        )

        def found(term):
            return codes(anonymous.get(LIST_URL, {"search": term}))

        assert found("glaciares") == [by_title.manuscript.code]
        assert found("quinua") == [by_abstract.manuscript.code]
        assert found("hidroponía") == [by_keyword.manuscript.code]
        assert found("oceanografía") == [by_area.manuscript.code]
        assert found("Zambrano") == [by_author.manuscript.code]
        assert found("ESPOL") == [by_author.manuscript.code]
        assert found("inexistente") == []

    def test_search_never_returns_a_non_public_article(self, anonymous) -> None:
        ManuscriptFactory(status="UNDER_REVIEW", title="Secreto en revisión")

        assert codes(anonymous.get(LIST_URL, {"search": "secreto"})) == []

    def test_author_match_does_not_duplicate_the_article(self, anonymous) -> None:
        entry = published()
        ManuscriptAuthorFactory(
            manuscript=entry.manuscript, full_name="Ana Otra", author_order=2, affiliation="UNL"
        )

        assert codes(anonymous.get(LIST_URL, {"search": "ana"})) == [entry.manuscript.code]

    def test_area_language_keyword_filters(self, anonymous) -> None:
        agro = published(area="Agronomía", language="es", keywords=["suelo"])
        published(area="Física", language="en", keywords=["energía"])

        assert codes(anonymous.get(LIST_URL, {"area": "agronomía"})) == [agro.manuscript.code]
        assert codes(anonymous.get(LIST_URL, {"language": "es"})) == [agro.manuscript.code]
        assert codes(anonymous.get(LIST_URL, {"keyword": "suelo"})) == [agro.manuscript.code]

    def test_publication_date_range(self, anonymous) -> None:
        old = published()
        CatalogEntry.objects.filter(pk=old.pk).update(published_at=timezone.now() - timedelta(days=30))
        recent = published()
        today = timezone.localdate()

        recent_only = codes(anonymous.get(LIST_URL, {"date_from": (today - timedelta(days=1)).isoformat()}))
        old_only = codes(anonymous.get(LIST_URL, {"date_to": (today - timedelta(days=10)).isoformat()}))

        assert recent_only == [recent.manuscript.code]
        assert old_only == [old.manuscript.code]

    def test_ordering(self, anonymous) -> None:
        b = published(title="B artículo")
        a = published(title="A artículo")

        assert codes(anonymous.get(LIST_URL, {"ordering": "title"})) == [a.manuscript.code, b.manuscript.code]
        assert codes(anonymous.get(LIST_URL, {"ordering": "-title"})) == [b.manuscript.code, a.manuscript.code]
        newest_first = codes(anonymous.get(LIST_URL))
        assert newest_first == [a.manuscript.code, b.manuscript.code]

    @pytest.mark.parametrize(
        "params",
        [
            {"date_from": "ayer"},
            {"date_from": "2026-05-02", "date_to": "2026-05-01"},
            {"language": "espanol"},
            {"ordering": "code"},
            {"page_size": 101},
            {"page": "x"},
        ],
    )
    def test_malformed_parameters_answer_400(self, anonymous, params) -> None:
        response = anonymous.get(LIST_URL, params)

        assert response.status_code == 400

    def test_pagination(self, anonymous) -> None:
        for _ in range(3):
            published()

        body = anonymous.get(LIST_URL, {"page_size": 2}).json()

        assert body["count"] == 3 and len(body["results"]) == 2 and body["next"]


class TestCaching:
    def test_pages_are_cached_for_at_most_five_minutes(self, anonymous) -> None:
        entry = published()

        for url in (LIST_URL, f"{LIST_URL}{entry.manuscript.code}/"):
            header = anonymous.get(url)["Cache-Control"]
            assert "public" in header
            assert int(header.split("max-age=")[1]) <= 300

    def test_document_is_never_cached(self, anonymous) -> None:
        entry = published()

        response = anonymous.get(f"{LIST_URL}{entry.manuscript.code}/document/")

        assert "no-store" in response["Cache-Control"]


class TestDocument:
    def test_delivers_the_public_copy_through_nginx_and_audits_it(self, anonymous) -> None:
        entry = published()

        response = anonymous.get(f"{LIST_URL}{entry.manuscript.code}/document/")

        assert response.status_code == 200
        assert response["X-Accel-Redirect"] == f"/_catalog/{entry.public_file_path}"
        assert response["Content-Type"] == "application/pdf"
        assert response["Content-Disposition"].startswith("inline")
        assert entry.manuscript.title not in response["Content-Disposition"]
        assert response.content == b""
        event = AuditLog.objects.get(action="CATALOG_DOCUMENT_DOWNLOADED")
        assert event.actor_id is None and event.result == "SUCCESS"
        assert event.entity_id == entry.version_id
        assert event.details["code"] == entry.manuscript.code
        assert event.details["kind"] == "public"

    def test_every_download_is_audited(self, anonymous) -> None:
        entry = published()
        url = f"{LIST_URL}{entry.manuscript.code}/document/"

        anonymous.get(url)
        anonymous.get(url)

        assert AuditLog.objects.filter(action="CATALOG_DOCUMENT_DOWNLOADED").count() == 2

    def test_the_internal_path_never_comes_from_the_request(self, anonymous) -> None:
        entry = published()

        response = anonymous.get(
            f"{LIST_URL}{entry.manuscript.code}/document/",
            {"path": "../../private/secret.pdf", "file": "original.pdf"},
        )

        assert response["X-Accel-Redirect"] == f"/_catalog/{entry.public_file_path}"
        assert "_protected" not in response["X-Accel-Redirect"]

    @pytest.mark.parametrize("status", ["UNDER_REVIEW", "REJECTED", "SUBMITTED", "DRAFT"])
    def test_non_accepted_article_answers_404_without_audit(self, anonymous, status) -> None:
        manuscript = ManuscriptFactory(status=status)

        assert anonymous.get(f"{LIST_URL}{manuscript.code}/document/").status_code == 404
        assert not AuditLog.objects.filter(action="CATALOG_DOCUMENT_DOWNLOADED").exists()

    def test_unknown_code_answers_404(self, anonymous) -> None:
        assert anonymous.get(f"{LIST_URL}GPC-2026-999999/document/").status_code == 404

    def test_retired_pdf_answers_410_without_audit(self, anonymous) -> None:
        entry = published()
        CatalogEntry.objects.filter(pk=entry.pk).update(is_active=False, unpublished_at=timezone.now())

        response = anonymous.get(f"{LIST_URL}{entry.manuscript.code}/document/")

        assert response.status_code == 410
        assert "X-Accel-Redirect" not in response
        assert not AuditLog.objects.filter(action="CATALOG_DOCUMENT_DOWNLOADED").exists()

    def test_withdrawn_article_document_answers_410(self, anonymous) -> None:
        entry = published()
        Manuscript.objects.filter(pk=entry.manuscript_id).update(
            is_active=False, withdrawn_at=timezone.now()
        )

        assert anonymous.get(f"{LIST_URL}{entry.manuscript.code}/document/").status_code == 410

    def test_missing_file_answers_503_without_audit(self, anonymous) -> None:
        entry = published(with_file=False)

        response = anonymous.get(f"{LIST_URL}{entry.manuscript.code}/document/")

        assert response.status_code == 503
        assert response.json()["error"]["code"] == "STORAGE_UNAVAILABLE"
        assert not AuditLog.objects.filter(action="CATALOG_DOCUMENT_DOWNLOADED").exists()

    def test_without_audit_there_is_no_redirect(self, anonymous, monkeypatch) -> None:
        entry = published()

        def broken(**kwargs):
            raise AuditUnavailable("sin auditoría")

        monkeypatch.setattr("apps.publications.services.downloads.AuditService.record", broken)
        response = anonymous.get(f"{LIST_URL}{entry.manuscript.code}/document/")

        assert response.status_code == 503
        assert response.json()["error"]["code"] == "AUDIT_UNAVAILABLE"
        assert "X-Accel-Redirect" not in response


class TestWithdrawalRetiresTheArticle:
    @pytest.fixture(autouse=True)
    def seeded_roles(self, db) -> None:
        call_command("seed_roles", verbosity=0)

    def test_withdrawing_removes_entry_page_and_copy(
        self, anonymous, django_capture_on_commit_callbacks
    ) -> None:
        owner = actor("AUTHOR")
        entry = published(created_by=owner)
        code, copy = entry.manuscript.code, catalog_path(entry.public_file_path)
        assert copy.is_file()

        with django_capture_on_commit_callbacks(execute=True):
            response = client_for(owner).post(
                f"/api/manuscripts/{entry.manuscript_id}/withdraw/",
                {"reason": "Retiro por error en los datos."},
                format="json",
            )

        assert response.status_code == 200
        entry.refresh_from_db()
        assert entry.is_active is False and entry.unpublished_at is not None
        assert not copy.exists()
        assert anonymous.get(f"{LIST_URL}{code}/").status_code == 404
        assert anonymous.get(f"{LIST_URL}{code}/document/").status_code == 410
        assert codes(anonymous.get(LIST_URL)) == []

    def test_a_failing_file_removal_still_hides_the_article(
        self, anonymous, monkeypatch, django_capture_on_commit_callbacks
    ) -> None:
        owner = actor("AUTHOR")
        entry = published(created_by=owner)
        monkeypatch.setattr(
            "pathlib.Path.unlink", lambda self, missing_ok=False: (_ for _ in ()).throw(OSError("denegado"))
        )

        with django_capture_on_commit_callbacks(execute=True):
            response = client_for(owner).post(
                f"/api/manuscripts/{entry.manuscript_id}/withdraw/",
                {"reason": "Retiro por error en los datos."},
                format="json",
            )
        monkeypatch.undo()

        assert response.status_code == 200
        assert catalog_path(entry.public_file_path).is_file()
        assert anonymous.get(f"{LIST_URL}{entry.manuscript.code}/").status_code == 404
