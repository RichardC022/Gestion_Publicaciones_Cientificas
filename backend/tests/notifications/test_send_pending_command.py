"""Tests for the ``send_pending_notifications`` command (TSK-76).

Acceptance criteria: a sent notice is not mailed again on the next run,
and an SMTP failure is stored as ``FAILED`` with a backoff. Plus: the panel
channel is never touched, a retry waits for its backoff, and the retries
end after the last attempt.
"""

from __future__ import annotations

from datetime import timedelta
from io import StringIO

import pytest
from django.core import mail
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from apps.notifications.delivery import BACKOFF_STEPS, MAX_ATTEMPTS, backoff_for
from apps.notifications.models import Notification
from tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def make_notice(recipient=None, *, key="evt-1", channel="EMAIL", **overrides) -> Notification:
    return Notification.objects.create(
        recipient=recipient or UserFactory(),
        event_key=key,
        event_type="VERDICT_REGISTERED",
        channel=channel,
        payload={"title": "Veredicto registrado", "message": "Ya puede consultarlo."},
        **overrides,
    )


def run() -> str:
    out = StringIO()
    call_command("send_pending_notifications", stdout=out)
    return out.getvalue()


@pytest.fixture
def broken_smtp(monkeypatch):
    def fail(*args, **kwargs):
        raise ConnectionRefusedError("smtp caído")

    monkeypatch.setattr("apps.notifications.delivery.send_mail", fail)


class TestSending:
    def test_pending_email_is_sent_and_marked(self) -> None:
        notice = make_notice()

        assert "avisos enviados: 1" in run()

        notice.refresh_from_db()
        assert notice.status == "SENT"
        assert notice.attempts == 1
        assert notice.sent_at is not None
        assert notice.last_error is None
        assert len(mail.outbox) == 1
        assert mail.outbox[0].subject == "Veredicto registrado"
        assert mail.outbox[0].to == [notice.recipient.email]

    def test_a_sent_notice_is_not_sent_again(self) -> None:
        make_notice()
        run()
        assert run() == ""

        assert len(mail.outbox) == 1

    def test_panel_notices_are_left_alone(self) -> None:
        notice = make_notice(channel="PANEL")

        assert run() == ""

        notice.refresh_from_db()
        assert notice.status == "PENDING"
        assert notice.attempts == 0
        assert mail.outbox == []

    def test_nothing_to_do_is_silent(self) -> None:
        assert run() == ""

    def test_only_the_sanitized_payload_fields_are_mailed(self) -> None:
        notice = make_notice()
        notice.payload = {"title": "T", "message": "M", "reviewer_id": "secreto"}
        notice.save(update_fields=["payload"])

        run()

        assert "secreto" not in mail.outbox[0].subject + mail.outbox[0].body


class TestFailures:
    def test_smtp_failure_is_stored_as_failed_with_backoff(self, broken_smtp) -> None:
        notice = make_notice()
        before = timezone.now()

        with pytest.raises(CommandError):
            run()

        notice.refresh_from_db()
        assert notice.status == "FAILED"
        assert notice.attempts == 1
        assert "ConnectionRefusedError" in notice.last_error
        assert notice.sent_at is None
        assert notice.next_attempt_at >= before + BACKOFF_STEPS[0]

    def test_failure_does_not_block_the_other_notices(self, monkeypatch) -> None:
        bad = make_notice(UserFactory(), key="evt-bad")
        good = make_notice(UserFactory(), key="evt-good")
        real = mail.send_mail

        def flaky(subject, message, from_email, recipients, **kwargs):
            if recipients == [bad.recipient.email]:
                raise OSError("rechazado")
            return real(subject, message, from_email, recipients, **kwargs)

        monkeypatch.setattr("apps.notifications.delivery.send_mail", flaky)

        with pytest.raises(CommandError):
            run()

        bad.refresh_from_db()
        good.refresh_from_db()
        assert (bad.status, good.status) == ("FAILED", "SENT")

    def test_failed_notice_waits_for_its_backoff(self, broken_smtp, monkeypatch) -> None:
        notice = make_notice()
        with pytest.raises(CommandError):
            run()

        # El servidor se recupera, pero el backoff aún no vence.
        monkeypatch.undo()
        assert run() == ""
        notice.refresh_from_db()
        assert notice.status == "FAILED"
        assert mail.outbox == []

    def test_failed_notice_is_retried_after_the_backoff(self, broken_smtp, monkeypatch) -> None:
        notice = make_notice()
        with pytest.raises(CommandError):
            run()
        monkeypatch.undo()
        Notification.objects.filter(pk=notice.pk).update(
            next_attempt_at=timezone.now() - timedelta(seconds=1)
        )

        assert "avisos enviados: 1" in run()

        notice.refresh_from_db()
        assert notice.status == "SENT"
        assert notice.attempts == 2
        assert notice.last_error is None
        assert notice.next_attempt_at is None

    def test_retries_stop_after_the_last_attempt(self, broken_smtp) -> None:
        notice = make_notice(
            status="FAILED",
            attempts=MAX_ATTEMPTS - 1,
            next_attempt_at=timezone.now() - timedelta(seconds=1),
        )

        with pytest.raises(CommandError):
            run()

        notice.refresh_from_db()
        assert notice.attempts == MAX_ATTEMPTS
        assert notice.next_attempt_at is None
        assert run() == ""

    def test_recipient_without_email_is_a_failure(self) -> None:
        recipient = UserFactory()
        type(recipient).objects.filter(pk=recipient.pk).update(email="")
        notice = make_notice(recipient)

        with pytest.raises(CommandError):
            run()

        notice.refresh_from_db()
        assert notice.status == "FAILED"
        assert mail.outbox == []


def test_backoff_grows_and_ends() -> None:
    waits = [backoff_for(n) for n in range(1, MAX_ATTEMPTS)]
    assert waits == sorted(waits)
    assert backoff_for(MAX_ATTEMPTS) is None
