"""Tests for role and object permissions (TSK-21).

Covers the acceptance criteria:

1. ``403`` is only used for a role without module permission; a foreign
   object answers ``404``.
2. ``IsAdmin`` does not unlock manuscripts, evaluations or PDFs.
3. A role revoked during the session blocks the next action even though
   the access token is still valid.

The object permissions follow the model contract of the plan (sections
1.8 and 1.13) — ``created_by_id``/``manuscript`` and
``reviewer_id``/``status`` — so they are exercised here with contract
stubs; the real ``Manuscript`` and ``Assignment`` models arrive in
TSK-30 and TSK-46 and consume these permissions unchanged.
"""

from __future__ import annotations

import base64
import json

import pytest
from django.core.management import call_command
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory, APIClient, force_authenticate
from rest_framework.views import APIView

from apps.publications.permissions import IsManuscriptOwner
from apps.reviews.permissions import IsActiveAssignedReviewer, IsAssignedReviewer
from apps.users.models import Role, User, UserRole
from apps.users.permissions import (
    IsAdmin,
    IsAuthor,
    IsEditor,
    IsPublicCatalog,
    IsReviewer,
)

pytestmark = pytest.mark.django_db

LOGIN_URL = "/api/auth/login/"
ME_URL = "/api/auth/me/"
PASSWORD = "institucional-123"
FACTORY = APIRequestFactory()


def make_user(**overrides):
    """Create an institutional account with defaults."""
    payload = {
        "institutional_id": "INST-1001",
        "username": "a.lopez",
        "email": "a.lopez@unl.edu.ec",
        "first_name": "Ana",
        "last_name": "López",
    }
    payload.update(overrides)
    return User.objects.create_user(password=PASSWORD, **payload)


def assign_roles(user: User, *codes: str) -> User:
    """Seed the role catalog and assign active roles."""
    call_command("seed_roles", verbosity=0)
    for code in codes:
        UserRole.objects.create(user=user, role=Role.objects.get(code=code))
    return user


def decode_payload(token: str) -> dict:
    """Decode the payload of a JWT without verifying the signature."""
    segment = token.split(".")[1]
    padded = segment + "=" * (-len(segment) % 4)
    return json.loads(base64.urlsafe_b64decode(padded))


def module_view(*permission_classes):
    """Minimal API view gated only by ``permission_classes`` (GET)."""
    gate = list(permission_classes)

    class ProbeView(APIView):
        permission_classes = gate

        def get(self, request):
            return Response({"ok": True})

    return ProbeView.as_view()


def object_view(*permission_classes):
    """Build a view that object-checks a captured target (GET)."""
    gate = list(permission_classes)

    def build(target):
        class ProbeView(APIView):
            permission_classes = gate

            def get(self, request):
                self.check_object_permissions(request, target)
                return Response({"ok": True})

        return ProbeView.as_view()

    return build


def call(view, *, user=None, headers=None):
    """Invoke a probe view, optionally authenticated."""
    request = FACTORY.get("/probe/", **(headers or {}))
    if user is not None:
        force_authenticate(request, user=user)
    return view(request)


# ---------------------------------------------------------------------------
# Contract stubs (the real models arrive with TSK-30 and TSK-46)
# ---------------------------------------------------------------------------


class StubManuscript:
    """Contract: a manuscript carries ``created_by_id``."""

    def __init__(self, created_by_id):
        self.created_by_id = created_by_id


class StubVersion:
    """Contract: a version reaches its manuscript through ``manuscript``."""

    def __init__(self, manuscript):
        self.manuscript = manuscript


class StubAssignment:
    """Contract: an assignment carries ``reviewer_id`` and ``status``."""

    def __init__(self, reviewer_id, status):
        self.reviewer_id = reviewer_id
        self.status = status


class StubEvaluation:
    """Contract: an evaluation reaches its assignment through ``assignment``."""

    def __init__(self, assignment):
        self.assignment = assignment


class TestModulePermissions:
    def test_role_permission_grants_only_the_active_role(self) -> None:
        user = assign_roles(make_user(), "AUTHOR")
        request = FACTORY.get("/")
        # Llamada unitaria sobre la petición cruda: el usuario se fija a mano.
        request.user = user

        assert IsAuthor().has_permission(request, None) is True
        assert IsEditor().has_permission(request, None) is False

    def test_anonymous_is_rejected_by_role_permissions(self) -> None:
        request = FACTORY.get("/")
        assert IsAuthor().has_permission(request, None) is False

    def test_module_denial_answers_403_for_a_valid_session(self) -> None:
        author = assign_roles(make_user(), "AUTHOR")
        response = call(module_view(IsAuthenticated, IsEditor), user=author)

        assert response.status_code == 403
        assert response.data["error"]["code"] == "FORBIDDEN"

    def test_anonymous_sessionless_request_answers_401(self) -> None:
        response = call(module_view(IsAuthenticated, IsEditor))

        assert response.status_code == 401
        assert response.data["error"]["code"] == "AUTH_INVALID"

    def test_multirrole_user_passes_each_module_gate(self) -> None:
        user = assign_roles(make_user(), "AUTHOR", "EDITOR", "ADMIN")

        assert (
            call(module_view(IsAuthenticated, IsAuthor), user=user).status_code == 200
        )
        assert (
            call(module_view(IsAuthenticated, IsEditor), user=user).status_code == 200
        )
        assert call(module_view(IsAuthenticated, IsAdmin), user=user).status_code == 200
        assert (
            call(module_view(IsAuthenticated, IsReviewer), user=user).status_code
            == 403
        )


class TestRevokedRoleBlocksTheNextAction:
    def test_revoked_role_blocks_with_a_still_valid_access_token(self) -> None:
        user = assign_roles(make_user(), "EDITOR")
        client = APIClient()
        login = client.post(
            LOGIN_URL,
            {"identifier": "INST-1001", "password": PASSWORD},
            format="json",
        )
        assert login.status_code == 200
        access = login.json()["access"]

        # El claim del token aún declara EDITOR...
        assert decode_payload(access)["roles"] == ["EDITOR"]

        # ...pero el rol se retira de PostgreSQL a mitad de la sesión.
        UserRole.objects.filter(user=user, role__code="EDITOR").update(
            is_active=False, revoked_at=timezone.now()
        )

        response = call(
            module_view(IsAuthenticated, IsEditor),
            headers={"HTTP_AUTHORIZATION": f"Bearer {access}"},
        )
        assert response.status_code == 403
        assert response.data["error"]["code"] == "FORBIDDEN"

        # El token en sí sigue vigente: la identidad responde 200 y ya
        # no lista el rol retirado.
        me = APIClient().get(ME_URL, HTTP_AUTHORIZATION=f"Bearer {access}")
        assert me.status_code == 200
        assert me.json()["roles"] == []


class TestForeignObjectsAnswer404:
    def test_manuscript_owner_allows_the_registrar_only(self) -> None:
        owner = assign_roles(make_user(), "AUTHOR")
        other = make_user(
            username="b.otro",
            institutional_id="INST-1002",
            email="b.otro@unl.edu.ec",
        )
        probe = object_view(IsAuthenticated, IsAuthor, IsManuscriptOwner)

        own = call(probe(StubManuscript(owner.id)), user=owner)
        assert own.status_code == 200

        foreign = call(probe(StubManuscript(other.id)), user=owner)
        assert foreign.status_code == 404
        assert foreign.data["error"]["code"] == "NOT_FOUND"

    def test_owner_check_walks_related_objects(self) -> None:
        owner = assign_roles(make_user(), "AUTHOR")
        other = make_user(
            username="b.otro",
            institutional_id="INST-1002",
            email="b.otro@unl.edu.ec",
        )
        probe = object_view(IsAuthenticated, IsAuthor, IsManuscriptOwner)

        own_version = call(probe(StubVersion(StubManuscript(owner.id))), user=owner)
        assert own_version.status_code == 200

        foreign_version = call(
            probe(StubVersion(StubManuscript(other.id))), user=owner
        )
        assert foreign_version.status_code == 404

    def test_object_without_manuscript_relation_is_denied(self) -> None:
        author = assign_roles(make_user(), "AUTHOR")
        probe = object_view(IsAuthenticated, IsAuthor, IsManuscriptOwner)

        response = call(probe(object()), user=author)
        assert response.status_code == 404

    def test_assigned_reviewer_checks_ownership_and_status(self) -> None:
        reviewer = assign_roles(make_user(), "REVIEWER")
        other = make_user(
            username="b.otro",
            institutional_id="INST-1002",
            email="b.otro@unl.edu.ec",
        )
        probe = object_view(IsAuthenticated, IsReviewer, IsAssignedReviewer)

        active = call(probe(StubAssignment(reviewer.id, "ACTIVE")), user=reviewer)
        assert active.status_code == 200
        completed = call(
            probe(StubAssignment(reviewer.id, "COMPLETED")), user=reviewer
        )
        assert completed.status_code == 200

        # Ajena, revocada o vencida: 404, sin revelar existencia.
        assert (
            call(probe(StubAssignment(other.id, "ACTIVE")), user=reviewer).status_code
            == 404
        )
        assert (
            call(probe(StubAssignment(reviewer.id, "REVOKED")), user=reviewer).status_code
            == 404
        )
        assert (
            call(probe(StubAssignment(reviewer.id, "EXPIRED")), user=reviewer).status_code
            == 404
        )

    def test_document_download_requires_an_active_assignment(self) -> None:
        reviewer = assign_roles(make_user(), "REVIEWER")
        probe = object_view(
            IsAuthenticated, IsReviewer, IsActiveAssignedReviewer
        )

        active = call(probe(StubAssignment(reviewer.id, "ACTIVE")), user=reviewer)
        assert active.status_code == 200
        completed = call(
            probe(StubAssignment(reviewer.id, "COMPLETED")), user=reviewer
        )
        assert completed.status_code == 404

    def test_assignment_check_walks_related_objects(self) -> None:
        reviewer = assign_roles(make_user(), "REVIEWER")
        probe = object_view(IsAuthenticated, IsReviewer, IsAssignedReviewer)

        evaluation = StubEvaluation(StubAssignment(reviewer.id, "ACTIVE"))
        assert call(probe(evaluation), user=reviewer).status_code == 200


class TestAdminScope:
    def test_admin_does_not_unlock_manuscript_modules(self) -> None:
        admin = assign_roles(make_user(), "ADMIN")
        other = make_user(
            username="b.otro",
            institutional_id="INST-1002",
            email="b.otro@unl.edu.ec",
        )

        # Sin rol AUTHOR el módulo responde 403: nada de manuscritos.
        author_gate = call(module_view(IsAuthenticated, IsAuthor), user=admin)
        assert author_gate.status_code == 403

        # Y el objeto ajeno responde 404, no 403.
        probe = object_view(IsAuthenticated, IsManuscriptOwner)
        foreign = call(probe(StubManuscript(other.id)), user=admin)
        assert foreign.status_code == 404

    def test_admin_module_permission_grants_admin_users(self) -> None:
        admin = assign_roles(make_user(), "ADMIN")
        response = call(module_view(IsAuthenticated, IsAdmin), user=admin)
        assert response.status_code == 200


class TestPublicCatalog:
    def test_anonymous_read_only_access_is_allowed(self) -> None:
        response = call(module_view(IsPublicCatalog))
        assert response.status_code == 200

    def test_unsafe_methods_are_denied(self) -> None:
        class WriteProbe(APIView):
            permission_classes = [IsPublicCatalog]

            def post(self, request):
                return Response({"ok": True})

        # Anónimo: sin sesión que proteger, la respuesta es 401.
        anonymous = WriteProbe.as_view()(FACTORY.post("/probe/"))
        assert anonymous.status_code == 401

        # Autenticado sin importar el rol: el catálogo es de solo lectura.
        reader = assign_roles(make_user(), "AUTHOR")
        request = FACTORY.post("/probe/")
        force_authenticate(request, user=reader)
        denied = WriteProbe.as_view()(request)
        assert denied.status_code == 403
        assert denied.data["error"]["code"] == "FORBIDDEN"
