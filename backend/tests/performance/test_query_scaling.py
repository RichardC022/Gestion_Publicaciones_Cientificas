"""Los listados no hacen una consulta por fila (TSK-90).

Cada endpoint de lectura se mide con pocas filas y otra vez con muchas más: si el
número de consultas SQL crece con las filas hay un N+1. El tope fijo de las pruebas
por módulo no lo detecta si el tope es holgado; comparar dos tamaños, sí.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

import pytest
from django.core.management import call_command
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from apps.audit.services import AuditService
from apps.notifications.models import Notification
from apps.publications.models import CorrectionRound, Manuscript, StatusEvent, Verdict
from apps.reviews.models import Assignment
from tests.factories import (
    AssignmentFactory,
    CatalogEntryFactory,
    FinalEvaluationFactory,
    IncidentReportFactory,
    ManuscriptAuthorFactory,
    ManuscriptFactory,
    ManuscriptVersionFactory,
    UserFactory,
    VerdictFactory,
)
from tests.publications.test_manuscript_api import actor, client_for
from tests.reviews.test_editor_api import make_assignment, make_reviewer, submitted

pytestmark = pytest.mark.django_db

SMALL = 2
LARGE = 7  # SMALL + LARGE filas por tipo siguen dentro de la primera página (20).


@dataclass
class World:
    author: object
    editor: object
    reviewer: object
    admin: object
    focus: Manuscript
    versions: int = 1
    handles: dict = field(default_factory=dict)


@pytest.fixture(autouse=True)
def fast_hashing(settings) -> None:
    """Cada fábrica de usuario cifra una contraseña; con PBKDF2 la prueba tarda minutos."""
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


@pytest.fixture(autouse=True)
def seeded_roles(db) -> None:
    call_command("seed_roles", verbosity=0)


@pytest.fixture
def world() -> World:
    author = actor("AUTHOR")
    focus = submitted(author, status="UNDER_REVIEW")
    return World(
        author=author,
        editor=actor("EDITOR"),
        reviewer=make_reviewer(),
        admin=actor("ADMIN"),
        focus=focus,
    )


def co_authored(manuscript: Manuscript) -> None:
    """Dos coautores más, para que el prefetch de autores tenga algo que traer."""
    for _ in range(2):
        ManuscriptAuthorFactory(manuscript=manuscript)


def grow(w: World, rows: int) -> None:
    """Añade ``rows`` filas de cada cosa que algún listado devuelve."""
    now = timezone.now()
    for _ in range(rows):
        # Bandeja del Editor y lista del Autor.
        co_authored(submitted(w.author, status="SUBMITTED"))
        co_authored(submitted(status="SUBMITTED"))

        # Bandeja del Revisor, borradores, vencidas e incidentes.
        reviewed = submitted(status="UNDER_REVIEW")
        co_authored(reviewed)
        assignment = make_assignment(reviewed, w.reviewer, w.editor, days_ago=25)
        FinalEvaluationFactory(
            assignment=assignment, manuscript=reviewed, version=assignment.version, reviewer=w.reviewer
        )
        leaked = submitted(status="UNDER_REVIEW")
        leaked_assignment = make_assignment(leaked, w.reviewer, w.editor)
        IncidentReportFactory(assignment=leaked_assignment, manuscript=leaked, reporter=w.reviewer)

        # Catálogo público.
        entry = CatalogEntryFactory()
        co_authored(entry.manuscript)

        # Revisores del Editor.
        make_reviewer()

        # Notificaciones y auditoría.
        for user in (w.author, w.editor, w.reviewer):
            Notification.objects.create(
                recipient=user, event_key=f"k-{user.pk}-{Notification.objects.count()}",
                event_type="ASSIGNMENT_CREATED", manuscript=reviewed, channel="PANEL",
                payload={"manuscript_code": reviewed.code},
            )
        AuditService.record(action="LOGIN", entity_type="SESSION", actor=w.author)

        # Historial del manuscrito de enfoque: un autor, una versión, ronda,
        # asignación, evaluación y veredicto más por iteración.
        ManuscriptAuthorFactory(manuscript=w.focus)
        w.versions += 1
        version = ManuscriptVersionFactory(
            manuscript=w.focus, version_number=w.versions, round_number=w.versions - 1,
            submitted_by=w.author,
        )
        CorrectionRound.objects.create(manuscript=w.focus, round_number=w.versions - 1)
        StatusEvent.objects.create(manuscript=w.focus, from_status="UNDER_REVIEW", to_status="UNDER_REVIEW")
        past = AssignmentFactory(
            manuscript=w.focus, version=version, reviewer=UserFactory(), assigned_by=w.editor,
            status=Assignment.Status.COMPLETED, assigned_at=now - timedelta(days=30),
            due_at=now - timedelta(days=10),
        )
        final = FinalEvaluationFactory(
            assignment=past, manuscript=w.focus, version=version, reviewer=past.reviewer
        )
        VerdictFactory(
            evaluation=final, manuscript=w.focus, version=version, editor=w.editor,
            decision=Verdict.Decision.REQUIRES_CORRECTIONS, observations="Ajustar la metodología.",
        )


#: nombre -> (actor, ruta). La ruta recibe el mundo; ``focus`` es el manuscrito de enfoque.
ENDPOINTS = {
    "editor: bandeja": ("editor", lambda w: "/api/editor/submissions/"),
    "editor: detalle": ("editor", lambda w: f"/api/editor/submissions/{w.focus.pk}/"),
    "editor: revisores": ("editor", lambda w: "/api/editor/reviewers/"),
    "editor: vencidas": ("editor", lambda w: "/api/editor/assignments/expired/"),
    "editor: incidentes": ("editor", lambda w: "/api/editor/incidents/"),
    "editor: asignaciones": ("editor", lambda w: f"/api/editor/manuscripts/{w.focus.pk}/assignments/"),
    "editor: evaluaciones": ("editor", lambda w: f"/api/editor/manuscripts/{w.focus.pk}/evaluations/"),
    "editor: veredictos": ("editor", lambda w: f"/api/editor/manuscripts/{w.focus.pk}/verdicts/"),
    "autor: lista": ("author", lambda w: "/api/manuscripts/"),
    "autor: detalle": ("author", lambda w: f"/api/manuscripts/{w.focus.pk}/"),
    "autor: historial": ("author", lambda w: f"/api/manuscripts/{w.focus.pk}/history/"),
    "autor: versiones": ("author", lambda w: f"/api/manuscripts/{w.focus.pk}/versions/"),
    "revisor: bandeja": ("reviewer", lambda w: "/api/reviewer/assignments/"),
    "revisor: evaluaciones": ("reviewer", lambda w: "/api/reviewer/evaluations/"),
    "catálogo": (None, lambda w: "/api/catalog/"),
    "auditoría": ("admin", lambda w: "/api/admin/audit/"),
    "notificaciones": ("author", lambda w: "/api/notifications/"),
    "tablero del autor": ("author", lambda w: "/api/dashboard/"),
    "tablero del editor": ("editor", lambda w: "/api/dashboard/"),
    "tablero del revisor": ("reviewer", lambda w: "/api/dashboard/"),
}


def measure(w: World, who: str | None, url: str):
    client = APIClient() if who is None else client_for(getattr(w, who))
    with CaptureQueriesContext(connection) as captured:
        response = client.get(url)
    assert response.status_code == 200, response.content
    body = response.json()
    rows = len(body["results"]) if isinstance(body, dict) and "results" in body else None
    return len(captured), rows, captured


@pytest.mark.parametrize("name", list(ENDPOINTS))
def test_the_number_of_queries_does_not_grow_with_the_rows(world, name) -> None:
    who, build_url = ENDPOINTS[name]
    grow(world, SMALL)
    few, few_rows, _ = measure(world, who, build_url(world))

    grow(world, LARGE)
    many, many_rows, captured = measure(world, who, build_url(world))

    detail = "\n".join(q["sql"][:160] for q in captured)
    assert many == few, f"{name}: {few} consultas con {few_rows} filas y {many} con {many_rows}\n{detail}"
    if few_rows is not None:
        assert many_rows > few_rows, f"{name}: la prueba no aumentó las filas ({few_rows} → {many_rows})"
