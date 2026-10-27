"""Edge cases of the manuscript module found by the coverage review (TSK-40).

Each test exists because a real behavior had no test: several versions
inside one round, the retry that reaches the transaction instead of the
view, XMP hidden outside the catalog, embedded-file streams, a cleanup
that cannot delete, and the defensive branches of the scopes.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pikepdf
import pytest
from pikepdf import Dictionary, Name

from apps.publications import views as views_module
from apps.publications.models import CorrectionRound, Manuscript, ManuscriptVersion
from apps.publications.permissions import resolve_manuscript
from apps.publications.services.idempotency import IdempotencyScope
from apps.publications.services.manuscripts import validate_author_roster
from apps.publications.services.pdf import PdfInvalid, PdfService, find_active_content
from apps.publications.services.storage import remove_quietly
from tests.factories import (
    CorrectionRoundFactory,
    ManuscriptAuthorFactory,
    ManuscriptFactory,
    ManuscriptVersionFactory,
    StatusEventFactory,
    UserFactory,
)
from tests.publications import pdf_factory as factory
from tests.publications.test_draft_file import pdf_file
from tests.publications.test_manuscript_api import actor, client_for  # noqa: F401
from tests.publications.test_new_version import (  # noqa: F401
    CORRECTED_PDF,
    corrected,
    request_corrections,
    send,
)
from tests.publications.test_submission import (  # noqa: F401
    media_root,
    owner,
    ready_draft,
    seeded_roles,
    submit,
)
from tests.publications.test_versions_history import history_url

pytestmark = pytest.mark.django_db

THIRD_PDF = factory.clean_pdf(pages=3)


class TestSeveralVersionsInOneRound:
    def test_a_version_joins_a_round_that_is_already_closed_without_reopening_it(
        self, owner, corrected, send
    ) -> None:
        assert send(owner, corrected, key="v2").status_code == 201
        closed_at = CorrectionRound.objects.get(manuscript=corrected, round_number=1).closed_at
        # Vuelve a pedirse una corrección sin abrir ronda nueva: la ronda 1 ya está cerrada.
        Manuscript.objects.filter(pk=corrected.pk).update(status="REQUIRES_CORRECTIONS")

        response = send(owner, corrected, pdf_file(THIRD_PDF), key="v3")

        assert response.status_code == 201
        assert (response.json()["version_number"], response.json()["round_number"]) == (3, 1)
        v2, v3 = ManuscriptVersion.objects.filter(manuscript=corrected, version_number__in=(2, 3)).order_by("version_number")
        assert (v2.round_number, v3.round_number) == (1, 1)
        round_one = CorrectionRound.objects.get(manuscript=corrected, round_number=1)
        assert round_one.closed_by_version == v2 and round_one.closed_at == closed_at
        assert CorrectionRound.objects.filter(manuscript=corrected).count() == 2

    def test_the_history_lists_both_versions_under_the_same_round(self, owner, corrected, send) -> None:
        send(owner, corrected, key="v2")
        Manuscript.objects.filter(pk=corrected.pk).update(status="REQUIRES_CORRECTIONS")
        send(owner, corrected, pdf_file(THIRD_PDF), key="v3")

        entries = client_for(owner).get(history_url(corrected)).json()["results"]

        versions = [e for e in entries if e["type"] == "VERSION_SUBMITTED"]
        assert [(e["version_number"], e["round_number"]) for e in versions] == [(1, 0), (2, 1), (3, 1)]
        rounds = [e for e in entries if e["type"] == "ROUND_OPENED"]
        assert [(r["round_number"], r["closed_by_version_number"]) for r in rounds] == [(0, 1), (1, 2)]


class TestRetryThatReachesTheTransaction:
    """The retry the view could not intercept (it raced the first request)."""

    def test_a_submission_retry_is_answered_from_the_stored_response(self, owner, submit, monkeypatch) -> None:
        manuscript = ready_draft(owner)
        first = submit(owner, manuscript, key="envio-1")
        monkeypatch.setattr(IdempotencyScope, "find", lambda self: None)
        monkeypatch.setattr(views_module, "ensure_draft", lambda *args, **kwargs: None)

        second = submit(owner, manuscript, key="envio-1")

        assert second.status_code == 201 and second.json() == first.json()
        assert second["Idempotent-Replayed"] == "true"
        assert ManuscriptVersion.objects.filter(manuscript=manuscript).count() == 1

    def test_a_new_version_retry_is_answered_from_the_stored_response(
        self, owner, corrected, send, media_root, monkeypatch
    ) -> None:
        first = send(owner, corrected, key="v2")
        monkeypatch.setattr(IdempotencyScope, "find", lambda self: None)
        monkeypatch.setattr(views_module, "ensure_requires_corrections", lambda *args, **kwargs: None)

        second = send(owner, corrected, key="v2")

        assert second.status_code == 201 and second.json() == first.json()
        assert second["Idempotent-Replayed"] == "true"
        assert ManuscriptVersion.objects.filter(manuscript=corrected).count() == 2
        assert list((media_root / "tmp" / "uploads").glob("*")) == []


def save(pdf: pikepdf.Pdf, path: Path) -> Path:
    pdf.save(path)
    return path


class TestSanitizationDepth:
    def test_xmp_hanging_from_a_non_root_object_is_removed(self, tmp_path) -> None:
        pdf = pikepdf.new()
        pdf.add_blank_page()
        image = pdf.make_stream(b"datos")
        xmp = pdf.make_stream(b"<x:xmpmeta>Ana Lopez</x:xmpmeta>")
        xmp.Type, xmp.Subtype = Name.Metadata, Name.XML
        image.Metadata = xmp
        pdf.pages[0].Resources.XObject = Dictionary(Im1=image)
        source = save(pdf, tmp_path / "origen.pdf")
        destination = tmp_path / "sanitizada.pdf"

        PdfService().sanitize(source, destination)

        # Los flujos van comprimidos: se busca el XMP ya decodificado.
        def decoded_streams(path):
            with pikepdf.open(path) as opened:
                return [
                    obj.read_bytes() for obj in opened.objects if isinstance(obj, pikepdf.Stream)
                ]

        assert any(b"Ana Lopez" in data for data in decoded_streams(source))
        assert not any(b"xmpmeta" in data or b"Ana Lopez" in data for data in decoded_streams(destination))
        with pikepdf.open(destination) as result:
            assert "/Metadata" not in result.pages[0].Resources.XObject.Im1

    def test_an_embedded_file_stream_is_active_content(self, tmp_path) -> None:
        pdf = pikepdf.new()
        pdf.add_blank_page()
        attachment = pdf.make_stream(b"ejecutable")
        attachment.Type = Name.EmbeddedFile
        pdf.Root.Adjunto = attachment
        path = save(pdf, tmp_path / "adjunto.pdf")

        with pikepdf.open(path) as opened:
            assert find_active_content(opened) == ["/EmbeddedFiles"]
        with pytest.raises(PdfInvalid) as raised:
            PdfService().validate(path)
        assert raised.value.error_details == {"active_content": ["/EmbeddedFiles"]}


class TestStorageCleanup:
    def test_a_file_that_cannot_be_deleted_never_breaks_the_caller(self, tmp_path, monkeypatch) -> None:
        stuck = tmp_path / "bloqueado.part"
        stuck.write_bytes(b"x")

        def refuse(self, missing_ok=False):
            raise PermissionError("sin permiso")

        monkeypatch.setattr(Path, "unlink", refuse)

        remove_quietly(stuck)  # solo registra una advertencia

        assert stuck.exists()

    def test_nothing_to_delete_is_fine(self) -> None:
        remove_quietly(None)


class TestUnchangedAuthors:
    def test_resending_the_same_author_list_is_a_no_op(self, owner) -> None:
        from apps.audit.models import AuditLog
        from tests.publications.test_manuscript_api import detail_url, owned_manuscript

        manuscript = owned_manuscript(owner)
        same = [{
            "full_name": owner.get_full_name(), "email": owner.email,
            "affiliation": "UNL", "is_corresponding": True,
        }]

        response = client_for(owner).patch(
            detail_url(manuscript), {"authors": same}, format="json", HTTP_IF_MATCH='"0"'
        )

        assert response.status_code == 200 and response["ETag"] == '"0"'
        manuscript.refresh_from_db()
        assert manuscript.lock_version == 0 and manuscript.authors.count() == 1
        assert not AuditLog.objects.filter(action="MANUSCRIPT_UPDATED").exists()


class TestDefensiveBranches:
    def test_an_empty_author_list_is_refused(self) -> None:
        with pytest.raises(ValueError, match="al menos un autor"):
            validate_author_roster([], "alguien@unl.edu.ec")

    def test_a_user_with_no_manuscript_role_has_an_empty_scope(self) -> None:
        ManuscriptFactory()

        scope = Manuscript.objects.visible_to(UserFactory(), as_author=False, as_editor=False)

        assert list(scope) == []

    def test_the_manuscript_is_found_through_a_chain_of_relations(self) -> None:
        manuscript = ManuscriptFactory()
        version = SimpleNamespace(manuscript=manuscript)
        review = SimpleNamespace(version=version, manuscript=SimpleNamespace(manuscript=version))

        assert resolve_manuscript(version) is manuscript
        assert resolve_manuscript(review) is manuscript

    def test_a_chain_that_never_reaches_a_manuscript_gives_up(self) -> None:
        deep = SimpleNamespace()
        for _ in range(8):
            deep = SimpleNamespace(manuscript=deep)

        assert resolve_manuscript(deep) is None
        assert resolve_manuscript(None) is None


class TestFactories:
    def test_a_manuscript_is_a_valid_draft_with_a_sequence_code(self) -> None:
        first, second = ManuscriptFactory(), ManuscriptFactory()

        assert first.status == "DRAFT" and first.is_active
        assert first.code != second.code and first.code.startswith("GPC-")
        assert first.keywords == ["clima", "cultivos"]
        assert str(first) == f"{first.code} · {first.title}"

    def test_a_stored_idempotency_key_describes_itself(self, owner) -> None:
        from datetime import timedelta

        from django.utils import timezone

        from apps.publications.models import IdempotencyKey

        row = IdempotencyKey.objects.create(
            user=owner, endpoint="POST /api/x/", key="k1", request_hash="a" * 64,
            response_status=201, response_body={}, expires_at=timezone.now() + timedelta(hours=1),
        )

        assert str(row) == "POST /api/x/ · k1"

    def test_each_call_gets_its_own_keywords_list(self) -> None:
        first, second = ManuscriptFactory(), ManuscriptFactory()

        first.keywords.append("otra")

        assert second.keywords == ["clima", "cultivos"]

    def test_authors_get_distinct_orders_and_emails(self) -> None:
        manuscript = ManuscriptFactory()

        authors = [ManuscriptAuthorFactory(manuscript=manuscript) for _ in range(3)]

        assert len({a.author_order for a in authors}) == 3 and len({a.email for a in authors}) == 3
        assert str(authors[0]) == f"{authors[0].full_name} ({manuscript.pk})"

    def test_a_version_has_valid_hashes_paths_and_the_owner_as_submitter(self) -> None:
        version = ManuscriptVersionFactory()

        assert version.submitted_by == version.manuscript.created_by
        assert len(version.original_sha256) == len(version.sanitized_sha256) == len(version.metadata_sha256) == 64
        assert version.original_file_path == f"manuscripts/{version.manuscript.pk}/v0001/original.pdf"
        assert version.metadata_snapshot == {"title": version.manuscript.title}
        assert str(version) == f"{version.manuscript_id} · v1"

    def test_rounds_and_events_build_on_a_manuscript(self) -> None:
        manuscript = ManuscriptFactory()

        opened = CorrectionRoundFactory(manuscript=manuscript, round_number=1)
        event = StatusEventFactory(manuscript=manuscript)

        assert opened.closed_by_version is None and str(opened) == f"{manuscript.pk} · ronda 1"
        assert (event.from_status, event.to_status) == (None, "DRAFT")
        assert str(event) == f"{manuscript.pk}: None → DRAFT"
