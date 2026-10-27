"""Tests for the reviewer endpoints: inbox, detail and document (TSK-61).

Covers the acceptance criteria: the inbox only lists the reviewer's own
assignments and tells five states apart; the download uses a generic
name, never resolves ``original.pdf`` and answers ``410`` for a
non-``ACTIVE`` assignment; and it is audited, failing with ``503`` when
the audit trail is unavailable.

Plus the double-blind contract of the plan (section 2.9): a foreign
assignment, a withdrawn manuscript or one the reviewer co-authored answer
``404``, and no identifying value reaches the reviewer under any key.
The document tests go through the real submission flow, so the PDF on
disk is the sanitized copy the system produced.
"""

from __future__ import annotations

from datetime import timedelta

import pikepdf
import pytest
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.audit.services import AuditService, AuditUnavailable
from apps.publications.models import Manuscript
from apps.reviews.models import Assignment
from tests.factories import (
    AssignmentFactory,
    EvaluationFactory,
    FinalEvaluationFactory,
    ManuscriptAuthorFactory,
    ManuscriptFactory,
    ManuscriptVersionFactory,
    UserFactory,
)
from tests.publications import pdf_factory as factory
from tests.publications.test_manuscript_api import actor, client_for, error_code  # noqa: F401
from tests.publications.test_submission import (  # noqa: F401
    media_root,
    owner,
    ready_draft,
    seeded_roles,
    submit,
    version_dir_of,
)

pytestmark = pytest.mark.django_db

BASE = "/api/reviewer/assignments/"
AUTHOR_NAME = "Ana Lopez"
V1_PDF = factory.pdf_with_identity()


def detail_url(assignment) -> str:
    return f"{BASE}{assignment.pk}/"


def document_url(assignment) -> str:
    return f"{BASE}{assignment.pk}/document/"


@pytest.fixture
def reviewer():
    return actor("REVIEWER")


def own_assignment(reviewer, *, days_ago: int = 0, **manuscript_values) -> Assignment:
    """An assignment of the reviewer over a manuscript with a known author."""
    author = UserFactory()
    manuscript = ManuscriptFactory(
        status="UNDER_REVIEW", created_by=author, current_version=1, **manuscript_values
    )
    ManuscriptAuthorFactory(
        manuscript=manuscript,
        user=author,
        full_name=AUTHOR_NAME,
        email=author.email,
        is_corresponding=True,
        author_order=1,
    )
    version = ManuscriptVersionFactory(
        manuscript=manuscript, submitted_by=author, original_filename="ana-lopez-articulo.pdf"
    )
    return AssignmentFactory(
        manuscript=manuscript,
        version=version,
        reviewer=reviewer,
        assigned_at=timezone.now() - timedelta(days=days_ago),
    )


@pytest.fixture
def uploaded(owner, reviewer, submit) -> Assignment:
    """An ``ACTIVE`` assignment over a really submitted manuscript (files on disk)."""
    manuscript = ready_draft(owner, pdf=V1_PDF)
    assert submit(owner, manuscript).status_code == 201
    Manuscript.objects.filter(pk=manuscript.pk).update(status="UNDER_REVIEW")
    assigned_at = timezone.now()
    return Assignment.objects.create(
        manuscript=manuscript,
        version=manuscript.versions.get(version_number=1),
        reviewer=reviewer,
        assigned_by=actor("EDITOR"),
        assigned_at=assigned_at,
        due_at=assigned_at + timedelta(days=20),
    )


def set_status(assignment: Assignment, status: str) -> None:
    Assignment.objects.filter(pk=assignment.pk).update(status=status)


class TestAccess:
    @pytest.mark.parametrize("suffix", ["", "{id}/", "{id}/document/"])
    def test_anonymous_requests_answer_401(self, reviewer, suffix) -> None:
        assignment = own_assignment(reviewer)
        from rest_framework.test import APIClient

        response = APIClient().get(BASE + suffix.format(id=assignment.pk))

        assert response.status_code == 401

    @pytest.mark.parametrize("role", ["AUTHOR", "EDITOR", "ADMIN"])
    @pytest.mark.parametrize("suffix", ["", "{id}/", "{id}/document/"])
    def test_other_roles_answer_403(self, reviewer, role, suffix) -> None:
        assignment = own_assignment(reviewer)

        response = client_for(actor(role)).get(BASE + suffix.format(id=assignment.pk))

        assert response.status_code == 403

    def test_the_endpoints_are_read_only(self, reviewer) -> None:
        assignment = own_assignment(reviewer)
        client = client_for(reviewer)

        for url in (BASE, detail_url(assignment), document_url(assignment)):
            assert client.post(url, {}, format="json").status_code == 405
            assert client.delete(url).status_code == 405


class TestInbox:
    def test_lists_only_the_reviewers_own_assignments(self, reviewer) -> None:
        own = own_assignment(reviewer)
        own_assignment(actor("REVIEWER"))

        body = client_for(reviewer).get(BASE).json()

        assert body["count"] == 1
        assert body["results"][0]["id"] == str(own.pk)

    def test_an_empty_inbox_is_a_valid_answer(self, reviewer) -> None:
        body = client_for(reviewer).get(BASE).json()

        assert body["count"] == 0 and body["results"] == []

    def test_a_withdrawn_manuscript_and_a_coauthored_one_are_not_listed(self, reviewer) -> None:
        withdrawn = own_assignment(reviewer, is_active=False, withdrawn_at=timezone.now())
        coauthored = own_assignment(reviewer)
        ManuscriptAuthorFactory(manuscript=coauthored.manuscript, user=reviewer, author_order=2)
        visible = own_assignment(reviewer)

        ids = [row["id"] for row in client_for(reviewer).get(BASE).json()["results"]]

        assert ids == [str(visible.pk)]
        assert str(withdrawn.pk) not in ids and str(coauthored.pk) not in ids

    def test_the_five_states_are_told_apart(self, reviewer) -> None:
        pending = own_assignment(reviewer)
        on_time = own_assignment(reviewer)
        EvaluationFactory(assignment=on_time)
        overdue_active = own_assignment(reviewer, days_ago=25)
        expired = own_assignment(reviewer, days_ago=25)
        set_status(expired, "EXPIRED")
        evaluated = own_assignment(reviewer)
        FinalEvaluationFactory(assignment=evaluated)
        set_status(evaluated, "COMPLETED")
        revoked = own_assignment(reviewer)
        set_status(revoked, "REVOKED")

        rows = {
            row["id"]: row for row in client_for(reviewer).get(BASE).json()["results"]
        }

        states = {key: rows[str(a.pk)]["state"] for key, a in {
            "PENDING": pending,
            "ON_TIME": on_time,
            "OVERDUE_ACTIVE": overdue_active,
            "OVERDUE_EXPIRED": expired,
            "EVALUATED": evaluated,
            "REVOKED": revoked,
        }.items()}
        assert states == {
            "PENDING": "PENDING",
            "ON_TIME": "ON_TIME",
            "OVERDUE_ACTIVE": "OVERDUE",
            "OVERDUE_EXPIRED": "OVERDUE",
            "EVALUATED": "EVALUATED",
            "REVOKED": "REVOKED",
        }
        assert rows[str(overdue_active.pk)]["is_overdue"] is True
        assert rows[str(pending.pk)]["is_overdue"] is False
        assert rows[str(evaluated.pk)]["status"] == "COMPLETED"

    def test_rows_carry_the_allowlist_and_no_identity(self, reviewer) -> None:
        own_assignment(reviewer)

        row = client_for(reviewer).get(BASE).json()["results"][0]

        assert set(row) == {
            "id", "manuscript_code", "manuscript_title", "area", "version_number",
            "round_number", "assigned_at", "due_at", "status", "state", "is_overdue",
            "completed_at",
        }
        text = str(row)
        for forbidden in (AUTHOR_NAME, "ana-lopez", "assigned_by", "created_by", "authors"):
            assert forbidden not in text

    def test_the_inbox_is_paginated(self, reviewer) -> None:
        for _ in range(3):
            own_assignment(reviewer)

        body = client_for(reviewer).get(BASE, {"page_size": 2}).json()

        assert body["count"] == 3 and len(body["results"]) == 2 and body["next"]

    def test_the_inbox_does_not_query_per_row(self, reviewer, django_assert_max_num_queries) -> None:
        for _ in range(4):
            own_assignment(reviewer)

        with django_assert_max_num_queries(8):
            assert client_for(reviewer).get(BASE).status_code == 200


class TestDetail:
    def test_returns_the_blind_manuscript_and_version(self, reviewer) -> None:
        assignment = own_assignment(reviewer)

        response = client_for(reviewer).get(detail_url(assignment))

        assert response.status_code == 200
        body = response.json()
        assert set(body["manuscript"]) == {
            "id", "code", "title", "abstract", "keywords", "area", "language",
            "current_round", "current_version",
        }
        assert set(body["version"]) == {"version_number", "round_number", "submitted_at"}
        assert body["manuscript"]["code"] == assignment.manuscript.code
        assert body["state"] == "PENDING"
        assert body["document_url"] == document_url(assignment)

    def test_no_identifying_value_leaks_under_any_key(self, reviewer) -> None:
        assignment = own_assignment(reviewer)
        author = assignment.manuscript.created_by

        text = client_for(reviewer).get(detail_url(assignment)).content.decode()

        for secret in (
            AUTHOR_NAME,
            author.email,
            author.institutional_id,
            "ana-lopez-articulo.pdf",
            "metadata_snapshot",
            "original.pdf",
            "sanitized.pdf",
            "a" * 64,
        ):
            assert secret not in text

    def test_a_completed_assignment_is_readable_but_has_no_document_url(self, reviewer) -> None:
        assignment = own_assignment(reviewer)
        set_status(assignment, "COMPLETED")

        body = client_for(reviewer).get(detail_url(assignment)).json()

        assert body["document_url"] is None

    def test_a_foreign_assignment_answers_404_not_403(self, reviewer) -> None:
        foreign = own_assignment(actor("REVIEWER"))

        response = client_for(reviewer).get(detail_url(foreign))

        assert response.status_code == 404 and error_code(response) == "NOT_FOUND"

    @pytest.mark.parametrize("status", ["REVOKED", "EXPIRED"])
    def test_a_closed_assignment_answers_404(self, reviewer, status) -> None:
        assignment = own_assignment(reviewer)
        set_status(assignment, status)

        assert client_for(reviewer).get(detail_url(assignment)).status_code == 404

    def test_a_withdrawn_manuscript_answers_404(self, reviewer) -> None:
        assignment = own_assignment(reviewer)
        Manuscript.objects.filter(pk=assignment.manuscript_id).update(
            is_active=False, withdrawn_at=timezone.now()
        )

        assert client_for(reviewer).get(detail_url(assignment)).status_code == 404

    def test_a_reviewer_who_is_a_coauthor_does_not_see_the_manuscript(self, reviewer) -> None:
        assignment = own_assignment(reviewer)
        ManuscriptAuthorFactory(manuscript=assignment.manuscript, user=reviewer, author_order=2)

        assert client_for(reviewer).get(detail_url(assignment)).status_code == 404

    def test_a_reviewer_who_registered_the_manuscript_does_not_see_it(self, reviewer) -> None:
        assignment = own_assignment(reviewer)
        Manuscript.objects.filter(pk=assignment.manuscript_id).update(created_by=reviewer)

        assert client_for(reviewer).get(detail_url(assignment)).status_code == 404

    def test_an_unknown_id_answers_404(self, reviewer) -> None:
        assert client_for(reviewer).get(f"{BASE}{ManuscriptFactory().pk}/").status_code == 404


class TestDocument:
    def test_serves_the_sanitized_copy_with_a_generic_name(self, uploaded, reviewer) -> None:
        response = client_for(reviewer).get(document_url(uploaded))

        assert response.status_code == 200
        manuscript = uploaded.manuscript
        assert response["X-Accel-Redirect"] == (
            f"/_protected/manuscripts/{manuscript.pk}/v0001/sanitized.pdf"
        )
        assert response["Content-Type"] == "application/pdf"
        assert response["Content-Disposition"] == (
            f'attachment; filename="manuscript-{manuscript.code}-v1.pdf"'
        )
        assert response["X-Content-Type-Options"] == "nosniff"
        assert response["Cache-Control"] == "private, no-store"
        assert response.content == b""
        assert "original" not in response["X-Accel-Redirect"]
        assert "Ana" not in str(response.headers)

    def test_the_sanitized_file_has_no_identity_metadata(self, uploaded, media_root) -> None:
        path = version_dir_of(media_root, uploaded.manuscript, 1) / "sanitized.pdf"

        with pikepdf.open(path) as pdf:
            assert "/Info" not in pdf.trailer
            for key in ("/Metadata", "/OpenAction", "/AA", "/AcroForm"):
                assert key not in pdf.Root
            assert "/EmbeddedFiles" not in pdf.Root.get("/Names", {})
            assert "/JavaScript" not in pdf.Root.get("/Names", {})
        assert b"Ana Lopez" not in path.read_bytes()

    def test_each_download_is_audited_before_answering(self, uploaded, reviewer) -> None:
        client_for(reviewer).get(document_url(uploaded))

        row = AuditLog.objects.get(action="MANUSCRIPT_FILE_DOWNLOADED")
        assert row.actor_id == reviewer.pk and row.actor_role == "REVIEWER"
        assert row.entity_type == "MANUSCRIPT_VERSION"
        assert row.entity_id == uploaded.version_id and row.request_id
        assert row.details == {
            "manuscript_id": str(uploaded.manuscript_id),
            "version_number": 1,
            "kind": "sanitized",
        }
        assert AUTHOR_NAME not in str(row.details)

    def test_audit_failure_answers_503_without_redirect(
        self, uploaded, reviewer, monkeypatch
    ) -> None:
        def fail(**kwargs):
            raise AuditUnavailable("sin auditoría")

        monkeypatch.setattr(AuditService, "record", staticmethod(fail))

        response = client_for(reviewer).get(document_url(uploaded))

        assert response.status_code == 503 and error_code(response) == "AUDIT_UNAVAILABLE"
        assert "X-Accel-Redirect" not in response.headers
        assert not AuditLog.objects.filter(action="MANUSCRIPT_FILE_DOWNLOADED").exists()

    def test_a_missing_sanitized_file_answers_503_and_is_not_audited(
        self, uploaded, reviewer, media_root
    ) -> None:
        (version_dir_of(media_root, uploaded.manuscript, 1) / "sanitized.pdf").unlink()

        response = client_for(reviewer).get(document_url(uploaded))

        assert response.status_code == 503 and error_code(response) == "STORAGE_UNAVAILABLE"
        assert "X-Accel-Redirect" not in response.headers
        assert not AuditLog.objects.filter(action="MANUSCRIPT_FILE_DOWNLOADED").exists()

    def test_the_original_is_never_resolved_even_if_it_is_the_only_file(
        self, uploaded, reviewer, media_root
    ) -> None:
        (version_dir_of(media_root, uploaded.manuscript, 1) / "sanitized.pdf").unlink()
        assert (version_dir_of(media_root, uploaded.manuscript, 1) / "original.pdf").is_file()

        response = client_for(reviewer).get(document_url(uploaded))

        assert response.status_code == 503
        assert "X-Accel-Redirect" not in response.headers

    @pytest.mark.parametrize("status", ["COMPLETED", "REVOKED", "EXPIRED"])
    def test_a_non_active_assignment_answers_410_without_redirect(
        self, uploaded, reviewer, status
    ) -> None:
        set_status(uploaded, status)

        response = client_for(reviewer).get(document_url(uploaded))

        assert response.status_code == 410
        assert "X-Accel-Redirect" not in response.headers
        assert not AuditLog.objects.filter(action="MANUSCRIPT_FILE_DOWNLOADED").exists()

    def test_a_foreign_assignment_answers_404(self, uploaded) -> None:
        other = actor("REVIEWER")

        response = client_for(other).get(document_url(uploaded))

        assert response.status_code == 404
        assert "X-Accel-Redirect" not in response.headers

    def test_a_foreign_closed_assignment_still_answers_404_not_410(self, uploaded) -> None:
        set_status(uploaded, "REVOKED")

        assert client_for(actor("REVIEWER")).get(document_url(uploaded)).status_code == 404

    def test_a_withdrawn_manuscript_answers_404(self, uploaded, reviewer) -> None:
        Manuscript.objects.filter(pk=uploaded.manuscript_id).update(
            is_active=False, withdrawn_at=timezone.now()
        )

        assert client_for(reviewer).get(document_url(uploaded)).status_code == 404

    def test_a_reviewer_who_is_a_coauthor_cannot_download(self, uploaded, reviewer) -> None:
        ManuscriptAuthorFactory(manuscript=uploaded.manuscript, user=reviewer, author_order=2)

        response = client_for(reviewer).get(document_url(uploaded))

        assert response.status_code == 404
        assert "X-Accel-Redirect" not in response.headers
