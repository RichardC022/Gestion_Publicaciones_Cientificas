"""Editorial cycles through the API, from the submission to the catalog (TSK-53).

The author submits with the real endpoints, the editor starts the review,
assigns, revokes and judges with the real editor endpoints. Only the
reviewer's final evaluation is written with a factory: its endpoint
belongs to Phase 4.

Each cycle checks, at every step, the invariants of the plan: a single
``ACTIVE`` assignment, an exact 20-day deadline, the round counter, the
catalog only for accepted manuscripts, and an audit chain that stays
intact after each cycle.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from apps.audit.models import AuditLog
from apps.publications.models import CatalogEntry, CorrectionRound, Manuscript, Verdict
from apps.publications.services.storage import catalog_path
from apps.reviews.models import Assignment
from apps.reviews.services.expiration import mark_expired_assignments
from tests.factories import FinalEvaluationFactory, ReviewerProfileFactory, UserRoleFactory
from tests.publications import pdf_factory as factory
from tests.publications.test_draft_file import pdf_file
from tests.publications.test_lifecycle import assert_audit_chain_intact
from tests.publications.test_manuscript_api import actor, client_for, error_code
from tests.publications.test_new_version import versions_url
from tests.publications.test_submission import (  # noqa: F401
    media_root,
    owner,
    ready_draft,
    seeded_roles,
    submit,
)
from tests.reviews.test_editor_api import make_assignment

pytestmark = pytest.mark.django_db

EDITOR_API = "/api/editor/"
AREA = "Agronomía"


@pytest.fixture
def editor():
    return actor("EDITOR")


def new_reviewer():
    profile = ReviewerProfileFactory(expertise_areas=[AREA])
    UserRoleFactory(user=profile.user, role_code="REVIEWER")
    return profile.user


def submitted_by_author(owner, submit) -> Manuscript:
    manuscript = ready_draft(owner, pdf=factory.clean_pdf(pages=1), area=AREA)
    assert submit(owner, manuscript).status_code == 201
    manuscript.refresh_from_db()
    assert (manuscript.status, manuscript.current_version, manuscript.current_round) == (
        "SUBMITTED", 1, 0,
    )
    return manuscript


def start_review(editor, manuscript, reviewer=None):
    body = {"reviewer_id": str(reviewer.pk)} if reviewer else {}
    return client_for(editor).post(
        f"{EDITOR_API}submissions/{manuscript.pk}/start-review/", body, format="json"
    )


def finish_evaluation(assignment, **values):
    """The reviewer's final evaluation (Phase 4 endpoint) and the assignment closing."""
    evaluation = FinalEvaluationFactory(assignment=assignment, **values)
    Assignment.objects.filter(pk=assignment.pk).update(status="COMPLETED")
    return evaluation


def judge(editor, manuscript, body, key, django_capture_on_commit_callbacks):
    manuscript.refresh_from_db()
    with django_capture_on_commit_callbacks(execute=True):
        return client_for(editor).post(
            f"{EDITOR_API}manuscripts/{manuscript.pk}/verdicts/",
            body,
            format="json",
            HTTP_IDEMPOTENCY_KEY=key,
            HTTP_IF_MATCH=f'"{manuscript.lock_version}"',
        )


def assert_exact_deadline(assignment) -> None:
    assert assignment.due_at - assignment.assigned_at == timedelta(days=20)
    assert assignment.status == "ACTIVE"


def one_active_assignment(manuscript) -> Assignment:
    return Assignment.objects.get(manuscript=manuscript, status="ACTIVE")


class TestCorrectionsThenAcceptance:
    def test_the_whole_cycle_publishes_the_second_version(
        self, owner, editor, submit, django_capture_on_commit_callbacks
    ) -> None:
        manuscript = submitted_by_author(owner, submit)
        inbox = client_for(editor).get(f"{EDITOR_API}submissions/").json()["results"]
        assert [row["id"] for row in inbox] == [str(manuscript.pk)]

        # Ronda 0: se asigna al iniciar la revisión.
        first_reviewer = new_reviewer()
        started = start_review(editor, manuscript, first_reviewer)
        assert started.status_code == 200 and started.json()["status"] == "UNDER_REVIEW"
        first = one_active_assignment(manuscript)
        assert_exact_deadline(first)
        finish_evaluation(first, recommendation="REQUIRES_CORRECTIONS")

        requested = judge(
            editor,
            manuscript,
            {"decision": "REQUIRES_CORRECTIONS", "observations": "Ampliar la metodología."},
            "ciclo-1",
            django_capture_on_commit_callbacks,
        )
        assert requested.status_code == 201 and requested.json()["opened_round"] == 1
        manuscript.refresh_from_db()
        assert (manuscript.status, manuscript.current_round) == ("REQUIRES_CORRECTIONS", 1)
        assert not CatalogEntry.objects.exists()
        round_one = CorrectionRound.objects.get(manuscript=manuscript, round_number=1)
        assert round_one.opened_by_verdict_id is not None and round_one.closed_at is None

        # El Autor responde con la versión 2, que cierra la ronda 1.
        with django_capture_on_commit_callbacks(execute=True):
            answered = client_for(owner).post(
                versions_url(manuscript),
                {"file": pdf_file(factory.clean_pdf(pages=2), name="v2.pdf")},
                format="multipart",
                HTTP_IDEMPOTENCY_KEY="respuesta-1",
            )
        assert answered.status_code == 201, answered.content
        manuscript.refresh_from_db()
        round_one.refresh_from_db()
        assert (manuscript.status, manuscript.current_version) == ("SUBMITTED", 2)
        assert round_one.closed_by_version.version_number == 2

        # Ronda 1: nueva revisión con otro Revisor sobre la versión 2.
        second_reviewer = new_reviewer()
        assert start_review(editor, manuscript, second_reviewer).status_code == 200
        second = one_active_assignment(manuscript)
        assert second.version.version_number == 2 and second.reviewer == second_reviewer
        assert_exact_deadline(second)
        finish_evaluation(second)

        accepted = judge(
            editor, manuscript, {"decision": "ACCEPTED"}, "ciclo-2",
            django_capture_on_commit_callbacks,
        )

        assert accepted.status_code == 201, accepted.content
        body = accepted.json()
        assert body["manuscript"]["status"] == "ACCEPTED"
        assert body["manuscript"]["current_round"] == 1 and body["opened_round"] is None
        assert [row["decision"] for row in body["history"]] == [
            "REQUIRES_CORRECTIONS", "ACCEPTED",
        ]
        entry = CatalogEntry.objects.get(manuscript=manuscript)
        assert entry.is_active and entry.version.version_number == 2
        assert catalog_path(entry.public_file_path).is_file()
        evaluations = client_for(editor).get(
            f"{EDITOR_API}manuscripts/{manuscript.pk}/evaluations/"
        ).json()["results"]
        assert [row["version_number"] for row in evaluations] == [1, 2]
        assert Verdict.objects.filter(manuscript=manuscript).count() == 2
        assert [e.to_status for e in manuscript.status_events.order_by("id")] == [
            "DRAFT", "SUBMITTED", "UNDER_REVIEW", "REQUIRES_CORRECTIONS", "SUBMITTED",
            "UNDER_REVIEW", "ACCEPTED",
        ]
        assert_audit_chain_intact()


class TestRevocationAndReassignment:
    def test_a_revoked_reviewer_is_replaced_and_the_manuscript_is_rejected(
        self, owner, editor, submit, django_capture_on_commit_callbacks
    ) -> None:
        manuscript = submitted_by_author(owner, submit)
        wrong = new_reviewer()
        assert start_review(editor, manuscript, wrong).status_code == 200
        first = one_active_assignment(manuscript)

        # Con un Revisor activo no se puede asignar a otro.
        blocked = client_for(editor).post(
            f"{EDITOR_API}manuscripts/{manuscript.pk}/assignments/",
            {"reviewer_id": str(new_reviewer().pk)},
            format="json",
        )
        assert blocked.status_code == 409 and error_code(blocked) == "ASSIGNMENT_CONFLICT"

        revoked = client_for(editor).post(
            f"{EDITOR_API}assignments/{first.pk}/revoke/",
            {"cause": "ASSIGNMENT_ERROR", "reason": "Se asignó al Revisor equivocado."},
            format="json",
        )
        assert revoked.status_code == 200 and revoked.json()["status"] == "REVOKED"
        manuscript.refresh_from_db()
        assert (manuscript.status, manuscript.current_round, manuscript.current_version) == (
            "UNDER_REVIEW", 0, 1,
        )

        replacement = new_reviewer()
        reassigned = client_for(editor).post(
            f"{EDITOR_API}manuscripts/{manuscript.pk}/assignments/",
            {"reviewer_id": str(replacement.pk)},
            format="json",
        )
        assert reassigned.status_code == 201
        second = one_active_assignment(manuscript)
        assert second.reviewer == replacement and second.pk != first.pk
        assert_exact_deadline(second)
        manuscript.refresh_from_db()
        assert (manuscript.current_round, manuscript.current_version) == (0, 1)

        finish_evaluation(second, recommendation="REJECT")
        rejected = judge(
            editor,
            manuscript,
            {"decision": "REJECTED", "justification": "Resultados no reproducibles."},
            "rechazo",
            django_capture_on_commit_callbacks,
        )

        assert rejected.status_code == 201
        assert rejected.json()["catalog_entry"] is None
        assert not CatalogEntry.objects.exists()
        history = client_for(editor).get(
            f"{EDITOR_API}manuscripts/{manuscript.pk}/assignments/"
        ).json()["results"]
        assert [row["status"] for row in history] == ["COMPLETED", "REVOKED"]
        assert_audit_chain_intact()


class TestExpiredAssignment:
    def test_the_editor_decides_after_the_deadline(
        self, owner, editor, submit, django_capture_on_commit_callbacks
    ) -> None:
        manuscript = submitted_by_author(owner, submit)
        silent = new_reviewer()
        assert start_review(editor, manuscript, silent).status_code == 200
        # El plazo ya venció: se mueve la asignación 21 días al pasado.
        stale = one_active_assignment(manuscript)
        Assignment.objects.filter(pk=stale.pk).update(
            assigned_at=stale.assigned_at - timedelta(days=21),
            due_at=stale.due_at - timedelta(days=21),
        )

        with django_capture_on_commit_callbacks(execute=True):
            result = mark_expired_assignments()

        assert (result.expired, result.failed) == (1, 0)
        stale.refresh_from_db()
        manuscript.refresh_from_db()
        assert stale.status == "EXPIRED" and manuscript.status == "UNDER_REVIEW"
        listed = client_for(editor).get(f"{EDITOR_API}assignments/expired/").json()["results"]
        assert [row["id"] for row in listed] == [str(stale.pk)]

        # Vencida no es revocada: hay que revocarla antes de asignar a otro.
        replacement = new_reviewer()
        url = f"{EDITOR_API}manuscripts/{manuscript.pk}/assignments/"
        blocked = client_for(editor).post(
            url, {"reviewer_id": str(replacement.pk)}, format="json"
        )
        assert blocked.status_code == 409
        assert client_for(editor).post(
            f"{EDITOR_API}assignments/{stale.pk}/revoke/",
            {"cause": "OVERDUE", "reason": "No respondió en el plazo."},
            format="json",
        ).status_code == 200
        assert client_for(editor).get(f"{EDITOR_API}assignments/expired/").json()["results"] == []
        assert client_for(editor).post(
            url, {"reviewer_id": str(replacement.pk)}, format="json"
        ).status_code == 201
        assert_exact_deadline(one_active_assignment(manuscript))
        assert [
            a.action
            for a in AuditLog.objects.filter(entity_type="ASSIGNMENT").order_by("id")
        ] == [
            "ASSIGNMENT_CREATED", "ASSIGNMENT_EXPIRED", "ASSIGNMENT_REVOKED", "ASSIGNMENT_CREATED",
        ]
        assert_audit_chain_intact()


class TestAuditFailureDuringPublication:
    def test_nothing_is_published_and_the_editor_can_retry(
        self, owner, editor, submit, monkeypatch, django_capture_on_commit_callbacks
    ) -> None:
        from apps.audit.services import AuditService, AuditUnavailable

        manuscript = submitted_by_author(owner, submit)
        assert start_review(editor, manuscript, new_reviewer()).status_code == 200
        finish_evaluation(one_active_assignment(manuscript))
        original = AuditService.record

        def fail(**kwargs):
            raise AuditUnavailable("sin auditoría")

        monkeypatch.setattr(AuditService, "record", staticmethod(fail))
        failed = judge(editor, manuscript, {"decision": "ACCEPTED"}, "intento",
                       django_capture_on_commit_callbacks)

        assert failed.status_code == 503 and error_code(failed) == "AUDIT_UNAVAILABLE"
        manuscript.refresh_from_db()
        assert manuscript.status == "UNDER_REVIEW" and not Verdict.objects.exists()
        assert not CatalogEntry.objects.exists()

        monkeypatch.setattr(AuditService, "record", staticmethod(original))
        retried = judge(editor, manuscript, {"decision": "ACCEPTED"}, "intento",
                        django_capture_on_commit_callbacks)

        assert retried.status_code == 201
        assert CatalogEntry.objects.filter(is_active=True).count() == 1
        assert_audit_chain_intact()

