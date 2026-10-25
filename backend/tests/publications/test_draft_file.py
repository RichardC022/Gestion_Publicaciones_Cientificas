"""Tests for the draft PDF upload and replacement (TSK-34).

Covers the acceptance criteria:

1. Only the owning author, and only while the manuscript is a ``DRAFT``,
   can upload; any other state answers ``409``.
2. The upload creates no version, round or snapshot.
3. An invalid file, one over 50 MB or one with a wrong content type
   answers ``400``/``413``/``415`` and the staged temporary is removed.

Plus the contracts of the plan: UUID-only paths, mode ``0640``, the
previous draft deleted on replacement, and a full rollback (file and
database) when the audit trail is unavailable.
"""

from __future__ import annotations

import stat

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.audit.services import AuditService, AuditUnavailable
from apps.publications.models import (
    CorrectionRound,
    Manuscript,
    ManuscriptVersion,
    StatusEvent,
)
from apps.publications.services import drafts
from apps.users.models import User
from config.exceptions import DomainError
from tests.publications import pdf_factory as factory
from tests.publications.test_manuscript_api import (
    URL,
    actor,
    client_for,
    create_payload,
    detail_url,
    error_code,
    owned_manuscript,
)

pytestmark = pytest.mark.django_db

MAX_BYTES = 50 * factory.MIB


@pytest.fixture(autouse=True)
def seeded_roles(db) -> None:
    call_command("seed_roles", verbosity=0)


@pytest.fixture(autouse=True)
def media_root(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    return tmp_path


def draft_url(manuscript) -> str:
    return f"{detail_url(manuscript)}draft-file/"


def pdf_file(data: bytes | None = None, name: str = "articulo.pdf", content_type: str = "application/pdf"):
    return SimpleUploadedFile(name, factory.clean_pdf() if data is None else data, content_type=content_type)


def upload(user, manuscript, file=None, **extra):
    return client_for(user).post(
        draft_url(manuscript),
        {"file": pdf_file() if file is None else file},
        format="multipart",
        **extra,
    )


def drafts_on_disk(media_root) -> list:
    return sorted((media_root / "private" / "drafts").rglob("*.pdf"))


def staged_files(media_root) -> list:
    folder = media_root / "tmp" / "uploads"
    return sorted(folder.glob("*")) if folder.exists() else []


@pytest.fixture
def owner() -> User:
    return actor("AUTHOR")


@pytest.fixture
def draft(owner) -> Manuscript:
    return owned_manuscript(owner)


class TestUpload:
    def test_first_upload_answers_201_with_name_size_and_date(self, owner, draft, media_root) -> None:
        data = factory.clean_pdf(pages=2)

        response = upload(owner, draft, pdf_file(data, name="mi articulo.pdf"))

        assert response.status_code == 201
        assert response.json()["filename"] == "mi articulo.pdf"
        assert response.json()["size_bytes"] == len(data)
        assert response.json()["uploaded_at"]
        [stored] = drafts_on_disk(media_root)
        assert stored.read_bytes() == data

    def test_file_lives_under_the_user_and_a_draft_uuid_with_mode_0640(self, owner, draft, media_root) -> None:
        upload(owner, draft, pdf_file(name="Ana Lopez - tesis.pdf"))

        [stored] = drafts_on_disk(media_root)
        relative = stored.relative_to(media_root)
        assert relative.parts[:3] == ("private", "drafts", str(owner.pk))
        assert stat.S_IMODE(stored.stat().st_mode) == 0o640
        for leaked in ("Ana", "tesis", owner.email, draft.title):
            assert leaked not in str(relative)

    def test_the_manuscript_points_to_the_file_and_the_api_hides_the_path(self, owner, draft, media_root) -> None:
        upload(owner, draft)

        draft.refresh_from_db()
        assert draft.draft_file_path == str(drafts_on_disk(media_root)[0].relative_to(media_root))
        body = client_for(owner).get(detail_url(draft)).json()
        assert set(body["draft_file"]) == {"filename", "size_bytes", "uploaded_at"}
        assert "private" not in str(body)

    def test_manuscript_without_draft_reports_none(self, owner, draft) -> None:
        assert client_for(owner).get(detail_url(draft)).json()["draft_file"] is None

    def test_upload_creates_no_version_round_or_snapshot(self, owner) -> None:
        client = client_for(owner)
        created = client.post(URL, create_payload(owner), format="json").json()
        manuscript = Manuscript.objects.get(pk=created["id"])
        events_before = StatusEvent.objects.count()

        assert upload(owner, manuscript).status_code == 201

        manuscript.refresh_from_db()
        assert not ManuscriptVersion.objects.exists()
        assert not CorrectionRound.objects.exists()
        assert StatusEvent.objects.count() == events_before
        assert (manuscript.current_version, manuscript.current_round) == (0, 0)
        assert manuscript.status == "DRAFT"

    def test_upload_does_not_invalidate_the_etag_of_the_metadata(self, owner, draft) -> None:
        upload(owner, draft)

        response = client_for(owner).patch(
            detail_url(draft), {"title": "Sigue editable"}, format="json", HTTP_IF_MATCH='"0"'
        )

        assert response.status_code == 200

    def test_upload_is_audited_without_the_file_name(self, owner, draft) -> None:
        data = factory.clean_pdf()

        upload(owner, draft, pdf_file(data, name="Ana Lopez.pdf"))

        audit = AuditLog.objects.get(action="MANUSCRIPT_DRAFT_FILE_UPLOADED")
        assert audit.entity_id == draft.pk and audit.actor_id == owner.pk
        assert audit.actor_role == "AUTHOR" and audit.request_id
        assert audit.details == {"size_bytes": len(data), "replaced": False}

    def test_the_staging_area_is_empty_after_a_successful_upload(self, owner, draft, media_root) -> None:
        upload(owner, draft)

        assert staged_files(media_root) == []

    def test_extension_is_matched_ignoring_case(self, owner, draft) -> None:
        assert upload(owner, draft, pdf_file(name="ARTICULO.PDF")).status_code == 201

    @pytest.mark.parametrize("content_type", ["application/pdf", "application/x-pdf", "application/octet-stream", ""])
    def test_usual_declared_types_are_accepted(self, owner, draft, content_type) -> None:
        assert upload(owner, draft, pdf_file(content_type=content_type)).status_code == 201


class TestReplacement:
    def test_second_upload_answers_200_and_deletes_the_previous_file(self, owner, draft, media_root) -> None:
        upload(owner, draft, pdf_file(factory.clean_pdf(pages=1), name="primero.pdf"))
        [first] = drafts_on_disk(media_root)
        second_data = factory.clean_pdf(pages=4)

        response = upload(owner, draft, pdf_file(second_data, name="segundo.pdf"))

        assert response.status_code == 200
        assert response.json()["filename"] == "segundo.pdf"
        [current] = drafts_on_disk(media_root)
        assert current != first and not first.exists()
        assert current.read_bytes() == second_data
        draft.refresh_from_db()
        assert draft.draft_filename == "segundo.pdf" and draft.draft_size_bytes == len(second_data)

    def test_replacement_is_audited_as_such(self, owner, draft) -> None:
        upload(owner, draft)
        upload(owner, draft)

        actions = list(AuditLog.objects.filter(entity_id=draft.pk).order_by("id").values_list("action", flat=True))
        assert actions == ["MANUSCRIPT_DRAFT_FILE_UPLOADED", "MANUSCRIPT_DRAFT_FILE_REPLACED"]
        assert AuditLog.objects.get(action="MANUSCRIPT_DRAFT_FILE_REPLACED").details["replaced"] is True

    def test_replacement_never_creates_a_version(self, owner, draft) -> None:
        upload(owner, draft)
        upload(owner, draft)

        assert not ManuscriptVersion.objects.exists() and not CorrectionRound.objects.exists()

    def test_each_manuscript_keeps_its_own_draft(self, owner, media_root) -> None:
        first, second = owned_manuscript(owner), owned_manuscript(owner)

        upload(owner, first)
        upload(owner, second)

        assert len(drafts_on_disk(media_root)) == 2


class TestState:
    @pytest.mark.parametrize(
        "status", ["SUBMITTED", "UNDER_REVIEW", "REQUIRES_CORRECTIONS", "ACCEPTED", "REJECTED"]
    )
    def test_any_other_state_answers_409_and_stores_nothing(self, owner, media_root, status) -> None:
        manuscript = owned_manuscript(owner, status=status)

        response = upload(owner, manuscript)

        assert response.status_code == 409
        assert error_code(response) == "STATE_CONFLICT"
        assert response.json()["error"]["details"]["status"] == status
        assert drafts_on_disk(media_root) == [] and staged_files(media_root) == []

    def test_state_is_checked_before_the_body_is_parsed(self, owner) -> None:
        manuscript = owned_manuscript(owner, status="SUBMITTED")

        response = client_for(owner).post(draft_url(manuscript), {"x": 1}, format="json")

        assert response.status_code == 409

    def test_a_withdrawn_draft_answers_409(self, owner, draft) -> None:
        Manuscript.objects.filter(pk=draft.pk).update(is_active=False, withdrawn_at=timezone.now())

        assert upload(owner, draft).status_code == 409

    def test_state_changed_while_uploading_rolls_the_file_back(self, owner, draft, media_root) -> None:
        # El estado cambia entre la validación de la vista y el bloqueo de fila.
        Manuscript.objects.filter(pk=draft.pk).update(status="SUBMITTED")

        with pytest.raises(DomainError) as raised:
            drafts.attach_draft_file(
                manuscript_id=draft.pk, user=owner, uploaded=pdf_file(), context={}
            )

        assert raised.value.status_code == 409
        assert drafts_on_disk(media_root) == [] and staged_files(media_root) == []
        draft.refresh_from_db()
        assert draft.draft_file_path is None


class TestAccess:
    def test_anonymous_answers_401(self, draft) -> None:
        from rest_framework.test import APIClient

        response = APIClient().post(draft_url(draft), {"file": pdf_file()}, format="multipart")

        assert response.status_code == 401

    @pytest.mark.parametrize("roles", [("EDITOR",), ("REVIEWER",), ("ADMIN",), ()])
    def test_roles_without_the_author_module_answer_403(self, draft, roles) -> None:
        assert upload(actor(*roles), draft).status_code == 403

    def test_someone_elses_manuscript_answers_404(self, draft, media_root) -> None:
        response = upload(actor("AUTHOR"), draft)

        assert response.status_code == 404
        assert error_code(response) == "NOT_FOUND"
        assert drafts_on_disk(media_root) == []

    def test_multirole_user_cannot_upload_to_a_manuscript_seen_as_editor(self, media_root) -> None:
        person = actor("AUTHOR", "EDITOR")
        foreign = owned_manuscript(actor("AUTHOR"), status="SUBMITTED")

        assert upload(person, foreign).status_code == 404
        assert drafts_on_disk(media_root) == []

    def test_unknown_manuscript_answers_404(self, owner) -> None:
        response = client_for(owner).post(
            "/api/manuscripts/00000000-0000-0000-0000-000000000000/draft-file/",
            {"file": pdf_file()},
            format="multipart",
        )

        assert response.status_code == 404

    def test_revoked_role_blocks_the_next_upload(self, owner, draft) -> None:
        owner.role_assignments.update(is_active=False, revoked_at=timezone.now())

        assert upload(owner, draft).status_code == 403


class TestUnsupportedContentType:
    def test_json_body_answers_415(self, owner, draft, media_root) -> None:
        response = client_for(owner).post(draft_url(draft), {"file": "x"}, format="json")

        assert response.status_code == 415
        assert error_code(response) == "PDF_UNSUPPORTED"
        assert drafts_on_disk(media_root) == []

    def test_raw_pdf_body_answers_415(self, owner, draft) -> None:
        response = client_for(owner).post(
            draft_url(draft), factory.clean_pdf(), content_type="application/pdf"
        )

        assert response.status_code == 415

    def test_file_part_declared_as_another_type_answers_415(self, owner, draft, media_root) -> None:
        response = upload(owner, draft, pdf_file(content_type="image/png"))

        assert response.status_code == 415
        assert error_code(response) == "PDF_UNSUPPORTED"
        assert drafts_on_disk(media_root) == [] and staged_files(media_root) == []


class TestInvalidFile:
    def test_missing_file_field_answers_400(self, owner, draft) -> None:
        response = client_for(owner).post(draft_url(draft), {"otro": "x"}, format="multipart")

        assert response.status_code == 400
        assert error_code(response) == "VALIDATION_ERROR"

    def test_a_text_field_instead_of_a_file_answers_400(self, owner, draft) -> None:
        response = client_for(owner).post(draft_url(draft), {"file": "no soy un archivo"}, format="multipart")

        assert response.status_code == 400

    @pytest.mark.parametrize("name", ["articulo.txt", "articulo.docx", "articulo", "articulo.pdf.exe"])
    def test_only_the_pdf_extension_is_accepted(self, owner, draft, media_root, name) -> None:
        response = upload(owner, draft, pdf_file(name=name))

        assert response.status_code == 400
        assert error_code(response) == "PDF_INVALID"
        assert drafts_on_disk(media_root) == []

    @pytest.mark.parametrize(
        "data",
        [
            pytest.param(b"", id="vacio"),
            pytest.param(b"Esto es texto plano", id="texto-con-extension-pdf"),
            pytest.param(factory.clean_pdf(pages=5)[:200], id="truncado"),
            pytest.param(factory.encrypted_pdf("clave"), id="cifrado"),
            pytest.param(factory.pdf_without_pages(), id="sin-paginas"),
            pytest.param(factory.pdf_with_active_content("/JavaScript"), id="javascript"),
            pytest.param(factory.pdf_with_active_content("/OpenAction"), id="openaction"),
        ],
    )
    def test_invalid_content_answers_400_and_removes_the_staged_temporary(self, owner, draft, media_root, data) -> None:
        response = upload(owner, draft, pdf_file(data))

        assert response.status_code == 400
        assert error_code(response) == "PDF_INVALID"
        assert staged_files(media_root) == []
        assert drafts_on_disk(media_root) == []
        draft.refresh_from_db()
        assert draft.draft_file_path is None
        assert not AuditLog.objects.filter(action__startswith="MANUSCRIPT_DRAFT").exists()

    def test_an_invalid_replacement_keeps_the_previous_draft(self, owner, draft, media_root) -> None:
        good = factory.clean_pdf(pages=2)
        upload(owner, draft, pdf_file(good, name="bueno.pdf"))
        [kept] = drafts_on_disk(media_root)

        response = upload(owner, draft, pdf_file(b"corrupto", name="malo.pdf"))

        assert response.status_code == 400
        assert drafts_on_disk(media_root) == [kept] and kept.read_bytes() == good
        draft.refresh_from_db()
        assert draft.draft_filename == "bueno.pdf"
        assert staged_files(media_root) == []


class TestSizeLimit:
    def test_one_byte_over_50_mb_answers_413_and_leaves_no_temporary(self, owner, draft, media_root) -> None:
        oversized = factory.pdf_of_size(MAX_BYTES) + b"\n"

        response = upload(owner, draft, pdf_file(oversized))

        assert response.status_code == 413
        assert error_code(response) == "PDF_TOO_LARGE"
        assert staged_files(media_root) == [] and drafts_on_disk(media_root) == []

    def test_exactly_50_mb_is_accepted(self, owner, draft, media_root) -> None:
        exact = factory.pdf_of_size(MAX_BYTES)

        response = upload(owner, draft, pdf_file(exact))

        assert response.status_code == 201
        assert response.json()["size_bytes"] == MAX_BYTES
        assert staged_files(media_root) == []


class TestAuditUnavailable:
    @staticmethod
    def break_audit(monkeypatch) -> None:
        def fail(**kwargs):
            raise AuditUnavailable("sin auditoria")

        monkeypatch.setattr(AuditService, "record", staticmethod(fail))

    def test_first_upload_rolls_back_file_and_database(self, owner, draft, media_root, monkeypatch) -> None:
        self.break_audit(monkeypatch)

        response = upload(owner, draft)

        assert response.status_code == 503
        assert error_code(response) == "AUDIT_UNAVAILABLE"
        assert drafts_on_disk(media_root) == [] and staged_files(media_root) == []
        draft.refresh_from_db()
        assert draft.draft_file_path is None

    def test_failed_replacement_keeps_the_previous_draft_intact(self, owner, draft, media_root, monkeypatch) -> None:
        original = factory.clean_pdf(pages=1)
        upload(owner, draft, pdf_file(original, name="vigente.pdf"))
        [kept] = drafts_on_disk(media_root)
        self.break_audit(monkeypatch)

        response = upload(owner, draft, pdf_file(factory.clean_pdf(pages=3), name="nuevo.pdf"))

        assert response.status_code == 503
        assert drafts_on_disk(media_root) == [kept] and kept.read_bytes() == original
        draft.refresh_from_db()
        assert draft.draft_filename == "vigente.pdf"
