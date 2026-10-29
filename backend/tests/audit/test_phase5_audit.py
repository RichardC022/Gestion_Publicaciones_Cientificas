"""Global audit over a whole editorial cycle (TSK-79, HU-21).

Acceptance criterion: the audit chain verifies after the real flows of
Phase 5 (submission, review, verdict, public download, withdrawal,
administrative correction and the administrator's own queries), and the
administrator sees all of it without personal data or content.
"""

from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.audit.integrity import verify_audit_chain
from apps.audit.models import AuditLog
from apps.audit.services import AuditService
from tests.phase5 import AUTHOR_TOKENS, REVIEWER_TOKENS, EVALUATION, Lifecycle, anonymous
from tests.publications.test_lifecycle import assert_audit_chain_intact
from tests.publications.test_manuscript_api import client_for
from tests.publications.test_submission import media_root, seeded_roles, submit  # noqa: F401

pytestmark = pytest.mark.django_db

AUDIT_URL = "/api/admin/audit/"
IPV6 = "2001:DB8:0:0:0:0:0:1"


@pytest.fixture
def flow(django_capture_on_commit_callbacks, submit) -> Lifecycle:  # noqa: F811
    return Lifecycle.create(django_capture_on_commit_callbacks, submit)


def verify_everything() -> str:
    out = StringIO()
    call_command("verify_integrity", stdout=out, stderr=StringIO())
    return out.getvalue()


def actions_for(admin, manuscript) -> list[str]:
    rows = client_for(admin).get(AUDIT_URL, {"manuscript": str(manuscript.pk), "page_size": 100}).json()["results"]
    return [row["action"] for row in rows]


class TestChainAfterTheCycle:
    def test_files_and_chain_verify_after_acceptance_and_withdrawal(self, flow) -> None:
        manuscript = flow.accepted()
        assert anonymous().get(f"/api/catalog/{manuscript.code}/document/").status_code == 200
        assert flow.withdraw().status_code == 200

        assert "sin discrepancias" in verify_everything()
        assert_audit_chain_intact()

    def test_the_chain_verifies_with_a_non_canonical_ipv6_address(self, flow) -> None:
        manuscript = flow.accepted()

        response = anonymous().get(
            f"/api/catalog/{manuscript.code}/document/",
            HTTP_X_FORWARDED_FOR=IPV6,
            HTTP_USER_AGENT="Mozilla/5.0 (X11; Linux)",
        )

        assert response.status_code == 200
        assert not verify_audit_chain().discrepancies
        assert "sin discrepancias" in verify_everything()

    def test_a_service_call_with_an_uppercase_ipv6_keeps_the_chain_valid(self) -> None:
        AuditService.record(action="LOGIN", entity_type="SESSION", ip_address=IPV6)
        AuditService.record(action="LOGOUT", entity_type="SESSION", ip_address="::FFFF:10.0.0.1")

        assert not verify_audit_chain().discrepancies

    def test_the_stored_address_is_the_canonical_one(self) -> None:
        AuditService.record(action="LOGIN", entity_type="SESSION", ip_address=IPV6)

        assert AuditLog.objects.get().ip_address == "2001:db8::1"

    def test_a_tampered_row_after_the_cycle_is_detected(self, flow) -> None:
        from django.db import connection

        flow.accepted()
        with connection.cursor() as cursor:
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
            cursor.execute("ALTER TABLE audit_audit_log DISABLE TRIGGER trg_audit_no_update")
            cursor.execute("UPDATE audit_audit_log SET action = 'ADMIN' WHERE action = 'VERDICT_REGISTERED'")
            cursor.execute("ALTER TABLE audit_audit_log ENABLE TRIGGER trg_audit_no_update")

        with pytest.raises(CommandError):
            verify_everything()


class TestAdministratorView:
    def test_the_admin_sees_the_whole_cycle_of_one_manuscript(self, flow) -> None:
        manuscript = flow.accepted()
        anonymous().get(f"/api/catalog/{manuscript.code}/document/")
        flow.withdraw()

        actions = set(actions_for(flow.admin, manuscript))

        assert {
            "MANUSCRIPT_SUBMITTED",
            "ASSIGNMENT_CREATED",
            "EVALUATION_SUBMITTED",
            "VERDICT_REGISTERED",
            "CATALOG_DOCUMENT_DOWNLOADED",
            "MANUSCRIPT_WITHDRAWN",
        } <= actions

    def test_the_view_carries_no_personal_data_or_content_of_the_cycle(self, flow) -> None:
        manuscript = flow.accepted()
        anonymous().get(
            f"/api/catalog/{manuscript.code}/document/",
            HTTP_X_FORWARDED_FOR="203.0.113.77", HTTP_USER_AGENT="NavegadorDePrueba/1.0",
        )
        flow.withdraw()
        client = client_for(flow.admin)

        pages = [client.get(AUDIT_URL, {"page_size": 100}).content.decode()]
        first = client.get(AUDIT_URL, {"manuscript": str(manuscript.pk)}).json()["results"][0]
        pages.append(client.get(f"{AUDIT_URL}{first['id']}/").content.decode())
        blob = "\n".join(pages)

        for forbidden in (
            *AUTHOR_TOKENS, *REVIEWER_TOKENS,
            "203.0.113.77", "NavegadorDePrueba", "Retiro por decisión",
            EVALUATION["confidential_comments"], EVALUATION["comments_for_author"],
            manuscript.title, manuscript.abstract,
        ):
            assert forbidden not in blob

    def test_the_admin_queries_are_audited_and_the_chain_still_verifies(self, flow) -> None:
        flow.accepted()
        client = client_for(flow.admin)
        listed = client.get(AUDIT_URL, {"action": "VERDICT_REGISTERED"}).json()["results"][0]
        client.get(f"{AUDIT_URL}{listed['id']}/")

        queries = AuditLog.objects.filter(actor_id=flow.admin.pk).order_by("id")
        assert [q.action for q in queries] == ["AUDIT_QUERIED", "AUDIT_DETAIL_VIEWED"]
        assert queries[0].details["filters"] == {"action": "VERDICT_REGISTERED"}
        assert "sin discrepancias" in verify_everything()


class TestCorrectionInTheAudit:
    def test_the_correction_cycle_leaves_three_linked_events(self, flow) -> None:
        manuscript = flow.accepted()
        original = manuscript.verdicts.get()
        assert flow.authorize_correction(original.pk).status_code == 201
        manuscript.refresh_from_db()
        # Aceptado -> rechazado por corrección.
        corrected = flow.judge({"decision": "REJECTED", "justification": "Se detectó un error grave."}, "corrige-1")
        assert corrected.status_code == 201, corrected.content

        events = list(
            AuditLog.objects.filter(
                action__in=("VERDICT_REGISTERED", "VERDICT_CORRECTION_AUTHORIZED", "VERDICT_CORRECTED")
            ).order_by("id")
        )
        assert [e.action for e in events] == [
            "VERDICT_REGISTERED", "VERDICT_CORRECTION_AUTHORIZED", "VERDICT_CORRECTED",
        ]
        newest = manuscript.verdicts.order_by("created_at", "id").last()
        assert events[2].details["verdict_id"] == str(newest.pk)
        assert events[2].details["previous_verdict_id"] == str(original.pk)
        assert events[2].details["correction_id"] == events[1].entity_id.__str__()
        assert_audit_chain_intact()

    def test_the_flag_moves_to_the_newest_verdict(self, flow) -> None:
        manuscript = flow.accepted()
        original = manuscript.verdicts.get()
        flow.authorize_correction(original.pk)
        flow.judge({"decision": "REJECTED", "justification": "Se detectó un error grave."}, "corrige-1")
        client = client_for(flow.admin)

        def flag(action):
            event = AuditLog.objects.filter(action=action).latest("id")
            return client.get(f"{AUDIT_URL}{event.event_id}/").json()["can_authorize_correction"]

        assert flag("VERDICT_REGISTERED") is False   # ya no es el más reciente
        assert flag("VERDICT_CORRECTED") is True     # el nuevo veredicto sí puede corregirse
