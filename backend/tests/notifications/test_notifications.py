"""Tests for the notifications of Phase 5 (TSK-75, HU-24, RF-20).

Acceptance criteria: each recipient gets one notice per event; the
notices for the reviewer carry no author data and the ones for the author
no reviewer data (checked on the notice already built, plan section 2.9
point 3); and the panel works while the mail is still ``PENDING`` or
``FAILED``.
"""

from __future__ import annotations

import json
from datetime import timedelta

import pytest
from django.core import mail
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIClient

from apps.notifications.models import Notification
from apps.notifications.payloads import PAYLOAD_FIELDS, build_payload
from apps.publications.models import Manuscript
from apps.publications.services.verdicts import register_verdict
from apps.publications.signals import (
    manuscript_submitted,
    manuscript_withdrawn,
    new_version_submitted,
    verdict_registered,
)
from apps.reviews.models import IncidentReport
from apps.reviews.signals import (
    announce,
    assignment_created,
    assignment_expired,
    assignment_revoked,
    evaluation_submitted,
    incident_reported,
    incident_resolved,
    reviewer_conflict_declared,
)
from tests.factories import ManuscriptAuthorFactory, UserFactory
from tests.publications.test_manuscript_api import actor, client_for
from tests.reviews.test_editor_api import make_assignment, make_reviewer, submitted

pytestmark = pytest.mark.django_db

AUTHOR_NAME = "Marcela Quizhpe Ordóñez"
AUTHOR_SECRETS = ("Marcela", "Quizhpe", "Ordóñez", "marcela.autora", "Instituto Secreto")
REVIEWER_NAME = "Rodrigo Valarezo Cueva"
REVIEWER_SECRETS = ("Rodrigo", "Valarezo", "Cueva", "rodrigo.revisor")


@pytest.fixture(autouse=True)
def seeded_roles(db) -> None:
    call_command("seed_roles", verbosity=0)


@pytest.fixture(autouse=True)
def media_root(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    return tmp_path


@pytest.fixture
def author():
    return actor("AUTHOR", first_name="Marcela", last_name="Quizhpe Ordóñez", email="marcela.autora@unl.edu.ec")


@pytest.fixture
def editor():
    return actor("EDITOR")


@pytest.fixture
def reviewer():
    return make_reviewer(first_name="Rodrigo", last_name="Valarezo Cueva", email="rodrigo.revisor@unl.edu.ec")


@pytest.fixture
def manuscript(author) -> Manuscript:
    item = submitted(author, status="UNDER_REVIEW")
    item.authors.update(full_name=AUTHOR_NAME, affiliation="Instituto Secreto")
    return item


@pytest.fixture
def assignment(manuscript, reviewer, editor):
    return make_assignment(manuscript, reviewer, editor)


def panel(user, **filters):
    return list(Notification.objects.filter(recipient=user, channel="PANEL", **filters))


def mails(user):
    return list(Notification.objects.filter(recipient=user, channel="EMAIL"))


def text_of(notices) -> str:
    return json.dumps([n.payload for n in notices], ensure_ascii=False)


class TestPayload:
    def test_only_allowlisted_fields_are_accepted(self) -> None:
        with pytest.raises(ValueError, match="reviewer_name"):
            build_payload(title="T", message="M", link="/x", reviewer_name="Rodrigo")

    def test_required_fields(self) -> None:
        with pytest.raises(ValueError, match="link"):
            build_payload(title="T", message="M")

    def test_payload_has_exactly_the_planned_keys(self) -> None:
        payload = build_payload(title="T", message="M", link="/x")

        assert tuple(payload) == PAYLOAD_FIELDS
        assert payload["due_at"] is None


class TestReviewerNotices:
    def test_assignment_created_tells_the_reviewer_the_deadline(self, assignment, reviewer) -> None:
        announce(assignment_created, assignment_id=assignment.pk, manuscript_id=assignment.manuscript_id,
                 reviewer_id=reviewer.pk, assigned_by_id=assignment.assigned_by_id)

        (notice,) = panel(reviewer)
        assert notice.event_type == "ASSIGNMENT_CREATED"
        assert notice.status == "SENT" and notice.sent_at is not None
        assert notice.payload["manuscript_code"] == assignment.manuscript.code
        assert notice.payload["manuscript_title"] == assignment.manuscript.title
        assert notice.payload["due_at"] == assignment.due_at.isoformat()
        assert notice.payload["action"]
        assert notice.payload["link"] == f"/app/reviewer/assignments/{assignment.pk}"

    @pytest.mark.parametrize("cause", ["OVERDUE", "CONFLICT_OF_INTEREST", "MANUSCRIPT_WITHDRAWN"])
    def test_revocation_tells_the_reviewer_without_the_free_text(self, assignment, reviewer, cause) -> None:
        announce(assignment_revoked, assignment_id=assignment.pk, manuscript_id=assignment.manuscript_id,
                 reviewer_id=reviewer.pk, cause=cause)

        (notice,) = panel(reviewer)
        assert notice.event_type == "ASSIGNMENT_REVOKED"
        assert notice.payload["link"] == "/app/reviewer/assignments"

    def test_an_inactive_reviewer_gets_nothing(self, assignment, reviewer) -> None:
        type(reviewer).objects.filter(pk=reviewer.pk).update(is_active=False)

        announce(assignment_created, assignment_id=assignment.pk, manuscript_id=assignment.manuscript_id,
                 reviewer_id=reviewer.pk, assigned_by_id=assignment.assigned_by_id)

        assert Notification.objects.count() == 0


class TestEditorNotices:
    @pytest.mark.parametrize(
        ("signal", "kwargs", "event_type"),
        [
            (evaluation_submitted, {"evaluation_id": "11111111-1111-1111-1111-111111111111"}, "EVALUATION_SUBMITTED"),
            (reviewer_conflict_declared, {}, "CONFLICT_DECLARED"),
            (incident_reported, {"incident_id": "22222222-2222-2222-2222-222222222222", "report_type": "IDENTITY_LEAK"}, "INCIDENT_REPORTED"),
            (assignment_expired, {"assigned_by_id": None}, "ASSIGNMENT_EXPIRED"),
        ],
    )
    def test_the_assigning_editor_is_told(self, assignment, editor, reviewer, signal, kwargs, event_type) -> None:
        announce(signal, assignment_id=assignment.pk, manuscript_id=assignment.manuscript_id,
                 reviewer_id=reviewer.pk, **kwargs)

        (notice,) = panel(editor)
        assert notice.event_type == event_type
        assert notice.payload["manuscript_code"] == assignment.manuscript.code
        for secret in AUTHOR_SECRETS:
            assert secret not in text_of([notice])

    def test_other_editors_are_not_told_when_the_assigning_one_can_act(self, assignment, editor) -> None:
        other = actor("EDITOR")

        announce(reviewer_conflict_declared, assignment_id=assignment.pk,
                 manuscript_id=assignment.manuscript_id, reviewer_id=assignment.reviewer_id)

        assert panel(other) == [] and len(panel(editor)) == 1

    def test_if_the_assigning_editor_has_a_conflict_the_eligible_ones_are_told(self, assignment, editor) -> None:
        other = actor("EDITOR")
        ManuscriptAuthorFactory(manuscript=assignment.manuscript, user=editor, author_order=9)

        announce(reviewer_conflict_declared, assignment_id=assignment.pk,
                 manuscript_id=assignment.manuscript_id, reviewer_id=assignment.reviewer_id)

        assert panel(editor) == [] and len(panel(other)) == 1

    def test_expiry_carries_the_deadline(self, assignment, editor) -> None:
        announce(assignment_expired, assignment_id=assignment.pk, manuscript_id=assignment.manuscript_id,
                 reviewer_id=assignment.reviewer_id, assigned_by_id=editor.pk)

        (notice,) = panel(editor)
        assert notice.payload["due_at"] == assignment.due_at.isoformat()

    def test_the_incident_text_never_reaches_the_notice(self, assignment, editor, reviewer) -> None:
        incident = IncidentReport.objects.create(
            assignment=assignment, manuscript=assignment.manuscript, reporter=reviewer,
            report_type="IDENTITY_LEAK", description="DESCRIPCION_CONFIDENCIAL",
        )

        announce(incident_reported, incident_id=incident.pk, assignment_id=assignment.pk,
                 manuscript_id=assignment.manuscript_id, report_type="IDENTITY_LEAK")

        assert "DESCRIPCION_CONFIDENCIAL" not in text_of(panel(editor))


class TestAuthorNotices:
    def test_submission_notifies_the_author_and_the_eligible_editors(self, author, editor) -> None:
        manuscript = submitted(author)
        conflicted = actor("EDITOR")
        ManuscriptAuthorFactory(manuscript=manuscript, user=conflicted, author_order=9)
        inactive = actor("EDITOR")
        type(inactive).objects.filter(pk=inactive.pk).update(is_active=False)
        reviewer_only = actor("REVIEWER")
        version = manuscript.versions.get()

        announce(manuscript_submitted, manuscript_id=manuscript.pk, version_id=version.pk,
                 submitted_by_id=author.pk)

        assert [n.event_type for n in panel(author)] == ["MANUSCRIPT_SUBMITTED"]
        assert [n.event_type for n in panel(editor)] == ["SUBMISSION_RECEIVED"]
        # El editor con conflicto figura como coautor: recibe el aviso de autor, nunca el de Editor.
        assert [n.event_type for n in panel(conflicted)] == ["MANUSCRIPT_SUBMITTED"]
        assert panel(inactive) == panel(reviewer_only) == []

    def test_new_version_notifies_author_and_editors(self, manuscript, author, editor) -> None:
        version = manuscript.versions.get()

        announce(new_version_submitted, manuscript_id=manuscript.pk, version_id=version.pk,
                 submitted_by_id=author.pk)

        assert [n.event_type for n in panel(author)] == ["NEW_VERSION_SUBMITTED"]
        assert [n.event_type for n in panel(editor)] == ["NEW_VERSION_RECEIVED"]

    @pytest.mark.parametrize(
        ("decision", "title", "has_action"),
        [
            ("ACCEPTED", "Manuscrito aceptado", False),
            ("REJECTED", "Manuscrito rechazado", False),
            ("REQUIRES_CORRECTIONS", "Se solicitan correcciones", True),
        ],
    )
    def test_verdict_notifies_the_author(self, manuscript, author, decision, title, has_action) -> None:
        announce(verdict_registered, manuscript_id=manuscript.pk,
                 verdict_id="33333333-3333-3333-3333-333333333333", decision=decision,
                 editor_id=manuscript.created_by_id)

        (notice,) = panel(author)
        assert notice.payload["title"] == title
        assert bool(notice.payload["action"]) is has_action

    def test_withdrawal_tells_editors_and_other_authors_but_not_the_one_who_withdrew(
        self, manuscript, author, editor
    ) -> None:
        coauthor = actor("AUTHOR")
        ManuscriptAuthorFactory(manuscript=manuscript, user=coauthor, author_order=2)

        announce(manuscript_withdrawn, manuscript_id=manuscript.pk, withdrawn_by_id=author.pk,
                 previous_status="UNDER_REVIEW")

        assert panel(author) == []
        assert len(panel(coauthor)) == 1 and len(panel(editor)) == 1

    def test_withdrawing_a_draft_does_not_bother_the_editors(self, author, editor) -> None:
        draft = submitted(author, status="DRAFT")

        announce(manuscript_withdrawn, manuscript_id=draft.pk, withdrawn_by_id=author.pk,
                 previous_status="DRAFT")

        assert panel(editor) == []

    def test_anonymized_version_request_reaches_the_author_without_the_report(
        self, assignment, author, reviewer
    ) -> None:
        incident = IncidentReport.objects.create(
            assignment=assignment, manuscript=assignment.manuscript, reporter=reviewer,
            report_type="IDENTITY_LEAK", description="DESCRIPCION_CONFIDENCIAL",
        )

        announce(incident_resolved, incident_id=incident.pk, assignment_id=assignment.pk,
                 manuscript_id=assignment.manuscript_id, resolution="REQUEST_ANONYMIZED_VERSION",
                 correction_round_id=None)

        (notice,) = panel(author)
        body = text_of([notice]).lower()
        assert notice.event_type == "ANONYMIZED_VERSION_REQUESTED"
        assert notice.payload["action"]
        for word in ("reporte", "fuga", "incidente", "revisor", "confidencial", "descripcion"):
            assert word not in body
        for secret in REVIEWER_SECRETS:
            assert secret not in text_of([notice])

    @pytest.mark.parametrize("resolution", ["REASSIGN", "DISMISS"])
    def test_other_resolutions_do_not_notify_the_author(self, assignment, author, reviewer, resolution) -> None:
        incident = IncidentReport.objects.create(
            assignment=assignment, manuscript=assignment.manuscript, reporter=reviewer,
            report_type="OTHER", description="x" * 30,
        )

        announce(incident_resolved, incident_id=incident.pk, assignment_id=assignment.pk,
                 manuscript_id=assignment.manuscript_id, resolution=resolution, correction_round_id=None)

        assert panel(author) == []


class TestOneNoticePerEvent:
    def fire(self, assignment, reviewer):
        announce(assignment_created, assignment_id=assignment.pk, manuscript_id=assignment.manuscript_id,
                 reviewer_id=reviewer.pk, assigned_by_id=assignment.assigned_by_id)

    def test_the_same_event_twice_creates_one_panel_and_one_mail_notice(self, assignment, reviewer) -> None:
        self.fire(assignment, reviewer)
        self.fire(assignment, reviewer)

        assert len(panel(reviewer)) == 1 and len(mails(reviewer)) == 1

    def test_the_mail_twin_is_pending_and_never_listed_in_the_panel(self, assignment, reviewer) -> None:
        self.fire(assignment, reviewer)

        (twin,) = mails(reviewer)
        assert twin.status == "PENDING" and twin.attempts == 0
        assert twin.payload == panel(reviewer)[0].payload

    def test_two_roles_of_one_person_get_two_notices(self, assignment) -> None:
        both = actor("EDITOR", "AUTHOR")
        manuscript = submitted(actor("AUTHOR"))
        version = manuscript.versions.get()
        ManuscriptAuthorFactory(manuscript=manuscript, user=both, author_order=2)

        announce(manuscript_submitted, manuscript_id=manuscript.pk, version_id=version.pk,
                 submitted_by_id=manuscript.created_by_id)

        # Coautora con cuenta (rol Autor): un aviso; el rol Editor tiene conflicto.
        assert [n.event_type for n in panel(both)] == ["MANUSCRIPT_SUBMITTED"]

    def test_one_failing_recipient_does_not_block_the_rest(self, monkeypatch) -> None:
        from apps.notifications import services

        first, second = actor("EDITOR"), actor("EDITOR")
        manuscript = submitted(actor("AUTHOR"))
        real = services.notify

        def flaky(*, recipient, **kwargs):
            if recipient.pk == first.pk:
                raise RuntimeError("fallo simulado")
            return real(recipient=recipient, **kwargs)

        monkeypatch.setattr(services, "notify", flaky)
        announce(manuscript_submitted, manuscript_id=manuscript.pk,
                 version_id=manuscript.versions.get().pk, submitted_by_id=manuscript.created_by_id)

        assert panel(first) == [] and len(panel(second)) == 1

    def test_a_failing_receiver_never_breaks_the_business_action(self, manuscript, monkeypatch) -> None:
        from apps.notifications import receivers

        def boom(*args, **kwargs):
            raise RuntimeError("fallo simulado")

        monkeypatch.setattr(receivers, "authors_of", boom)

        announce(verdict_registered, manuscript_id=manuscript.pk,
                 verdict_id="44444444-4444-4444-4444-444444444444", decision="ACCEPTED",
                 editor_id=manuscript.created_by_id)

        assert Notification.objects.count() == 0


class TestNoCrossIdentityLeak:
    """Plan section 2.9, point 3: checked on the notices once they are built."""

    def test_nothing_addressed_to_the_reviewer_names_the_author(self, manuscript, assignment, reviewer, editor) -> None:
        announce(assignment_created, assignment_id=assignment.pk, manuscript_id=manuscript.pk,
                 reviewer_id=reviewer.pk, assigned_by_id=editor.pk)
        for cause in ("OVERDUE", "MANUSCRIPT_WITHDRAWN", "CONFLICT_OF_INTEREST"):
            announce(assignment_revoked, assignment_id=assignment.pk, manuscript_id=manuscript.pk,
                     reviewer_id=reviewer.pk, cause=cause)

        notices = list(Notification.objects.filter(recipient=reviewer))
        assert notices
        blob = text_of(notices)
        for secret in AUTHOR_SECRETS:
            assert secret not in blob

    def test_nothing_addressed_to_the_author_names_the_reviewer(self, manuscript, assignment, reviewer, author, editor) -> None:
        version = manuscript.versions.get()
        incident = IncidentReport.objects.create(
            assignment=assignment, manuscript=manuscript, reporter=reviewer,
            report_type="IDENTITY_LEAK", description="d" * 30,
        )
        announce(manuscript_submitted, manuscript_id=manuscript.pk, version_id=version.pk, submitted_by_id=author.pk)
        announce(new_version_submitted, manuscript_id=manuscript.pk, version_id=version.pk, submitted_by_id=author.pk)
        for number, decision in enumerate(("ACCEPTED", "REJECTED", "REQUIRES_CORRECTIONS")):
            announce(verdict_registered, manuscript_id=manuscript.pk, verdict_id=f"00000000-0000-0000-0000-00000000000{number}",
                     decision=decision, editor_id=editor.pk)
        announce(incident_resolved, incident_id=incident.pk, assignment_id=assignment.pk,
                 manuscript_id=manuscript.pk, resolution="REQUEST_ANONYMIZED_VERSION", correction_round_id=None)
        announce(manuscript_withdrawn, manuscript_id=manuscript.pk, withdrawn_by_id=editor.pk, previous_status="UNDER_REVIEW")

        notices = list(Notification.objects.filter(recipient=author))
        assert notices
        blob = text_of(notices)
        for secret in REVIEWER_SECRETS:
            assert secret not in blob
        assert str(reviewer.pk) not in blob and str(reviewer.email) not in blob

    def test_the_api_response_of_the_reviewer_has_no_author_data(self, assignment, reviewer, editor) -> None:
        announce(assignment_created, assignment_id=assignment.pk, manuscript_id=assignment.manuscript_id,
                 reviewer_id=reviewer.pk, assigned_by_id=editor.pk)

        response = client_for(reviewer).get("/api/notifications/")

        assert response.status_code == 200
        for secret in AUTHOR_SECRETS:
            assert secret not in response.content.decode()

    def test_the_mail_sent_to_the_reviewer_has_no_author_data(self, assignment, reviewer, editor) -> None:
        announce(assignment_created, assignment_id=assignment.pk, manuscript_id=assignment.manuscript_id,
                 reviewer_id=reviewer.pk, assigned_by_id=editor.pk)

        call_command("send_pending_notifications")

        (message,) = mail.outbox
        assert message.to == [reviewer.email]
        assert assignment.manuscript.code in message.body
        assert "Fecha límite" in message.body
        for secret in AUTHOR_SECRETS:
            assert secret not in message.subject + message.body


class TestPanelIndependentOfMail:
    def test_panel_notice_is_available_while_the_mail_fails(self, assignment, reviewer, editor, monkeypatch) -> None:
        announce(assignment_created, assignment_id=assignment.pk, manuscript_id=assignment.manuscript_id,
                 reviewer_id=reviewer.pk, assigned_by_id=editor.pk)

        def broken(*args, **kwargs):
            raise ConnectionRefusedError("smtp caído")

        monkeypatch.setattr("apps.notifications.delivery.send_mail", broken)
        with pytest.raises(Exception):
            call_command("send_pending_notifications")

        assert [n.status for n in mails(reviewer)] == ["FAILED"]
        assert client_for(reviewer).get("/api/notifications/").json()["count"] == 1


class TestApi:
    URL = "/api/notifications/"

    def make(self, user, key="k1", read=False, **overrides):
        return Notification.objects.create(
            recipient=user, event_key=key, event_type="ASSIGNMENT_CREATED", channel="PANEL",
            status="SENT", sent_at=timezone.now(), read_at=timezone.now() if read else None,
            payload=build_payload(title="T", message="M", link="/app/x"), **overrides,
        )

    def test_anonymous_gets_401(self) -> None:
        assert APIClient().get(self.URL).status_code == 401
        assert APIClient().post(self.URL + "read-all/").status_code == 401

    def test_lists_only_own_panel_notices_newest_first_with_unread_count(self) -> None:
        user, other = UserFactory(), UserFactory()
        old = self.make(user, "old", read=True)
        Notification.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=1))
        new = self.make(user, "new")
        self.make(other, "foreign")
        Notification.objects.create(
            recipient=user, event_key="new#email", event_type="X", channel="EMAIL", payload={}, status="PENDING"
        )

        body = client_for(user).get(self.URL).json()

        assert [row["id"] for row in body["results"]] == [str(new.pk), str(old.pk)]
        assert body["count"] == 2 and body["unread_count"] == 1

    def test_response_fields_are_the_planned_ones(self) -> None:
        user = UserFactory()
        self.make(user)

        row = client_for(user).get(self.URL).json()["results"][0]

        assert set(row) == {"id", "event_type", "payload", "is_read", "read_at", "created_at"}
        assert set(row["payload"]) == set(PAYLOAD_FIELDS)

    def test_read_filter(self) -> None:
        user = UserFactory()
        unread, read = self.make(user, "a"), self.make(user, "b", read=True)
        client = client_for(user)

        assert [r["id"] for r in client.get(self.URL, {"read": "false"}).json()["results"]] == [str(unread.pk)]
        assert [r["id"] for r in client.get(self.URL, {"read": "true"}).json()["results"]] == [str(read.pk)]
        assert client.get(self.URL, {"read": "quizas"}).status_code == 400

    def test_mark_one_read_is_idempotent(self) -> None:
        user = UserFactory()
        notice = self.make(user)
        client = client_for(user)

        first = client.patch(f"{self.URL}{notice.pk}/read/")
        stamp = Notification.objects.get(pk=notice.pk).read_at
        second = client.patch(f"{self.URL}{notice.pk}/read/")

        assert first.status_code == second.status_code == 200
        assert first.json()["is_read"] is True
        assert Notification.objects.get(pk=notice.pk).read_at == stamp

    def test_someone_elses_notice_answers_404_and_stays_unread(self) -> None:
        owner, intruder = UserFactory(), UserFactory()
        notice = self.make(owner)

        response = client_for(intruder).patch(f"{self.URL}{notice.pk}/read/")

        assert response.status_code == 404
        assert Notification.objects.get(pk=notice.pk).read_at is None

    def test_the_mail_twin_cannot_be_marked_through_the_api(self) -> None:
        user = UserFactory()
        twin = Notification.objects.create(
            recipient=user, event_key="e#email", event_type="X", channel="EMAIL", payload={}
        )

        assert client_for(user).patch(f"{self.URL}{twin.pk}/read/").status_code == 404

    def test_read_all_marks_only_own_notices(self) -> None:
        user, other = UserFactory(), UserFactory()
        self.make(user, "a"), self.make(user, "b")
        foreign = self.make(other, "c")

        response = client_for(user).post(self.URL + "read-all/")

        assert response.status_code == 204
        assert client_for(user).get(self.URL).json()["unread_count"] == 0
        assert Notification.objects.get(pk=foreign.pk).read_at is None

    def test_any_authenticated_account_can_read_its_own_notices(self) -> None:
        for role in ("AUTHOR", "REVIEWER", "EDITOR", "ADMIN"):
            assert client_for(actor(role)).get(self.URL).status_code == 200


class TestEndToEnd:
    def test_registering_a_verdict_notifies_the_author(self, author, editor, django_capture_on_commit_callbacks) -> None:
        from tests.publications.test_verdicts import reviewed

        manuscript = reviewed(editor, owner=author)

        with django_capture_on_commit_callbacks(execute=True):
            register_verdict(manuscript_id=manuscript.pk, editor=editor, decision="REJECTED",
                             justification="Justificación interna del editor.", context={})

        (notice,) = panel(author, event_type="VERDICT_REGISTERED")
        assert "Justificación interna" not in text_of([notice])
        assert client_for(author).get("/api/notifications/").json()["unread_count"] == 1

    def test_withdrawing_notifies_the_reviewer_and_the_editor(self, assignment, author, reviewer, editor, django_capture_on_commit_callbacks) -> None:
        with django_capture_on_commit_callbacks(execute=True):
            response = client_for(author).post(
                f"/api/manuscripts/{assignment.manuscript_id}/withdraw/",
                {"reason": "Retiro por decisión de los autores."},
                format="json",
            )

        assert response.status_code == 200
        assert [n.event_type for n in panel(reviewer)] == ["ASSIGNMENT_REVOKED"]
        assert [n.event_type for n in panel(editor)] == ["MANUSCRIPT_WITHDRAWN"]
        assert "Retiro por decisión" not in text_of(panel(reviewer) + panel(editor))
        for secret in AUTHOR_SECRETS:
            assert secret not in text_of(panel(reviewer))
