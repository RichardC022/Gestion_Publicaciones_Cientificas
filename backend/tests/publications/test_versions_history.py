"""Tests for the version list, the original download and the history (TSK-38).

Covers the acceptance criteria:

1. The owning author and the editor receive ``original.pdf`` (through
   ``X-Accel-Redirect``); the reviewer never reaches this endpoint — it
   has its own that serves the sanitized copy.
2. A foreign or out-of-scope manuscript answers ``404``, not ``403``.
3. If the download audit fails the answer is ``503`` and no
   ``X-Accel-Redirect`` is emitted.

Plus HU-23: a chronological, immutable history that survives a logical
withdrawal and shows no partial iteration.
"""

from __future__ import annotations

import hashlib

import pytest
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.audit.services import AuditService, AuditUnavailable
from apps.publications.models import Manuscript, ManuscriptAuthor, ManuscriptVersion
from apps.publications.services import versions as versions_module
from tests.publications import pdf_factory as factory
from tests.publications.test_draft_file import pdf_file
from tests.publications.test_manuscript_api import (  # noqa: F401
    actor,
    client_for,
    detail_url,
    error_code,
    owned_manuscript,
)
from tests.publications.test_new_version import (  # noqa: F401
    request_corrections,
    send,
)
from tests.publications.test_submission import (  # noqa: F401
    media_root,
    owner,
    ready_draft,
    seeded_roles,
    submit,
    version_dir_of,
)
from tests.publications.test_withdraw import withdraw  # noqa: F401

pytestmark = pytest.mark.django_db

V1_PDF = factory.pdf_with_identity()
V2_PDF = factory.clean_pdf(pages=2)


def versions_url(manuscript) -> str:
    return f"{detail_url(manuscript)}versions/"


def file_url(manuscript, version) -> str:
    return f"{versions_url(manuscript)}{version.pk}/file/"


def history_url(manuscript) -> str:
    return f"{detail_url(manuscript)}history/"


@pytest.fixture
def iterated(owner, submit, send) -> Manuscript:
    """A manuscript with v1 (round 0) and v2 (round 1)."""
    manuscript = ready_draft(owner, pdf=V1_PDF, name="Ana Lopez - primera.pdf")
    assert submit(owner, manuscript).status_code == 201
    request_corrections(manuscript)
    assert send(owner, manuscript, pdf_file(V2_PDF, name="segunda.pdf")).status_code == 201
    manuscript.refresh_from_db()
    return manuscript


def version_of(manuscript, number: int) -> ManuscriptVersion:
    return ManuscriptVersion.objects.get(manuscript=manuscript, version_number=number)


class TestVersionList:
    def test_the_owner_lists_every_iteration_oldest_first(self, owner, iterated) -> None:
        response = client_for(owner).get(versions_url(iterated))

        assert response.status_code == 200
        body = response.json()
        assert body["count"] == 2
        assert [v["version_number"] for v in body["results"]] == [1, 2]
        assert [v["round_number"] for v in body["results"]] == [0, 1]
        assert [v["original_filename"] for v in body["results"]] == [
            "Ana Lopez - primera.pdf",
            "segunda.pdf",
        ]
        assert body["results"][0]["original_sha256"] == hashlib.sha256(V1_PDF).hexdigest()
        assert body["results"][1]["original_sha256"] == hashlib.sha256(V2_PDF).hexdigest()
        assert body["results"][1]["id"] == str(version_of(iterated, 2).pk)

    def test_the_editor_gets_the_same_list(self, owner, iterated) -> None:
        mine = client_for(owner).get(versions_url(iterated)).json()
        theirs = client_for(actor("EDITOR")).get(versions_url(iterated)).json()

        assert theirs == mine

    def test_rows_expose_no_paths_no_sanitized_hash_and_no_snapshot(self, owner, iterated) -> None:
        row = client_for(owner).get(versions_url(iterated)).json()["results"][0]

        assert set(row) == {
            "id", "version_number", "round_number", "original_filename",
            "original_size_bytes", "original_sha256", "submitted_at",
        }
        text = str(row)
        for forbidden in ("private", "sanitized", "metadata_snapshot", "submitted_by"):
            assert forbidden not in text

    def test_the_list_is_paginated(self, owner, iterated) -> None:
        body = client_for(owner).get(versions_url(iterated), {"page_size": 1}).json()

        assert body["count"] == 2 and len(body["results"]) == 1 and body["next"]
        assert client_for(owner).get(versions_url(iterated), {"page_size": 101}).status_code == 400

    def test_a_draft_has_no_iterations_for_its_author_and_is_hidden_from_the_editor(self, owner) -> None:
        draft = owned_manuscript(owner)

        assert client_for(owner).get(versions_url(draft)).json()["results"] == []
        assert client_for(actor("EDITOR")).get(versions_url(draft)).status_code == 404

    def test_the_archived_manuscript_keeps_its_versions_available(self, owner, iterated, withdraw) -> None:
        withdraw(owner, iterated, {"reason": "Retiro."})

        assert client_for(owner).get(versions_url(iterated)).json()["count"] == 2
        assert client_for(actor("EDITOR")).get(versions_url(iterated)).json()["count"] == 2


class TestOriginalDownload:
    def test_the_owner_gets_an_empty_200_that_redirects_to_the_original(self, owner, iterated) -> None:
        response = client_for(owner).get(file_url(iterated, version_of(iterated, 1)))

        assert response.status_code == 200
        assert response.content == b""
        assert response["X-Accel-Redirect"] == f"/_protected/manuscripts/{iterated.pk}/v0001/original.pdf"
        assert response["Content-Type"] == "application/pdf"

    def test_the_editor_gets_the_original_of_any_version(self, iterated) -> None:
        editor = client_for(actor("EDITOR"))

        first = editor.get(file_url(iterated, version_of(iterated, 1)))
        second = editor.get(file_url(iterated, version_of(iterated, 2)))

        assert first["X-Accel-Redirect"].endswith("/v0001/original.pdf")
        assert second["X-Accel-Redirect"].endswith("/v0002/original.pdf")

    def test_the_internal_path_resolves_to_the_exact_file_and_never_to_the_sanitized_copy(
        self, owner, iterated, media_root
    ) -> None:
        for number, expected in ((1, V1_PDF), (2, V2_PDF)):
            response = client_for(owner).get(
                file_url(iterated, version_of(iterated, number)), {"kind": "sanitized"}
            )

            internal = response["X-Accel-Redirect"]
            assert internal.startswith("/_protected/") and "sanitized" not in internal
            served = media_root / "private" / internal.removeprefix("/_protected/")
            assert served.read_bytes() == expected

    def test_headers_forbid_sniffing_and_caching_and_hide_the_uploaded_name(self, owner, iterated) -> None:
        response = client_for(owner).get(file_url(iterated, version_of(iterated, 1)))

        assert response["Content-Disposition"] == f'attachment; filename="{iterated.code}-v1.pdf"'
        assert response["X-Content-Type-Options"] == "nosniff"
        assert response["Cache-Control"] == "private, no-store"
        assert "Ana" not in str(response.headers)

    def test_each_download_is_audited_before_answering(self, owner, iterated) -> None:
        v1 = version_of(iterated, 1)
        client_for(owner).get(file_url(iterated, v1))
        client_for(actor("EDITOR")).get(file_url(iterated, v1))

        rows = list(AuditLog.objects.filter(action="MANUSCRIPT_FILE_DOWNLOADED").order_by("id"))
        assert [r.actor_role for r in rows] == ["AUTHOR", "EDITOR"]
        assert rows[0].actor_id == owner.pk and rows[0].request_id
        assert all(r.entity_type == "MANUSCRIPT_VERSION" and r.entity_id == v1.pk for r in rows)
        assert rows[0].details == {
            "manuscript_id": str(iterated.pk), "version_number": 1, "kind": "original",
        }
        assert "Ana" not in str(rows[0].details)

    def test_audit_failure_answers_503_without_redirect(self, owner, iterated, monkeypatch) -> None:
        def fail(**kwargs):
            raise AuditUnavailable("sin auditoría")

        monkeypatch.setattr(AuditService, "record", staticmethod(fail))

        response = client_for(owner).get(file_url(iterated, version_of(iterated, 1)))

        assert response.status_code == 503 and error_code(response) == "AUDIT_UNAVAILABLE"
        assert "X-Accel-Redirect" not in response.headers
        assert not AuditLog.objects.filter(action="MANUSCRIPT_FILE_DOWNLOADED").exists()

    def test_a_missing_file_answers_503_without_redirect_and_without_a_download_record(
        self, owner, iterated, media_root
    ) -> None:
        (version_dir_of(media_root, iterated, 1) / "original.pdf").unlink()

        response = client_for(owner).get(file_url(iterated, version_of(iterated, 1)))

        assert response.status_code == 503 and error_code(response) == "STORAGE_UNAVAILABLE"
        assert "X-Accel-Redirect" not in response.headers
        assert not AuditLog.objects.filter(action="MANUSCRIPT_FILE_DOWNLOADED").exists()

    def test_a_withdrawn_manuscript_can_still_be_downloaded_by_owner_and_editor(self, owner, iterated, withdraw) -> None:
        withdraw(owner, iterated, {"reason": "Retiro."})
        v2 = version_of(iterated, 2)

        assert client_for(owner).get(file_url(iterated, v2)).status_code == 200
        assert client_for(actor("EDITOR")).get(file_url(iterated, v2)).status_code == 200

    def test_download_is_read_only(self, owner, iterated) -> None:
        url = file_url(iterated, version_of(iterated, 1))
        client = client_for(owner)

        assert client.post(url, {}, format="json").status_code == 405
        assert client.delete(url).status_code == 405
        assert ManuscriptVersion.objects.filter(manuscript=iterated).count() == 2


class TestScopeAnswers404:
    def test_someone_elses_manuscript_never_reveals_itself(self, iterated) -> None:
        stranger = client_for(actor("AUTHOR"))
        v1 = version_of(iterated, 1)

        for url in (versions_url(iterated), file_url(iterated, v1), history_url(iterated)):
            response = stranger.get(url)
            assert response.status_code == 404 and error_code(response) == "NOT_FOUND"
        assert not AuditLog.objects.filter(action="MANUSCRIPT_FILE_DOWNLOADED").exists()

    def test_a_version_of_another_manuscript_is_not_found_under_this_one(self, owner, iterated, submit) -> None:
        other = ready_draft(owner, pdf=factory.clean_pdf(pages=3), name="otro.pdf")
        submit(owner, other)

        response = client_for(owner).get(file_url(iterated, version_of(other, 1)))

        assert response.status_code == 404

    def test_an_unknown_version_answers_404(self, owner, iterated) -> None:
        url = f"{versions_url(iterated)}00000000-0000-0000-0000-000000000000/file/"

        assert client_for(owner).get(url).status_code == 404

    def test_an_editor_with_a_conflict_of_interest_never_reaches_it(self, iterated) -> None:
        editor = actor("EDITOR")
        ManuscriptAuthor.objects.create(
            manuscript=iterated, user=editor, full_name="Editor Coautor",
            email=editor.email, affiliation="UNL", author_order=9,
        )
        client = client_for(editor)

        for url in (versions_url(iterated), file_url(iterated, version_of(iterated, 1)), history_url(iterated)):
            assert client.get(url).status_code == 404

    def test_a_draft_download_is_hidden_from_the_editor(self, owner, submit) -> None:
        manuscript = ready_draft(owner)
        submit(owner, manuscript)
        Manuscript.objects.filter(pk=manuscript.pk).update(status="DRAFT")
        version = version_of(manuscript, 1)

        assert client_for(actor("EDITOR")).get(file_url(manuscript, version)).status_code == 404
        assert client_for(owner).get(file_url(manuscript, version)).status_code == 200


class TestModuleAccess:
    @pytest.mark.parametrize("which", ["versions", "file", "history"])
    def test_anonymous_answers_401(self, iterated, which) -> None:
        from rest_framework.test import APIClient

        urls = {
            "versions": versions_url(iterated),
            "file": file_url(iterated, version_of(iterated, 1)),
            "history": history_url(iterated),
        }

        assert APIClient().get(urls[which]).status_code == 401

    @pytest.mark.parametrize("roles", [("REVIEWER",), ("ADMIN",), ()])
    @pytest.mark.parametrize("which", ["versions", "file", "history"])
    def test_roles_outside_the_module_answer_403_and_never_get_the_original(self, iterated, roles, which) -> None:
        urls = {
            "versions": versions_url(iterated),
            "file": file_url(iterated, version_of(iterated, 1)),
            "history": history_url(iterated),
        }

        response = client_for(actor(*roles)).get(urls[which])

        assert response.status_code == 403
        assert "X-Accel-Redirect" not in response.headers
        assert not AuditLog.objects.filter(action="MANUSCRIPT_FILE_DOWNLOADED").exists()

    def test_a_reviewer_who_is_also_the_author_reaches_it_only_as_the_author(self, iterated, owner) -> None:
        # Tener el rol de Revisor no abre el original de un manuscrito ajeno.
        person = actor("AUTHOR", "REVIEWER")
        v1 = version_of(iterated, 1)

        assert client_for(person).get(file_url(iterated, v1)).status_code == 404

    def test_revoked_role_blocks_the_next_request(self, owner, iterated) -> None:
        client = client_for(owner)
        assert client.get(history_url(iterated)).status_code == 200

        owner.role_assignments.update(is_active=False, revoked_at=timezone.now())

        assert client.get(history_url(iterated)).status_code == 403


def types(entries) -> list[str]:
    return [entry["type"] for entry in entries]


class TestHistory:
    def test_the_timeline_is_chronological_and_complete(self, owner, iterated) -> None:
        entries = client_for(owner).get(history_url(iterated)).json()["results"]

        stamps = [e["occurred_at"] for e in entries]
        assert stamps == sorted(stamps)
        assert types(entries) == [
            "CREATED",
            "VERSION_SUBMITTED", "ROUND_OPENED", "STATUS_CHANGED",
            "ROUND_OPENED",
            "VERSION_SUBMITTED", "STATUS_CHANGED",
        ]

    def test_the_initial_entry_has_no_previous_status(self, owner, iterated) -> None:
        first = client_for(owner).get(history_url(iterated)).json()["results"][0]

        assert (first["type"], first["from_status"], first["to_status"]) == ("CREATED", None, "DRAFT")

    def test_status_changes_carry_the_version_and_round(self, owner, iterated) -> None:
        entries = client_for(owner).get(history_url(iterated)).json()["results"]
        changes = [e for e in entries if e["type"] == "STATUS_CHANGED"]

        assert [(c["from_status"], c["to_status"]) for c in changes] == [
            ("DRAFT", "SUBMITTED"), ("REQUIRES_CORRECTIONS", "SUBMITTED"),
        ]
        assert [(c["version_number"], c["round_number"]) for c in changes] == [(1, 0), (2, 1)]

    def test_each_iteration_keeps_its_exact_pdf_seal_and_metadata_seal(self, owner, iterated) -> None:
        entries = client_for(owner).get(history_url(iterated)).json()["results"]
        versions = [e for e in entries if e["type"] == "VERSION_SUBMITTED"]

        for entry, number, pdf in zip(versions, (1, 2), (V1_PDF, V2_PDF)):
            row = version_of(iterated, number)
            assert entry["version_id"] == str(row.pk) and entry["version_number"] == number
            assert entry["integrity_seal"] == f"sha256:{hashlib.sha256(pdf).hexdigest()}"
            assert entry["metadata_sha256"] == row.metadata_sha256
            assert entry["original_size_bytes"] == len(pdf)
        assert versions[0]["integrity_seal"] != versions[1]["integrity_seal"]

    def test_same_metadata_with_another_pdf_keeps_two_separate_records(self, owner, iterated) -> None:
        versions = [
            e for e in client_for(owner).get(history_url(iterated)).json()["results"]
            if e["type"] == "VERSION_SUBMITTED"
        ]

        assert versions[0]["metadata_sha256"] == versions[1]["metadata_sha256"]
        assert versions[0]["integrity_seal"] != versions[1]["integrity_seal"]
        assert versions[0]["version_id"] != versions[1]["version_id"]

    def test_rounds_show_the_version_that_closed_them(self, owner, iterated) -> None:
        rounds = [
            e for e in client_for(owner).get(history_url(iterated)).json()["results"]
            if e["type"] == "ROUND_OPENED"
        ]

        assert [(r["round_number"], r["closed_by_version_number"]) for r in rounds] == [(0, 1), (1, 2)]
        assert all(r["closed_at"] for r in rounds)

    def test_an_open_round_is_listed_without_a_closing_version(self, owner, submit) -> None:
        manuscript = ready_draft(owner)
        submit(owner, manuscript)
        request_corrections(manuscript)

        rounds = [
            e for e in client_for(owner).get(history_url(manuscript)).json()["results"]
            if e["type"] == "ROUND_OPENED"
        ]

        assert (rounds[1]["round_number"], rounds[1]["closed_at"], rounds[1]["closed_by_version_number"]) == (1, None, None)

    def test_entries_show_no_actor_path_or_sanitized_data(self, owner, iterated) -> None:
        text = str(client_for(owner).get(history_url(iterated)).json())

        for forbidden in ("actor", "private", "sanitized", "metadata_snapshot", "submitted_by", owner.email):
            assert forbidden not in text

    def test_the_editor_reads_the_same_timeline(self, owner, iterated) -> None:
        mine = client_for(owner).get(history_url(iterated)).json()
        theirs = client_for(actor("EDITOR")).get(history_url(iterated)).json()

        assert theirs == mine

    def test_the_history_survives_a_withdrawal_and_records_it(self, owner, iterated, withdraw) -> None:
        before = client_for(owner).get(history_url(iterated)).json()["results"]

        withdraw(owner, iterated, {"reason": "Ya no deseo continuar."})
        after = client_for(owner).get(history_url(iterated)).json()["results"]
        editor_view = client_for(actor("EDITOR")).get(history_url(iterated)).json()["results"]

        assert after[: len(before)] == before
        assert types(after)[-1] == "WITHDRAWN"
        assert (after[-1]["reason"], after[-1]["to_status"]) == ("Ya no deseo continuar.", "SUBMITTED")
        assert editor_view == after

    def test_new_activity_only_appends_and_never_rewrites_what_was_recorded(self, owner, submit, send) -> None:
        manuscript = ready_draft(owner, pdf=V1_PDF)
        submit(owner, manuscript)
        request_corrections(manuscript)
        before = client_for(owner).get(history_url(manuscript)).json()["results"]

        send(owner, manuscript, pdf_file(V2_PDF))
        after = client_for(owner).get(history_url(manuscript)).json()["results"]

        changed_round = {e["round_number"]: e for e in after if e["type"] == "ROUND_OPENED"}[1]
        stable = [e for e in before if not (e["type"] == "ROUND_OPENED" and e["round_number"] == 1)]
        assert all(e in after for e in stable)
        assert changed_round["closed_by_version_number"] == 2

    def test_a_draft_only_shows_its_creation(self, owner) -> None:
        draft = owned_manuscript(owner)
        from apps.publications.models import StatusEvent

        StatusEvent.objects.create(manuscript=draft, to_status="DRAFT", actor=owner)

        assert types(client_for(owner).get(history_url(draft)).json()["results"]) == ["CREATED"]

    def test_an_interrupted_submission_leaves_no_partial_iteration(self, owner, submit, monkeypatch) -> None:
        manuscript = ready_draft(owner)

        def disk_full(source, destination):
            raise OSError("No space left on device")

        monkeypatch.setattr(versions_module, "copy_exclusive", disk_full)
        assert submit(owner, manuscript).status_code == 503

        entries = client_for(owner).get(history_url(manuscript)).json()["results"]
        assert types(entries) == ["CREATED"]

    def test_the_history_is_paginated(self, owner, iterated) -> None:
        body = client_for(owner).get(history_url(iterated), {"page_size": 3}).json()

        assert body["count"] == 7 and len(body["results"]) == 3 and body["next"]
        second = client_for(owner).get(history_url(iterated), {"page_size": 3, "page": 2}).json()
        assert second["results"][0]["type"] == "STATUS_CHANGED"

    def test_history_is_read_only(self, owner, iterated) -> None:
        client = client_for(owner)

        for method in (client.post, client.put, client.patch):
            assert method(history_url(iterated), {}, format="json").status_code == 405
        assert client.delete(history_url(iterated)).status_code == 405
