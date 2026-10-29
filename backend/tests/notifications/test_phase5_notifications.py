"""Notifications over a whole editorial cycle (TSK-79, HU-24).

Acceptance criterion: the notifications do not duplicate events. The cycle
runs through the real endpoints; the tests then count what each person got,
replay the domain signals, and look for the other side's identity in every
notice, panel response and mail.
"""

from __future__ import annotations

from collections import Counter

import pytest
from django.core import mail
from django.core.management import call_command

from apps.notifications.models import Notification
from apps.publications.models import Manuscript
from apps.publications.signals import manuscript_submitted, verdict_registered
from apps.reviews.models import Evaluation
from apps.reviews.signals import announce, assignment_created, evaluation_submitted
from tests.factories import UserFactory
from tests.phase5 import AUTHOR_TOKENS, EVALUATION, REVIEWER_TOKENS, Lifecycle
from tests.publications.test_manuscript_api import actor, client_for
from tests.publications.test_submission import media_root, seeded_roles, submit  # noqa: F401

pytestmark = pytest.mark.django_db


@pytest.fixture
def flow(django_capture_on_commit_callbacks, submit) -> Lifecycle:  # noqa: F811
    return Lifecycle.create(django_capture_on_commit_callbacks, submit)


def panel(user) -> list[Notification]:
    return list(Notification.objects.filter(recipient=user, channel="PANEL").order_by("created_at", "id"))


def mails(user) -> list[Notification]:
    return list(Notification.objects.filter(recipient=user, channel="EMAIL").order_by("created_at", "id"))


def kinds(notices) -> list[str]:
    return sorted(n.event_type for n in notices)


def blob(notices) -> str:
    return " ".join(str(n.payload) for n in notices)


def replay_signals(flow: Lifecycle) -> None:
    """Fire again the signals of the cycle, with the real identifiers."""
    manuscript = flow.manuscript
    version = manuscript.versions.get()
    evaluation = Evaluation.objects.get(assignment=flow.assignment)
    verdict = manuscript.verdicts.get()
    manuscript_submitted.send_robust(
        sender=Manuscript, manuscript_id=manuscript.pk, version_id=version.pk,
        submitted_by_id=flow.author.pk,
    )
    announce(
        assignment_created, assignment_id=flow.assignment.pk, manuscript_id=manuscript.pk,
        reviewer_id=flow.reviewer.pk, assigned_by_id=flow.editor.pk,
    )
    announce(
        evaluation_submitted, evaluation_id=evaluation.pk, assignment_id=flow.assignment.pk,
        manuscript_id=manuscript.pk, reviewer_id=flow.reviewer.pk,
    )
    verdict_registered.send_robust(
        sender=Manuscript, manuscript_id=manuscript.pk, verdict_id=verdict.pk,
        decision="ACCEPTED", editor_id=flow.editor.pk,
    )


class TestOneNoticePerEvent:
    def test_each_person_gets_one_notice_per_step_of_the_cycle(self, flow) -> None:
        flow.accepted()

        assert kinds(panel(flow.author)) == ["MANUSCRIPT_SUBMITTED", "VERDICT_REGISTERED"]
        assert kinds(panel(flow.editor)) == ["EVALUATION_SUBMITTED", "SUBMISSION_RECEIVED"]
        assert kinds(panel(flow.reviewer)) == ["ASSIGNMENT_CREATED"]
        assert panel(flow.admin) == []

    def test_every_panel_notice_has_exactly_one_pending_mail_twin(self, flow) -> None:
        flow.accepted()

        for person in (flow.author, flow.editor, flow.reviewer):
            assert kinds(mails(person)) == kinds(panel(person))
            assert {n.status for n in mails(person)} == {"PENDING"}
            assert {n.status for n in panel(person)} == {"SENT"}

    def test_no_recipient_has_the_same_event_twice(self, flow) -> None:
        flow.accepted()
        replay_signals(flow)

        pairs = Counter(Notification.objects.values_list("recipient_id", "event_key"))
        assert pairs and max(pairs.values()) == 1

    def test_replaying_every_signal_creates_nothing_new(self, flow) -> None:
        flow.accepted()
        before = set(Notification.objects.values_list("pk", flat=True))

        replay_signals(flow)

        assert set(Notification.objects.values_list("pk", flat=True)) == before

    def test_the_assignment_notice_carries_the_deadline_once(self, flow) -> None:
        flow.accepted()

        (notice,) = [n for n in panel(flow.reviewer) if n.event_type == "ASSIGNMENT_CREATED"]
        assert notice.payload["due_at"] == flow.assignment.due_at.isoformat()
        assert notice.payload["manuscript_code"] == flow.manuscript.code

    def test_people_without_a_relation_to_the_manuscript_get_nothing(self, flow) -> None:
        stranger_author, stranger_reviewer, inactive_editor = actor("AUTHOR"), actor("REVIEWER"), actor("EDITOR")
        type(inactive_editor).objects.filter(pk=inactive_editor.pk).update(is_active=False)

        flow.accepted()

        for person in (stranger_author, stranger_reviewer, inactive_editor):
            assert Notification.objects.filter(recipient=person).count() == 0

    def test_a_second_withdrawal_does_not_notify_again(self, flow) -> None:
        flow.accepted()
        assert flow.withdraw().status_code == 200
        notices = Notification.objects.count()

        assert flow.withdraw().status_code == 409

        assert Notification.objects.count() == notices
        assert kinds(panel(flow.editor)).count("MANUSCRIPT_WITHDRAWN") == 1


class TestCorrectionNotices:
    def test_the_correction_cycle_notifies_once_each_step(self, flow) -> None:
        manuscript = flow.accepted()
        original = manuscript.verdicts.get()
        assert flow.authorize_correction(original.pk).status_code == 201
        assert flow.judge({"decision": "REJECTED", "justification": "Se detectó un error grave."}, "c-1").status_code == 201

        assert kinds(panel(flow.editor)).count("VERDICT_CORRECTION_AUTHORIZED") == 1
        author_titles = sorted(n.payload["title"] for n in panel(flow.author) if n.event_type == "VERDICT_REGISTERED")
        assert len(author_titles) == 2
        assert any(title.startswith("Decisión corregida") for title in author_titles)
        pairs = Counter(Notification.objects.values_list("recipient_id", "event_key"))
        assert max(pairs.values()) == 1

    def test_a_repeated_authorization_request_notifies_once(self, flow) -> None:
        manuscript = flow.accepted()
        original = manuscript.verdicts.get()

        first = flow.authorize_correction(original.pk, key="misma")
        replay = flow.authorize_correction(original.pk, key="misma")

        assert first.status_code == replay.status_code == 201
        assert kinds(panel(flow.editor)).count("VERDICT_CORRECTION_AUTHORIZED") == 1

    def test_the_administrators_reason_never_reaches_a_notice(self, flow) -> None:
        manuscript = flow.accepted()
        flow.authorize_correction(manuscript.verdicts.get().pk)

        everything = blob(Notification.objects.all())

        assert "evaluación equivocada" not in everything


class TestNoCrossIdentity:
    def test_nothing_for_the_reviewer_names_the_author_in_the_whole_cycle(self, flow) -> None:
        manuscript = flow.accepted()
        flow.authorize_correction(manuscript.verdicts.get().pk)
        flow.judge({"decision": "REJECTED", "justification": "Se detectó un error grave."}, "c-1")
        flow.withdraw()

        text = blob(panel(flow.reviewer) + mails(flow.reviewer))
        response = client_for(flow.reviewer).get("/api/notifications/").content.decode()

        assert panel(flow.reviewer)
        for token in AUTHOR_TOKENS:
            assert token not in text and token not in response

    def test_nothing_for_the_author_names_the_reviewer_or_the_confidential_text(self, flow) -> None:
        manuscript = flow.accepted()
        flow.authorize_correction(manuscript.verdicts.get().pk)
        flow.judge({"decision": "REJECTED", "justification": "JUSTIFICACION_INTERNA"}, "c-1")

        text = blob(panel(flow.author) + mails(flow.author))
        response = client_for(flow.author).get("/api/notifications/").content.decode()

        assert len(panel(flow.author)) == 3
        for token in (*REVIEWER_TOKENS, EVALUATION["confidential_comments"], "JUSTIFICACION_INTERNA"):
            assert token not in text and token not in response
        assert str(flow.reviewer.pk) not in response and flow.reviewer.email not in response


class TestMailDelivery:
    def test_mail_goes_out_once_and_the_panel_is_unchanged(self, flow) -> None:
        flow.accepted()
        twins = Notification.objects.filter(channel="EMAIL").count()
        panel_before = list(Notification.objects.filter(channel="PANEL").values_list("pk", "status", "read_at"))

        call_command("send_pending_notifications")
        call_command("send_pending_notifications")

        assert len(mail.outbox) == twins
        assert not Notification.objects.filter(channel="EMAIL").exclude(status="SENT").exists()
        assert list(Notification.objects.filter(channel="PANEL").values_list("pk", "status", "read_at")) == panel_before
        recipients = Counter(address for message in mail.outbox for address in message.to)
        assert recipients[flow.reviewer.email] == 1

    def test_the_mails_keep_the_double_blind(self, flow) -> None:
        flow.accepted()
        call_command("send_pending_notifications")

        for message in mail.outbox:
            text = message.subject + message.body
            if message.to == [flow.reviewer.email]:
                assert not any(token in text for token in AUTHOR_TOKENS)
            if message.to == [flow.author.email]:
                assert not any(token in text for token in REVIEWER_TOKENS)
            assert EVALUATION["confidential_comments"] not in text

    def test_reading_one_notice_does_not_touch_the_others_or_the_mail(self, flow) -> None:
        flow.accepted()
        notice = panel(flow.author)[0]
        client = client_for(flow.author)

        assert client.patch(f"/api/notifications/{notice.pk}/read/").status_code == 200

        assert client.get("/api/notifications/").json()["unread_count"] == len(panel(flow.author)) - 1
        assert not mails(flow.author)[0].read_at
        assert client_for(UserFactory()).get("/api/notifications/").json()["count"] == 0
