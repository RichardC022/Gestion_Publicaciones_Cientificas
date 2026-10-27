"""Tests for the manuscript CRUD and the author validation (TSK-32).

Covers the acceptance criteria:

1. Only ``DRAFT`` and ``REQUIRES_CORRECTIONS`` are editable; any other
   state answers ``409``; ``PATCH`` creates no version or round and
   audits the modified fields.
2. At least one author, exactly one corresponding, and the registrant
   must be listed.
3. A foreign manuscript answers ``404``; an editor never reaches a
   manuscript where they are author or coauthor; the author's
   serializer exposes nothing of the reviewer.

Plus the contracts of the plan: ``ETag``/``If-Match`` on ``lock_version``,
filters with ``400`` on malformed values, pagination, and the rollback
when the audit trail is unavailable.
"""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIClient

from apps.audit.models import AuditLog
from apps.audit.services import AuditService, AuditUnavailable
from apps.publications.models import (
    CorrectionRound,
    Manuscript,
    ManuscriptAuthor,
    ManuscriptVersion,
    StatusEvent,
)
from apps.publications.serializers import AuthorEvaluationFeedbackSerializer
from tests.factories import ManuscriptAuthorFactory, UserFactory, UserRoleFactory
from tests.publications.test_models import make_manuscript

pytestmark = pytest.mark.django_db

URL = "/api/manuscripts/"


def detail_url(manuscript) -> str:
    return f"{URL}{manuscript.pk}/"


@pytest.fixture(autouse=True)
def seeded_roles(db) -> None:
    call_command("seed_roles", verbosity=0)


def actor(*roles: str, **overrides):
    """Institutional account holding the given active roles."""
    user = UserFactory(**overrides)
    for code in roles:
        UserRoleFactory(user=user, role_code=code)
    return user


def client_for(user) -> APIClient:
    client = APIClient()
    client.force_authenticate(user)
    return client


def author_payload(user, *extra: dict) -> list[dict]:
    """Authors list: the registrant as corresponding plus the extras."""
    registrant = {
        "full_name": user.get_full_name(),
        "email": user.email,
        "affiliation": "Universidad Nacional de Loja",
        "is_corresponding": True,
    }
    return [registrant, *extra]


def coauthor(email: str = "co.autor@unl.edu.ec", **overrides) -> dict:
    return {
        "full_name": "Co Autor",
        "email": email,
        "affiliation": "Universidad Técnica",
        "is_corresponding": False,
        **overrides,
    }


def create_payload(user, **overrides) -> dict:
    return {
        "title": "Efecto del clima en cultivos andinos",
        "abstract": "Resumen del estudio de campo.",
        "keywords": ["clima", "cultivos"],
        "area": "Agronomía",
        "language": "es",
        "authors": author_payload(user),
        **overrides,
    }


def post_draft(user, **overrides):
    return client_for(user).post(URL, create_payload(user, **overrides), format="json")


def owned_manuscript(owner, **overrides) -> Manuscript:
    """Manuscript registered by ``owner`` with the owner as author."""
    manuscript = make_manuscript(owner, **overrides)
    ManuscriptAuthorFactory(
        manuscript=manuscript,
        user=owner,
        full_name=owner.get_full_name(),
        email=owner.email,
        affiliation="UNL",
        is_corresponding=True,
        author_order=1,
    )
    return manuscript


def patch(user, manuscript, body: dict, *, if_match: str | None = '"0"'):
    headers = {} if if_match is None else {"HTTP_IF_MATCH": if_match}
    return client_for(user).patch(detail_url(manuscript), body, format="json", **headers)


def error_code(response) -> str:
    return response.json()["error"]["code"]


class TestCreateDraft:
    def test_creates_a_draft_without_version_or_round(self) -> None:
        user = actor("AUTHOR")

        response = post_draft(user)

        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "DRAFT"
        assert body["code"].startswith(f"GPC-{timezone.localdate().year}-")
        assert body["current_version"] == 0 and body["current_round"] == 0
        assert response["ETag"] == '"0"'
        manuscript = Manuscript.objects.get(pk=body["id"])
        assert manuscript.created_by == user
        assert not ManuscriptVersion.objects.exists()
        assert not CorrectionRound.objects.exists()

    def test_records_the_initial_status_event_and_the_audit(self) -> None:
        user = actor("AUTHOR")

        manuscript = Manuscript.objects.get(pk=post_draft(user).json()["id"])

        event = StatusEvent.objects.get(manuscript=manuscript)
        assert (event.from_status, event.to_status, event.actor) == (None, "DRAFT", user)
        audit = AuditLog.objects.get(action="MANUSCRIPT_CREATED")
        assert audit.entity_id == manuscript.pk and audit.actor_id == user.pk
        assert audit.actor_role == "AUTHOR" and audit.request_id
        assert audit.details == {"code": manuscript.code, "authors": 1}

    def test_authors_keep_the_list_order_and_link_existing_accounts(self) -> None:
        user = actor("AUTHOR")
        colleague = actor("REVIEWER", email="Colega@UNL.edu.ec")
        extras = (coauthor("colega@unl.edu.ec"), coauthor("externo@otra.edu"))

        response = post_draft(user, authors=author_payload(user, *extras))

        assert response.status_code == 201
        assert [a["author_order"] for a in response.json()["authors"]] == [1, 2, 3]
        rows = ManuscriptAuthor.objects.filter(manuscript_id=response.json()["id"])
        linked = {row.email.lower(): row.user for row in rows}
        assert linked[user.email.lower()] == user
        assert linked["colega@unl.edu.ec"] == colleague
        assert linked["externo@otra.edu"] is None

    def test_a_draft_may_be_saved_with_partial_metadata(self) -> None:
        user = actor("AUTHOR")

        response = client_for(user).post(
            URL, {"authors": author_payload(user)}, format="json"
        )

        assert response.status_code == 201
        assert response.json()["title"] == "" and response.json()["keywords"] == []

    def test_the_registrant_is_matched_by_email_ignoring_case(self) -> None:
        user = actor("AUTHOR")
        authors = author_payload(user)
        authors[0]["email"] = user.email.upper()

        assert post_draft(user, authors=authors).status_code == 201


class TestAuthorValidation:
    def test_at_least_one_author_is_required(self) -> None:
        user = actor("AUTHOR")

        for authors in ([], None):
            body = create_payload(user)
            body.pop("authors")
            if authors is not None:
                body["authors"] = authors
            response = client_for(user).post(URL, body, format="json")

            assert response.status_code == 400
            assert error_code(response) == "VALIDATION_ERROR"
            assert "authors" in response.json()["error"]["details"]
        assert not Manuscript.objects.exists()

    def test_exactly_one_corresponding_author_is_required(self) -> None:
        user = actor("AUTHOR")
        none_responsible = author_payload(user)
        none_responsible[0]["is_corresponding"] = False
        two_responsible = author_payload(user, coauthor(is_corresponding=True))

        for authors in (none_responsible, two_responsible):
            response = post_draft(user, authors=authors)

            assert response.status_code == 400
            assert "authors" in response.json()["error"]["details"]
        assert not Manuscript.objects.exists()

    def test_the_registrant_must_be_listed(self) -> None:
        user = actor("AUTHOR")
        other = [coauthor("otra.persona@unl.edu.ec", is_corresponding=True)]

        response = post_draft(user, authors=other)

        assert response.status_code == 400
        assert "debe figurar" in response.json()["error"]["details"]["authors"][0]
        assert not Manuscript.objects.exists()

    def test_repeated_author_emails_are_rejected(self) -> None:
        user = actor("AUTHOR")

        response = post_draft(
            user, authors=author_payload(user, coauthor(user.email.upper()))
        )

        assert response.status_code == 400

    def test_author_contact_and_affiliation_are_mandatory(self) -> None:
        user = actor("AUTHOR")
        authors = author_payload(user)
        authors[0].pop("affiliation")

        assert post_draft(user, authors=authors).status_code == 400

    @pytest.mark.parametrize("language", ["spa", "E1", "es-EC"])
    def test_language_must_be_iso_639_1(self, language) -> None:
        user = actor("AUTHOR")

        assert post_draft(user, language=language).status_code == 400


class TestModuleAccess:
    def test_anonymous_requests_answer_401(self) -> None:
        assert APIClient().get(URL).status_code == 401
        assert APIClient().post(URL, {}, format="json").status_code == 401

    def test_user_without_active_roles_answers_403(self) -> None:
        user = actor()

        assert client_for(user).get(URL).status_code == 403
        assert post_draft(user).status_code == 403

    def test_admin_does_not_unlock_manuscripts(self) -> None:
        admin = actor("ADMIN")
        manuscript = owned_manuscript(actor("AUTHOR"))

        assert client_for(admin).get(URL).status_code == 403
        assert client_for(admin).get(detail_url(manuscript)).status_code == 403

    def test_reviewer_has_no_access_through_this_module(self) -> None:
        assert client_for(actor("REVIEWER")).get(URL).status_code == 403

    def test_editor_cannot_register_or_edit(self) -> None:
        editor = actor("EDITOR")
        manuscript = owned_manuscript(actor("AUTHOR"), status="SUBMITTED")

        assert post_draft(editor).status_code == 403
        assert patch(editor, manuscript, {"title": "X"}).status_code == 403

    def test_revoked_role_blocks_the_next_action(self) -> None:
        user = actor("AUTHOR")
        client = client_for(user)
        assert client.get(URL).status_code == 200

        user.role_assignments.update(is_active=False, revoked_at=timezone.now())

        assert client.get(URL).status_code == 403


class TestScopeAndPrivacy:
    def test_author_only_lists_their_own_manuscripts(self) -> None:
        mine = owned_manuscript(actor("AUTHOR"))
        owner = mine.created_by
        owned_manuscript(actor("AUTHOR"))

        body = client_for(owner).get(URL).json()

        assert [item["id"] for item in body["results"]] == [str(mine.pk)]

    def test_foreign_manuscript_answers_404_not_403(self) -> None:
        foreign = owned_manuscript(actor("AUTHOR"))
        stranger = actor("AUTHOR")

        response = client_for(stranger).get(detail_url(foreign))

        assert response.status_code == 404
        assert error_code(response) == "NOT_FOUND"

    def test_patching_a_foreign_manuscript_answers_404(self) -> None:
        foreign = owned_manuscript(actor("AUTHOR"))

        assert patch(actor("AUTHOR"), foreign, {"title": "X"}).status_code == 404
        foreign.refresh_from_db()
        assert foreign.title != "X"

    def test_unknown_id_answers_404(self) -> None:
        user = actor("AUTHOR")

        assert client_for(user).get(f"{URL}00000000-0000-0000-0000-000000000000/").status_code == 404
        assert client_for(user).get(f"{URL}no-es-uuid/").status_code == 404

    def test_editor_sees_submitted_manuscripts_with_author_contact(self) -> None:
        editor = actor("EDITOR")
        author = actor("AUTHOR")
        submitted = owned_manuscript(author, status="SUBMITTED")
        owned_manuscript(author, status="DRAFT")

        body = client_for(editor).get(URL).json()

        assert [item["id"] for item in body["results"]] == [str(submitted.pk)]
        item = body["results"][0]
        assert item["authors"][0]["email"] == author.email
        assert item["created_by"]["email"] == author.email
        assert item["versions"] == []

    def test_drafts_are_private_to_their_author(self) -> None:
        draft = owned_manuscript(actor("AUTHOR"), status="DRAFT")

        assert client_for(actor("EDITOR")).get(detail_url(draft)).status_code == 404

    def test_editor_never_reaches_a_manuscript_where_they_are_coauthor(self) -> None:
        editor = actor("EDITOR")
        manuscript = owned_manuscript(actor("AUTHOR"), status="SUBMITTED")
        ManuscriptAuthor.objects.create(
            manuscript=manuscript,
            user=editor,
            full_name="Editor Coautor",
            email=editor.email,
            affiliation="UNL",
            author_order=2,
        )

        client = client_for(editor)

        assert client.get(URL).json()["results"] == []
        assert client.get(detail_url(manuscript)).status_code == 404

    def test_editor_never_reaches_the_manuscript_they_registered(self) -> None:
        person = actor("EDITOR", "AUTHOR")
        own = owned_manuscript(person, status="SUBMITTED")
        client = client_for(person)

        # Como autor la ve con la vista del autor, no con la del Editor.
        assert "created_by" not in client.get(detail_url(own)).json()

        # Sin el rol de Autor, el rol de Editor no le abre su propio manuscrito.
        person.role_assignments.filter(role__code="AUTHOR").update(
            is_active=False, revoked_at=timezone.now()
        )
        assert client.get(detail_url(own)).status_code == 404
        assert client.get(URL).json()["results"] == []

    def test_multirole_user_gets_the_union_with_the_matching_serializer(self) -> None:
        person = actor("AUTHOR", "EDITOR")
        own = owned_manuscript(person, status="SUBMITTED")
        foreign = owned_manuscript(actor("AUTHOR"), status="SUBMITTED")

        items = {
            item["id"]: item for item in client_for(person).get(URL).json()["results"]
        }

        assert set(items) == {str(own.pk), str(foreign.pk)}
        assert "created_by" not in items[str(own.pk)]
        assert "created_by" in items[str(foreign.pk)]

    def test_multirole_user_cannot_patch_a_manuscript_seen_as_editor(self) -> None:
        person = actor("AUTHOR", "EDITOR")
        foreign = owned_manuscript(actor("AUTHOR"), status="SUBMITTED")

        response = patch(person, foreign, {"title": "X"})

        assert response.status_code == 404

    def test_author_payload_exposes_nothing_of_the_review(self) -> None:
        owner = actor("AUTHOR")
        manuscript = owned_manuscript(owner)

        body = client_for(owner).get(detail_url(manuscript)).json()

        assert set(body) == {
            "id", "code", "title", "abstract", "keywords", "area", "language",
            "status", "current_round", "current_version", "is_active",
            "withdrawn_at", "withdrawal_reason", "authors", "draft_file",
            "feedback", "created_at", "updated_at",
        }
        # Sin veredicto no hay nada que leer; con él, la lista blanca de tres campos
        # (ver `test_author_feedback.py`).
        assert body["feedback"] is None
        serialized = str(body).lower()
        for forbidden in ("reviewer", "confidential", "score", "created_by"):
            assert forbidden not in serialized

    def test_feedback_serializer_is_an_allowlist(self) -> None:
        evaluation = SimpleNamespace(
            comments_for_author="Mejorar la metodología.",
            decision="REQUIRES_CORRECTIONS",
            observations="Ampliar la muestra.",
            reviewer="Revisor Anónimo",
            confidential_comments="Solo para el Editor",
            originality_score=5,
            methodology_score=2,
        )

        data = AuthorEvaluationFeedbackSerializer(evaluation).data

        assert set(data) == {"comments_for_author", "decision", "observations"}
        assert data["comments_for_author"] == "Mejorar la metodología."


class TestListFilters:
    def test_pagination_is_enforced(self) -> None:
        owner = actor("AUTHOR")
        for _ in range(3):
            owned_manuscript(owner)

        body = client_for(owner).get(URL, {"page_size": 2}).json()

        assert body["count"] == 3 and len(body["results"]) == 2
        assert client_for(owner).get(URL, {"page_size": 101}).status_code == 400

    def test_filters_by_status_and_area(self) -> None:
        owner = actor("AUTHOR")
        owned_manuscript(owner, status="DRAFT", area="Agronomía")
        wanted = owned_manuscript(owner, status="SUBMITTED", area="Física")
        client = client_for(owner)

        by_status = client.get(URL, {"status": "SUBMITTED"}).json()["results"]
        by_area = client.get(URL, {"area": "física"}).json()["results"]

        assert [i["id"] for i in by_status] == [str(wanted.pk)]
        assert [i["id"] for i in by_area] == [str(wanted.pk)]

    def test_filters_by_creation_date(self) -> None:
        owner = actor("AUTHOR")
        owned_manuscript(owner)
        today = timezone.localdate()
        client = client_for(owner)

        inside = client.get(URL, {"date_from": today, "date_to": today}).json()
        after = client.get(URL, {"date_from": today + timedelta(days=1)}).json()
        before = client.get(URL, {"date_to": today - timedelta(days=1)}).json()

        assert (inside["count"], after["count"], before["count"]) == (1, 0, 0)

    def test_search_matches_text_and_code(self) -> None:
        owner = actor("AUTHOR")
        owned_manuscript(owner, title="Biodiversidad amazónica")
        other = owned_manuscript(owner, title="Hidrología andina")
        client = client_for(owner)

        by_text = client.get(URL, {"search": "biodiversidad"}).json()["results"]
        by_code = client.get(URL, {"search": other.code}).json()["results"]

        assert [i["title"] for i in by_text] == ["Biodiversidad amazónica"]
        assert [i["id"] for i in by_code] == [str(other.pk)]
        assert client.get(URL, {"search": ""}).json()["count"] == 2

    def test_archived_manuscripts_have_their_own_view(self) -> None:
        owner = actor("AUTHOR")
        active = owned_manuscript(owner)
        archived = owned_manuscript(owner)
        Manuscript.objects.filter(pk=archived.pk).update(
            is_active=False, withdrawn_at=timezone.now()
        )
        client = client_for(owner)

        default = client.get(URL).json()["results"]
        only_archived = client.get(URL, {"archived": "true"}).json()["results"]

        assert [i["id"] for i in default] == [str(active.pk)]
        assert [i["id"] for i in only_archived] == [str(archived.pk)]

    def test_ordering_is_applied(self) -> None:
        owner = actor("AUTHOR")
        owned_manuscript(owner, title="B")
        owned_manuscript(owner, title="A")

        asc = client_for(owner).get(URL, {"ordering": "title"}).json()["results"]
        desc = client_for(owner).get(URL, {"ordering": "-title"}).json()["results"]

        assert [i["title"] for i in asc] == ["A", "B"]
        assert [i["title"] for i in desc] == ["B", "A"]

    def test_blank_filters_are_ignored(self) -> None:
        owner = actor("AUTHOR")
        owned_manuscript(owner)

        response = client_for(owner).get(URL, {"status": "", "ordering": "", "area": ""})

        assert response.status_code == 200 and response.json()["count"] == 1

    @pytest.mark.parametrize(
        "params",
        [
            {"status": "NOPE"},
            {"ordering": "password"},
            {"date_from": "ayer"},
            {"date_from": "2026-12-31", "date_to": "2026-01-01"},
            {"archived": "quizas"},
        ],
    )
    def test_malformed_filters_answer_400(self, params) -> None:
        response = client_for(actor("AUTHOR")).get(URL, params)

        assert response.status_code == 400
        assert error_code(response) == "VALIDATION_ERROR"


class TestEdit:
    def test_patch_updates_the_metadata_and_bumps_the_etag(self) -> None:
        owner = actor("AUTHOR")
        manuscript = owned_manuscript(owner)

        response = patch(owner, manuscript, {"title": "Título corregido"})

        assert response.status_code == 200
        assert response.json()["title"] == "Título corregido"
        assert response["ETag"] == '"1"'
        manuscript.refresh_from_db()
        assert manuscript.lock_version == 1 and manuscript.title == "Título corregido"

    def test_patch_creates_no_version_round_or_status_event(self) -> None:
        owner = actor("AUTHOR")
        manuscript = owned_manuscript(owner)

        patch(owner, manuscript, {"abstract": "Nuevo resumen"})

        assert not ManuscriptVersion.objects.exists()
        assert not CorrectionRound.objects.exists()
        assert not StatusEvent.objects.exists()
        manuscript.refresh_from_db()
        assert (manuscript.current_version, manuscript.current_round) == (0, 0)

    def test_patch_audits_only_the_names_of_the_modified_fields(self) -> None:
        owner = actor("AUTHOR")
        manuscript = owned_manuscript(owner)

        patch(owner, manuscript, {"title": "Secreto científico", "area": "Física"})

        audit = AuditLog.objects.get(action="MANUSCRIPT_UPDATED")
        assert audit.entity_id == manuscript.pk and audit.actor_id == owner.pk
        assert audit.details == {"fields": ["area", "title"]}
        assert "Secreto" not in str(audit.details)

    def test_patch_without_changes_neither_bumps_nor_audits(self) -> None:
        owner = actor("AUTHOR")
        manuscript = owned_manuscript(owner)

        response = patch(owner, manuscript, {"title": manuscript.title})

        assert response.status_code == 200 and response["ETag"] == '"0"'
        assert not AuditLog.objects.filter(action="MANUSCRIPT_UPDATED").exists()

    def test_patch_replaces_the_authors_and_audits_the_change(self) -> None:
        owner = actor("AUTHOR")
        manuscript = owned_manuscript(owner)
        authors = author_payload(owner, coauthor("nuevo@otra.edu"))

        response = patch(owner, manuscript, {"authors": authors})

        assert response.status_code == 200
        assert [a["email"] for a in response.json()["authors"]] == [
            owner.email,
            "nuevo@otra.edu",
        ]
        assert AuditLog.objects.get(action="MANUSCRIPT_UPDATED").details == {
            "fields": ["authors"]
        }

    def test_patch_keeps_the_author_rules(self) -> None:
        owner = actor("AUTHOR")
        manuscript = owned_manuscript(owner)

        for authors in ([], [coauthor(is_corresponding=True)], author_payload(owner, coauthor(is_corresponding=True))):
            response = patch(owner, manuscript, {"authors": authors})
            assert response.status_code == 400

        manuscript.refresh_from_db()
        assert manuscript.lock_version == 0
        assert manuscript.authors.count() == 1

    def test_a_requires_corrections_manuscript_is_editable(self) -> None:
        owner = actor("AUTHOR")
        manuscript = owned_manuscript(owner, status="REQUIRES_CORRECTIONS")

        response = patch(owner, manuscript, {"title": "Versión corregida"})

        assert response.status_code == 200
        assert not ManuscriptVersion.objects.exists()

    @pytest.mark.parametrize(
        "status", ["SUBMITTED", "UNDER_REVIEW", "ACCEPTED", "REJECTED"]
    )
    def test_other_states_answer_409_even_with_an_invalid_body(self, status) -> None:
        owner = actor("AUTHOR")
        manuscript = owned_manuscript(owner, status=status)

        response = patch(owner, manuscript, {"title": "Cambio", "language": "!!"})

        assert response.status_code == 409
        assert error_code(response) == "STATE_CONFLICT"
        assert response.json()["error"]["details"]["status"] == status
        manuscript.refresh_from_db()
        assert manuscript.title != "Cambio" and manuscript.lock_version == 0

    def test_a_withdrawn_draft_is_not_editable(self) -> None:
        owner = actor("AUTHOR")
        manuscript = owned_manuscript(owner)
        Manuscript.objects.filter(pk=manuscript.pk).update(
            is_active=False, withdrawn_at=timezone.now()
        )

        response = patch(owner, manuscript, {"title": "Cambio"})

        assert response.status_code == 409

    def test_a_draft_may_blank_its_metadata_but_a_correction_may_not(self) -> None:
        owner = actor("AUTHOR")
        draft = owned_manuscript(owner)
        correction = owned_manuscript(owner, status="REQUIRES_CORRECTIONS")

        assert patch(owner, draft, {"title": ""}).status_code == 200

        response = patch(owner, correction, {"title": "", "keywords": []})
        assert response.status_code == 400
        assert set(response.json()["error"]["details"]) == {"title", "keywords"}

    def test_if_match_is_mandatory(self) -> None:
        owner = actor("AUTHOR")
        manuscript = owned_manuscript(owner)

        for header in (None, "", "abc", "*"):
            response = patch(owner, manuscript, {"title": "X"}, if_match=header)
            assert response.status_code == 400

    @pytest.mark.parametrize("header", ['"0"', 'W/"0"', "0"])
    def test_if_match_accepts_the_usual_etag_forms(self, header) -> None:
        owner = actor("AUTHOR")
        manuscript = owned_manuscript(owner)

        assert patch(owner, manuscript, {"title": "X"}, if_match=header).status_code == 200

    def test_stale_etag_answers_409_and_keeps_the_winning_edit(self) -> None:
        owner = actor("AUTHOR")
        manuscript = owned_manuscript(owner)
        first = patch(owner, manuscript, {"title": "Gana la primera"})
        assert first.status_code == 200

        stale = patch(owner, manuscript, {"title": "Pierde la segunda"}, if_match='"0"')

        assert stale.status_code == 409
        assert error_code(stale) == "VERSION_CONFLICT"
        assert stale.json()["error"]["details"] == {"lock_version": 1}
        manuscript.refresh_from_db()
        assert manuscript.title == "Gana la primera"
        assert patch(owner, manuscript, {"title": "Con etag vigente"}, if_match=first["ETag"]).status_code == 200

    def test_get_returns_the_current_etag(self) -> None:
        owner = actor("AUTHOR")
        manuscript = owned_manuscript(owner)
        patch(owner, manuscript, {"title": "Cambio"})

        response = client_for(owner).get(detail_url(manuscript))

        assert response["ETag"] == '"1"'

    def test_there_is_no_delete_endpoint(self) -> None:
        owner = actor("AUTHOR")
        manuscript = owned_manuscript(owner)

        response = client_for(owner).delete(detail_url(manuscript))

        assert response.status_code == 405
        assert Manuscript.objects.filter(pk=manuscript.pk).exists()


class TestAuditUnavailable:
    @staticmethod
    def break_audit(monkeypatch) -> None:
        def fail(**kwargs):
            raise AuditUnavailable("sin auditoría")

        monkeypatch.setattr(AuditService, "record", staticmethod(fail))

    def test_create_rolls_back_and_answers_503(self, monkeypatch) -> None:
        user = actor("AUTHOR")
        self.break_audit(monkeypatch)

        response = post_draft(user)

        assert response.status_code == 503
        assert error_code(response) == "AUDIT_UNAVAILABLE"
        assert not Manuscript.objects.exists()
        assert not ManuscriptAuthor.objects.exists()
        assert not StatusEvent.objects.exists()

    def test_patch_rolls_back_and_answers_503(self, monkeypatch) -> None:
        owner = actor("AUTHOR")
        manuscript = owned_manuscript(owner)
        self.break_audit(monkeypatch)

        response = patch(
            owner,
            manuscript,
            {"title": "No debe persistir", "authors": author_payload(owner, coauthor())},
        )

        assert response.status_code == 503
        manuscript.refresh_from_db()
        assert manuscript.title != "No debe persistir" and manuscript.lock_version == 0
        assert manuscript.authors.count() == 1
