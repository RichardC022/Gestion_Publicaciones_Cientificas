"""Tests for the ``mark_expired_assignments`` command (TSK-49).

Covers the acceptance criteria: it never changes an assignment to
``REVOKED`` nor creates a new one; running it twice repeats neither
events nor notices; and it leaves evaluations and drafts untouched.

Plus the contracts of the plan: the cut is ``due_at <= now()`` by the
database clock, each assignment expires with its own audit event, and an
unavailable audit trail leaves the assignment ``ACTIVE`` for the next run
without blocking the others.
"""

from __future__ import annotations

from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.audit.services import AuditService, AuditUnavailable
from apps.reviews.models import Assignment, Evaluation
from apps.reviews.signals import assignment_expired
from tests.publications.test_manuscript_api import actor, client_for
from tests.reviews.test_editor_api import make_assignment, make_reviewer, submitted

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def seeded_roles(db) -> None:
    call_command("seed_roles", verbosity=0)


@pytest.fixture
def editor():
    return actor("EDITOR")


@pytest.fixture
def events():
    received: list[dict] = []

    def on_expired(sender, **kwargs):
        received.append(kwargs)

    assignment_expired.connect(on_expired, dispatch_uid="test-expired")
    yield received
    assignment_expired.disconnect(dispatch_uid="test-expired")


def under_review():
    return submitted(status="UNDER_REVIEW")


def run(callbacks) -> str:
    out = StringIO()
    with callbacks(execute=True):
        call_command("mark_expired_assignments", stdout=out)
    return out.getvalue()


def audits() -> list[AuditLog]:
    return list(AuditLog.objects.filter(action="ASSIGNMENT_EXPIRED"))


class TestSelection:
    def test_expires_only_active_assignments_past_their_deadline(
        self, editor, django_capture_on_commit_callbacks
    ) -> None:
        late = make_assignment(under_review(), make_reviewer(), editor, days_ago=21)
        on_time = make_assignment(under_review(), make_reviewer(), editor, days_ago=5)

        output = run(django_capture_on_commit_callbacks)

        late.refresh_from_db()
        on_time.refresh_from_db()
        assert late.status == "EXPIRED" and late.lock_version == 1
        assert on_time.status == "ACTIVE" and on_time.lock_version == 0
        assert "vencidas: 1" in output

    def test_the_cut_is_due_at_less_than_or_equal_to_the_database_now(
        self, editor, django_capture_on_commit_callbacks
    ) -> None:
        with connection.cursor() as cursor:
            cursor.execute("SELECT now()")
            (now,) = cursor.fetchone()
        exactly_now = make_assignment(
            under_review(), make_reviewer(), editor,
            assigned_at=now - timedelta(days=20), due_at=now,
        )
        just_after = make_assignment(
            under_review(), make_reviewer(), editor,
            assigned_at=now - timedelta(days=19), due_at=now + timedelta(days=1),
        )

        run(django_capture_on_commit_callbacks)

        exactly_now.refresh_from_db()
        just_after.refresh_from_db()
        assert exactly_now.status == "EXPIRED"
        assert just_after.status == "ACTIVE"

    @pytest.mark.parametrize("status", ["REVOKED", "COMPLETED", "EXPIRED"])
    def test_other_statuses_are_never_touched(
        self, editor, status, django_capture_on_commit_callbacks
    ) -> None:
        closed = make_assignment(
            under_review(), make_reviewer(), editor, days_ago=40, status=status
        )

        output = run(django_capture_on_commit_callbacks)

        closed.refresh_from_db()
        assert closed.status == status and closed.lock_version == 0
        assert output == "" and audits() == []


class TestNoAutomaticDecision:
    def test_it_neither_revokes_nor_reassigns_and_keeps_the_manuscript(
        self, editor, django_capture_on_commit_callbacks
    ) -> None:
        manuscript = under_review()
        late = make_assignment(manuscript, make_reviewer(), editor, days_ago=25)

        run(django_capture_on_commit_callbacks)

        late.refresh_from_db()
        manuscript.refresh_from_db()
        assert late.status == "EXPIRED"
        assert late.revoked_at is None and late.revoked_by is None
        assert late.revocation_reason is None
        assert Assignment.objects.count() == 1
        assert manuscript.status == "UNDER_REVIEW"
        assert (manuscript.current_round, manuscript.current_version) == (0, 1)
        assert manuscript.lock_version == 0

    def test_evaluations_and_drafts_are_left_untouched(
        self, editor, django_capture_on_commit_callbacks
    ) -> None:
        late = make_assignment(under_review(), make_reviewer(), editor, days_ago=25)
        draft = Evaluation.objects.create(
            assignment=late,
            manuscript=late.manuscript,
            version=late.version,
            reviewer=late.reviewer,
            clarity_score=4,
            confidential_comments="Borrador privado.",
        )

        run(django_capture_on_commit_callbacks)

        draft.refresh_from_db()
        assert draft.status == "DRAFT" and draft.clarity_score == 4
        assert draft.confidential_comments == "Borrador privado."
        assert draft.lock_version == 0

    def test_the_editor_must_still_revoke_before_reassigning(
        self, editor, django_capture_on_commit_callbacks
    ) -> None:
        manuscript = under_review()
        late = make_assignment(manuscript, make_reviewer(), editor, days_ago=25)
        run(django_capture_on_commit_callbacks)
        client = client_for(editor)

        listed = client.get("/api/editor/assignments/expired/").json()["results"]
        blocked = client.post(
            f"/api/editor/manuscripts/{manuscript.pk}/assignments/",
            {"reviewer_id": str(make_reviewer().pk)},
            format="json",
        )

        assert [row["id"] for row in listed] == [str(late.pk)]
        assert listed[0]["status"] == "EXPIRED"
        assert blocked.status_code == 409


class TestIdempotency:
    def test_a_second_run_repeats_no_event_notice_or_change(
        self, editor, events, django_capture_on_commit_callbacks
    ) -> None:
        late = make_assignment(under_review(), make_reviewer(), editor, days_ago=25)

        first = run(django_capture_on_commit_callbacks)
        second = run(django_capture_on_commit_callbacks)

        late.refresh_from_db()
        assert "vencidas: 1" in first and second == ""
        assert late.lock_version == 1
        assert len(audits()) == 1
        assert len(events) == 1

    def test_the_notice_carries_identifiers_only(
        self, editor, events, django_capture_on_commit_callbacks
    ) -> None:
        late = make_assignment(under_review(), make_reviewer(), editor, days_ago=25)

        run(django_capture_on_commit_callbacks)

        (payload,) = events
        assert payload["assignment_id"] == late.pk
        assert payload["manuscript_id"] == late.manuscript_id
        assert payload["reviewer_id"] == late.reviewer_id
        assert payload["assigned_by_id"] == editor.pk

    def test_nothing_to_do_is_silent(self, django_capture_on_commit_callbacks) -> None:
        assert run(django_capture_on_commit_callbacks) == ""


class TestAudit:
    def test_each_expiration_is_audited_as_a_system_event(
        self, editor, django_capture_on_commit_callbacks
    ) -> None:
        first = make_assignment(under_review(), make_reviewer(), editor, days_ago=22)
        second = make_assignment(under_review(), make_reviewer(), editor, days_ago=30)

        run(django_capture_on_commit_callbacks)

        events = audits()
        assert {e.entity_id for e in events} == {first.pk, second.pk}
        for event in events:
            assert event.actor is None and event.result == "SUCCESS"
            assert event.details["source"] == "scheduler"
            assert event.details["manuscript_id"]

    def test_an_audit_failure_leaves_it_active_and_does_not_block_the_rest(
        self, editor, events, monkeypatch, django_capture_on_commit_callbacks
    ) -> None:
        blocked = make_assignment(under_review(), make_reviewer(), editor, days_ago=30)
        other = make_assignment(under_review(), make_reviewer(), editor, days_ago=25)
        original = AuditService.record

        def fail_for_blocked(**kwargs):
            if kwargs["entity_id"] == blocked.pk:
                raise AuditUnavailable("sin auditoría")
            return original(**kwargs)

        monkeypatch.setattr(AuditService, "record", staticmethod(fail_for_blocked))
        with pytest.raises(CommandError, match="se reintentarán"):
            run(django_capture_on_commit_callbacks)

        blocked.refresh_from_db()
        other.refresh_from_db()
        assert blocked.status == "ACTIVE" and blocked.lock_version == 0
        assert other.status == "EXPIRED"
        assert [e["assignment_id"] for e in events] == [other.pk]

        monkeypatch.setattr(AuditService, "record", staticmethod(original))
        run(django_capture_on_commit_callbacks)

        blocked.refresh_from_db()
        assert blocked.status == "EXPIRED"
        assert [e["assignment_id"] for e in events] == [other.pk, blocked.pk]
        assert len(audits()) == 2

    def test_the_log_line_reports_the_failures(
        self, editor, monkeypatch, django_capture_on_commit_callbacks
    ) -> None:
        make_assignment(under_review(), make_reviewer(), editor, days_ago=30)

        def fail(**kwargs):
            raise AuditUnavailable("sin auditoría")

        monkeypatch.setattr(AuditService, "record", staticmethod(fail))
        out = StringIO()
        with pytest.raises(CommandError):
            with django_capture_on_commit_callbacks(execute=True):
                call_command("mark_expired_assignments", stdout=out)

        assert "con error: 1" in out.getvalue()


class TestCronTemplate:
    def test_the_expiration_line_is_active_and_does_not_overlap(self) -> None:
        from pathlib import Path

        template = Path(__file__).resolve().parents[3] / "scripts" / "cron" / "gpc.cron"
        if not template.exists():
            pytest.skip("La plantilla de cron no está en la imagen del backend.")
        lines = [
            line
            for line in template.read_text(encoding="utf-8").splitlines()
            if "mark_expired_assignments" in line and not line.startswith("#")
        ]

        assert len(lines) == 1
        line = lines[0]
        assert line.startswith("* * * * * root ")
        assert "flock -n /var/lock/gpc-expire.lock" in line
        assert "exec -T backend python manage.py mark_expired_assignments" in line
        assert ">> /var/log/gpc-expire.log 2>&1" in line
