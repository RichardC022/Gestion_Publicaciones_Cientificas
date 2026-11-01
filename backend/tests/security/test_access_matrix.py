"""Access matrix of the whole API (TSK-89, plan sections 6.2 and 6.3).

Every route of the ``/api/`` URLconf is classified here by *module role* and by
*object scope*, and the test runs it against every kind of actor:

* no credentials  -> ``401``;
* signed in but without the module's role (including the Administrator on the
  manuscript, evaluation and PDF routes) -> ``403``;
* the module's role, but an object that is not theirs -> ``404``, the same
  answer as an object that does not exist;
* in scope -> anything but ``401``/``403``/``404`` (the body is empty on
  purpose, so a ``400`` or ``409`` is the expected, harmless answer).

``test_every_route_is_classified`` fails when somebody adds an endpoint without
classifying it, so the matrix cannot silently go stale.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

import pytest
from django.urls import get_resolver
from rest_framework.test import APIClient
from rest_framework.views import APIView

from apps.audit.models import AuditLog
from apps.notifications.models import Notification
from apps.publications.models import Verdict
from apps.reviews.models import Evaluation, IncidentReport
from apps.users.models import UserRole
from tests.factories import UserRoleFactory
from tests.phase5 import AUTHOR_TOKENS, EVALUATION, REVIEWER_TOKENS, Lifecycle
from tests.publications.test_manuscript_api import actor, client_for
from tests.publications.test_submission import media_root, seeded_roles, submit  # noqa: F401
from tests.reviews.test_editor_api import make_reviewer

pytestmark = pytest.mark.django_db

ANONYMOUS, OWNER, OTHER_AUTHOR, ASSIGNED, OTHER_REVIEWER, EDITOR, ADMIN, NO_ROLE = (
    "anonymous", "owner", "other_author", "assigned", "other_reviewer", "editor", "admin", "no_role",
)
ACTORS = (ANONYMOUS, OWNER, OTHER_AUTHOR, ASSIGNED, OTHER_REVIEWER, EDITOR, ADMIN, NO_ROLE)
ROLE_OF = {
    OWNER: "AUTHOR", OTHER_AUTHOR: "AUTHOR", ASSIGNED: "REVIEWER",
    OTHER_REVIEWER: "REVIEWER", EDITOR: "EDITOR", ADMIN: "ADMIN", NO_ROLE: None,
}
PUBLIC, AUTHENTICATED = "PUBLIC", "AUTHENTICATED"


@dataclass(frozen=True)
class Rule:
    """Who may call a route: ``module`` roles and, for an object route, ``scope`` actors."""

    module: tuple[str, ...] | str
    scope: tuple[str, ...] | None = None
    obj: str | None = None  # key of the world's objects that fills <uuid:pk>


AUTHOR_ONLY = Rule(("AUTHOR",), (OWNER,), "manuscript")
AUTHOR_OR_EDITOR = Rule(("AUTHOR", "EDITOR"), (OWNER, EDITOR), "manuscript")
EDITOR_OBJECT = Rule(("EDITOR",), (EDITOR,), "manuscript")
REVIEWER_OBJECT = Rule(("REVIEWER",), (ASSIGNED,), "assignment")

#: (method, route) -> rule. Routes are written as the URLconf spells them.
MATRIX: dict[tuple[str, str], Rule] = {
    ("GET", "api/admin/audit/"): Rule(("ADMIN",)),
    ("GET", "api/admin/audit/<uuid:pk>/"): Rule(("ADMIN",), None, "audit"),
    ("POST", "api/admin/verdicts/<uuid:pk>/authorize-correction/"): Rule(("ADMIN",), None, "verdict"),
    ("POST", "api/auth/logout/"): Rule(AUTHENTICATED),
    ("GET", "api/auth/me/"): Rule(AUTHENTICATED),
    ("GET", "api/catalog/"): Rule(PUBLIC),
    ("GET", "api/catalog/<str:code>/"): Rule(PUBLIC),
    ("GET", "api/catalog/<str:code>/document/"): Rule(PUBLIC),
    ("GET", "api/dashboard/"): Rule(AUTHENTICATED),
    ("POST", "api/editor/assignments/<uuid:pk>/revoke/"): Rule(("EDITOR",), None, "assignment"),
    ("GET", "api/editor/assignments/expired/"): Rule(("EDITOR",)),
    ("GET", "api/editor/incidents/"): Rule(("EDITOR",)),
    ("POST", "api/editor/incidents/<uuid:pk>/resolve/"): Rule(("EDITOR",), None, "incident"),
    ("GET", "api/editor/manuscripts/<uuid:pk>/assignments/"): EDITOR_OBJECT,
    ("POST", "api/editor/manuscripts/<uuid:pk>/assignments/"): EDITOR_OBJECT,
    ("GET", "api/editor/manuscripts/<uuid:pk>/evaluations/"): EDITOR_OBJECT,
    ("GET", "api/editor/manuscripts/<uuid:pk>/verdicts/"): EDITOR_OBJECT,
    ("POST", "api/editor/manuscripts/<uuid:pk>/verdicts/"): EDITOR_OBJECT,
    ("GET", "api/editor/reviewers/"): Rule(("EDITOR",)),
    ("GET", "api/editor/submissions/"): Rule(("EDITOR",)),
    ("GET", "api/editor/submissions/<uuid:pk>/"): EDITOR_OBJECT,
    ("POST", "api/editor/submissions/<uuid:pk>/start-review/"): EDITOR_OBJECT,
    ("GET", "api/manuscripts/"): Rule(("AUTHOR", "EDITOR")),
    ("POST", "api/manuscripts/"): Rule(("AUTHOR",)),
    ("GET", "api/manuscripts/<uuid:pk>/"): AUTHOR_OR_EDITOR,
    ("PATCH", "api/manuscripts/<uuid:pk>/"): AUTHOR_ONLY,
    ("POST", "api/manuscripts/<uuid:pk>/draft-file/"): AUTHOR_ONLY,
    ("GET", "api/manuscripts/<uuid:pk>/history/"): AUTHOR_OR_EDITOR,
    ("POST", "api/manuscripts/<uuid:pk>/submit/"): AUTHOR_ONLY,
    ("GET", "api/manuscripts/<uuid:pk>/versions/"): AUTHOR_OR_EDITOR,
    ("POST", "api/manuscripts/<uuid:pk>/versions/"): AUTHOR_ONLY,
    ("GET", "api/manuscripts/<uuid:pk>/versions/<uuid:version_id>/file/"): AUTHOR_OR_EDITOR,
    ("POST", "api/manuscripts/<uuid:pk>/withdraw/"): AUTHOR_ONLY,
    ("GET", "api/notifications/"): Rule(AUTHENTICATED),
    ("PATCH", "api/notifications/<uuid:pk>/read/"): Rule(AUTHENTICATED, (OWNER,), "notification"),
    ("POST", "api/notifications/read-all/"): Rule(AUTHENTICATED),
    ("GET", "api/reviewer/assignments/"): Rule(("REVIEWER",)),
    ("GET", "api/reviewer/assignments/<uuid:pk>/"): REVIEWER_OBJECT,
    ("POST", "api/reviewer/assignments/<uuid:pk>/conflict/"): REVIEWER_OBJECT,
    ("GET", "api/reviewer/assignments/<uuid:pk>/document/"): REVIEWER_OBJECT,
    ("GET", "api/reviewer/assignments/<uuid:pk>/evaluation/"): REVIEWER_OBJECT,
    ("PUT", "api/reviewer/assignments/<uuid:pk>/evaluation/"): REVIEWER_OBJECT,
    ("POST", "api/reviewer/assignments/<uuid:pk>/evaluation/submit/"): REVIEWER_OBJECT,
    ("POST", "api/reviewer/assignments/<uuid:pk>/identity-leak/"): REVIEWER_OBJECT,
    ("GET", "api/reviewer/evaluations/"): Rule(("REVIEWER",)),
    ("GET", "api/reviewer/evaluations/<uuid:pk>/"): Rule(("REVIEWER",), (ASSIGNED,), "evaluation"),
}

#: Routes that are open by design and carry their own tests.
OUTSIDE_THE_MATRIX = {"api/auth/login/", "api/auth/refresh/", "api/health/"}


def declared_routes() -> set[tuple[str, str]]:
    found: set[tuple[str, str]] = set()

    def walk(patterns, prefix: str = "") -> None:
        for pattern in patterns:
            if hasattr(pattern, "url_patterns"):
                walk(pattern.url_patterns, prefix + str(pattern.pattern))
                continue
            view = getattr(pattern.callback, "cls", None) or getattr(pattern.callback, "view_class", None)
            if view and issubclass(view, APIView):
                route = prefix + str(pattern.pattern)
                if route.startswith("api/") and route not in OUTSIDE_THE_MATRIX:
                    for method in view.http_method_names:
                        if method not in ("options", "head") and hasattr(view, method):
                            found.add((method.upper(), route))

    walk(get_resolver().url_patterns)
    return found


# ---------------------------------------------------------------------------
# The world: one accepted article, one manuscript in review, foreign people
# ---------------------------------------------------------------------------
@dataclass
class World:
    flow: Lifecycle
    other_author: object
    other_reviewer: object
    objects: dict

    def client(self, label: str) -> APIClient:
        users = {
            OWNER: self.flow.author, OTHER_AUTHOR: self.other_author, ASSIGNED: self.flow.reviewer,
            OTHER_REVIEWER: self.other_reviewer, EDITOR: self.flow.editor, ADMIN: self.flow.admin,
        }
        if label == ANONYMOUS:
            return APIClient()
        return client_for(users.get(label) or self.no_role)

    def url(self, route: str, *, pk: str | None = None) -> str:
        values = {"<uuid:pk>": pk, "<uuid:version_id>": self.objects["version"], "<str:code>": self.objects["code"]}
        for placeholder, value in values.items():
            route = route.replace(placeholder, str(value))
        return "/" + route


@pytest.fixture
def world(django_capture_on_commit_callbacks, submit, media_root) -> World:  # noqa: F811
    flow = Lifecycle.create(django_capture_on_commit_callbacks, submit)
    accepted = flow.accepted()
    verdict = Verdict.objects.get(manuscript=accepted)
    final_evaluation = Evaluation.objects.get(assignment__manuscript=accepted, status=Evaluation.Status.FINAL)
    notification = Notification.objects.filter(recipient=flow.author, channel="PANEL").first()

    in_review = flow.submit_manuscript()
    assignment = flow.start_review()
    client_for(flow.reviewer).put(
        f"/api/reviewer/assignments/{assignment.pk}/evaluation/", EVALUATION, format="json", HTTP_IF_MATCH='"0"'
    )
    reported = client_for(flow.reviewer).post(
        f"/api/reviewer/assignments/{assignment.pk}/identity-leak/",
        {"report_type": "IDENTITY_LEAK", "description": "El PDF menciona al grupo de investigación."},
        format="json",
    )
    assert reported.status_code in (200, 201), reported.content

    world = World(
        flow=flow,
        other_author=actor("AUTHOR", first_name="Otra", last_name="Persona", email="otra.persona@unl.edu.ec"),
        other_reviewer=make_reviewer(first_name="Otro", last_name="Revisor", email="otro.revisor@unl.edu.ec"),
        objects={
            "manuscript": in_review.pk, "assignment": assignment.pk, "code": accepted.code,
            "version": in_review.versions.first().pk, "verdict": verdict.pk,
            "evaluation": final_evaluation.pk, "notification": notification.pk,
            "incident": IncidentReport.objects.get(assignment=assignment).pk,
            "audit": AuditLog.objects.order_by("-id").first().event_id,
        },
    )
    world.no_role = actor()
    return world


def expected_denial(label: str, rule: Rule) -> int | None:
    """The status a denied actor must get, or ``None`` when the actor is allowed in."""
    if rule.module == PUBLIC:
        return None
    if label == ANONYMOUS:
        return 401
    if rule.module == AUTHENTICATED:
        denied_by_scope = rule.scope is not None and label not in rule.scope
        return 404 if denied_by_scope else None
    if ROLE_OF[label] not in rule.module:
        return 403
    if rule.scope is not None and label not in rule.scope:
        return 404
    return None


def call(client: APIClient, method: str, url: str):
    return getattr(client, method.lower())(url, {}, format="json")


class TestEveryRouteIsClassified:
    def test_every_route_is_classified(self) -> None:
        declared = declared_routes()
        assert declared - set(MATRIX) == set(), "rutas nuevas sin clasificar en la matriz de acceso"
        assert set(MATRIX) - declared == set(), "la matriz clasifica rutas que ya no existen"


class TestAccessMatrix:
    @pytest.mark.parametrize("label", ACTORS)
    def test_each_actor_gets_exactly_the_planned_answer(self, world, label) -> None:
        mismatches = []
        for (method, route), rule in sorted(MATRIX.items()):
            url = world.url(route, pk=world.objects.get(rule.obj) if rule.obj else None)
            status = call(world.client(label), method, url).status_code
            denial = expected_denial(label, rule)
            ok = status == denial if denial else status not in (401, 403, 404)
            if not ok:
                mismatches.append(f"{method} {route}: esperaba {denial or 'acceso'}, obtuvo {status}")
        assert not mismatches, f"{label}:\n" + "\n".join(mismatches)

    def test_the_administrator_reaches_no_manuscript_evaluation_or_pdf(self, world) -> None:
        admin = world.client(ADMIN)
        o = world.objects
        urls = [
            f"/api/manuscripts/{o['manuscript']}/", f"/api/manuscripts/{o['manuscript']}/history/",
            f"/api/manuscripts/{o['manuscript']}/versions/",
            f"/api/manuscripts/{o['manuscript']}/versions/{o['version']}/file/",
            f"/api/editor/submissions/{o['manuscript']}/", f"/api/editor/manuscripts/{o['manuscript']}/evaluations/",
            f"/api/reviewer/assignments/{o['assignment']}/", f"/api/reviewer/assignments/{o['assignment']}/document/",
            f"/api/reviewer/assignments/{o['assignment']}/evaluation/", f"/api/reviewer/evaluations/{o['evaluation']}/",
        ]
        assert [admin.get(url).status_code for url in urls] == [403] * len(urls)
        assert admin.get("/api/manuscripts/").status_code == 403


class TestForeignAndMissingObjectsAreIndistinguishable:
    #: Routes where somebody holds the module's role yet the object is not theirs.
    OBJECT_ROUTES = sorted(
        (method, route) for (method, route), rule in MATRIX.items()
        if rule.scope is not None and rule.module != ("EDITOR",)
    )

    @staticmethod
    def envelope(response) -> dict:
        body = response.json()["error"]
        return {key: value for key, value in body.items() if key != "request_id"}

    @pytest.mark.parametrize("method,route", OBJECT_ROUTES)
    def test_a_foreign_object_answers_like_one_that_does_not_exist(self, world, method, route) -> None:
        rule = MATRIX[(method, route)]
        foreign = OTHER_REVIEWER if rule.module == ("REVIEWER",) else OTHER_AUTHOR
        client = world.client(foreign)
        real = call(client, method, world.url(route, pk=world.objects[rule.obj]))
        missing = call(client, method, world.url(route, pk=uuid4()))
        assert real.status_code == missing.status_code == 404
        assert self.envelope(real) == self.envelope(missing)


class TestRetiredRoleIsDeniedOnTheNextRequest:
    @pytest.mark.parametrize("label,module", [(OWNER, "AUTHOR"), (ASSIGNED, "REVIEWER"), (EDITOR, "EDITOR"), (ADMIN, "ADMIN")])
    def test_a_revoked_role_loses_every_route_of_its_module(self, world, label, module) -> None:
        client = world.client(label)
        UserRole.objects.filter(role__code=module, is_active=True, user=client.handler._force_user).update(is_active=False)
        leaks = []
        for (method, route), rule in sorted(MATRIX.items()):
            if rule.module in (PUBLIC, AUTHENTICATED) or module not in rule.module:
                continue
            url = world.url(route, pk=world.objects.get(rule.obj) if rule.obj else None)
            status = call(client, method, url).status_code
            if status != 403:
                leaks.append(f"{method} {route}: {status}")
        assert not leaks, "\n".join(leaks)


class TestEditorWithAConflict:
    def test_an_editor_who_is_the_author_cannot_reach_the_manuscript_as_editor(self, world) -> None:
        both = world.flow.author
        UserRoleFactory(user=both, role_code="EDITOR")
        client = client_for(both)
        o = world.objects
        urls = [
            f"/api/editor/submissions/{o['manuscript']}/", f"/api/editor/manuscripts/{o['manuscript']}/evaluations/",
            f"/api/editor/manuscripts/{o['manuscript']}/assignments/", f"/api/editor/manuscripts/{o['manuscript']}/verdicts/",
        ]
        assert [client.get(url).status_code for url in urls] == [404] * len(urls)


class TestDraftsOfOthers:
    def test_the_editor_does_not_see_a_draft_nor_its_files(self, world) -> None:
        from tests.publications.test_submission import ready_draft

        draft = ready_draft(world.other_author)
        editor = world.client(EDITOR)
        for url in (f"/api/manuscripts/{draft.pk}/", f"/api/manuscripts/{draft.pk}/history/",
                    f"/api/manuscripts/{draft.pk}/versions/", f"/api/editor/submissions/{draft.pk}/"):
            assert editor.get(url).status_code == 404, url
        listed = editor.get("/api/manuscripts/").json()["results"]
        assert str(draft.pk) not in {row["id"] for row in listed}


class TestNoIdentityOutsideTheEditorialRoles:
    """Every reviewer-facing GET, and the other roles' notifications, hold no identity."""

    def test_no_reviewer_response_names_the_author(self, world) -> None:
        o = world.objects
        reviewer = world.client(ASSIGNED)
        urls = [
            "/api/auth/me/", "/api/dashboard/", "/api/notifications/", "/api/reviewer/assignments/",
            f"/api/reviewer/assignments/{o['assignment']}/", f"/api/reviewer/assignments/{o['assignment']}/evaluation/",
            "/api/reviewer/evaluations/", f"/api/reviewer/evaluations/{o['evaluation']}/",
        ]
        forbidden = (*AUTHOR_TOKENS, "metadata_snapshot", "original_filename", "created_by", "affiliation")
        found = []
        for url in urls:
            body = reviewer.get(url).content.decode()
            found += [f"{url}: {token}" for token in forbidden if token.lower() in body.lower()]
        assert not found, "\n".join(found)

    def test_the_administrators_audit_holds_no_identity_of_either_side(self, world) -> None:
        admin = world.client(ADMIN)
        body = admin.get("/api/admin/audit/", {"page_size": 100}).content.decode().lower()
        leaked = [token for token in (*AUTHOR_TOKENS, *REVIEWER_TOKENS, "metadata_snapshot") if token.lower() in body]
        assert not leaked, leaked

    def test_the_author_receives_no_reviewer_identity(self, world) -> None:
        author = world.client(OWNER)
        body = "".join(
            author.get(url).content.decode()
            for url in ("/api/notifications/", f"/api/manuscripts/{world.objects['manuscript']}/",
                        f"/api/manuscripts/{world.objects['manuscript']}/history/")
        ).lower()
        assert [token for token in REVIEWER_TOKENS if token.lower() in body] == []
