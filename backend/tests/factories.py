"""factory_boy factories for the domain test data (plan section 7.1, TSK-23).

Shared by the test suites of every app; the publications factories
(TSK-40) and the reviews ones (TSK-53) live here, and the notifications
and audit ones are added by their own tasks (TSK-65, TSK-79) on this
same module.

The users factories build accounts with unique identifiers and a known
password (:data:`FACTORY_PASSWORD`); the role assignments require
``seed_roles`` to have run, which the test helpers do beforehand.
"""

from __future__ import annotations

from datetime import timedelta

from django.contrib.auth.hashers import make_password
from django.utils import timezone
from factory import Faker, LazyAttribute, LazyFunction, SelfAttribute, Sequence, SubFactory
from factory.django import DjangoModelFactory

from apps.publications.models import (
    CatalogEntry,
    CorrectionRound,
    Manuscript,
    ManuscriptAuthor,
    ManuscriptVersion,
    StatusEvent,
    Verdict,
)
from apps.reviews.models import ASSIGNMENT_DAYS, Assignment, Evaluation, IncidentReport
from apps.users.models import ReviewerProfile, Role, User, UserRole

#: Plain password of every account built by :class:`UserFactory`.
FACTORY_PASSWORD = "institucional-123"


class UserFactory(DjangoModelFactory):
    """Institutional account with unique identifiers and Faker names."""

    class Meta:
        model = User

    institutional_id = Sequence(lambda n: f"INST-{n:04d}")
    username = LazyAttribute(lambda o: o.institutional_id.lower().replace("-", "."))
    email = LazyAttribute(lambda o: f"{o.username}@unl.edu.ec")
    first_name = Faker("first_name", locale="es")
    last_name = Faker("last_name", locale="es")
    # Hash persistido directamente en el INSERT: sin post-generación
    # y sin segundo save.
    password = LazyFunction(lambda: make_password(FACTORY_PASSWORD))


class UserRoleFactory(DjangoModelFactory):
    """Active role assignment; requires ``seed_roles`` beforehand."""

    class Meta:
        model = UserRole
        exclude = ("role_code",)

    user = SubFactory(UserFactory)
    role_code = "AUTHOR"
    role = LazyAttribute(lambda o: Role.objects.get(code=o.role_code))


class ManuscriptFactory(DjangoModelFactory):
    """An active ``DRAFT`` with complete metadata.

    The code comes from the PostgreSQL sequence on ``save()``. It creates
    no authors, versions or rounds: build those explicitly so each test
    states the history it needs.
    """

    class Meta:
        model = Manuscript

    title = "Efecto del clima en cultivos andinos"
    abstract = "Resumen del estudio."
    keywords = LazyFunction(lambda: ["clima", "cultivos"])
    area = "Agronomía"
    language = "es"
    created_by = SubFactory(UserFactory)


class ManuscriptAuthorFactory(DjangoModelFactory):
    """A non-corresponding author; ``author_order`` is unique per manuscript."""

    class Meta:
        model = ManuscriptAuthor

    manuscript = SubFactory(ManuscriptFactory)
    user = None
    full_name = Faker("name", locale="es")
    email = Sequence(lambda n: f"autor{n:04d}@otra.edu")
    affiliation = "Universidad Nacional de Loja"
    is_corresponding = False
    author_order = Sequence(lambda n: n + 1)


class ManuscriptVersionFactory(DjangoModelFactory):
    """A formal version row with valid hashes and a snapshot.

    It writes no files: tests that need the PDFs go through the API.
    """

    class Meta:
        model = ManuscriptVersion

    manuscript = SubFactory(ManuscriptFactory)
    version_number = 1
    round_number = 0
    original_file_path = LazyAttribute(
        lambda o: f"manuscripts/{o.manuscript.pk}/v{o.version_number:04d}/original.pdf"
    )
    original_filename = "articulo.pdf"
    original_size_bytes = 1024
    original_sha256 = "a" * 64
    sanitized_file_path = LazyAttribute(
        lambda o: f"manuscripts/{o.manuscript.pk}/v{o.version_number:04d}/sanitized.pdf"
    )
    sanitized_sha256 = "a" * 64
    metadata_snapshot = LazyAttribute(lambda o: {"title": o.manuscript.title})
    metadata_sha256 = "a" * 64
    submitted_by = SelfAttribute("manuscript.created_by")


class CorrectionRoundFactory(DjangoModelFactory):
    """An open correction round."""

    class Meta:
        model = CorrectionRound

    manuscript = SubFactory(ManuscriptFactory)
    round_number = 0


class StatusEventFactory(DjangoModelFactory):
    """The initial status event of a manuscript."""

    class Meta:
        model = StatusEvent

    manuscript = SubFactory(ManuscriptFactory)
    to_status = "DRAFT"


class ReviewerProfileFactory(DjangoModelFactory):
    """Availability and expertise of a reviewer; the role is granted apart.

    The account needs an active ``REVIEWER`` role (``UserRoleFactory``)
    to be eligible for an assignment.
    """

    class Meta:
        model = ReviewerProfile

    user = SubFactory(UserFactory)
    expertise_areas = LazyFunction(lambda: ["Agronomía"])
    is_available = True
    max_active_assignments = 3


class AssignmentFactory(DjangoModelFactory):
    """An ``ACTIVE`` assignment with the exact 20-day deadline.

    The version belongs to the same manuscript. It does not touch the
    manuscript status: the test states the editorial state it needs.
    """

    class Meta:
        model = Assignment

    manuscript = SubFactory(ManuscriptFactory, status=Manuscript.Status.UNDER_REVIEW)
    version = SubFactory(
        ManuscriptVersionFactory, manuscript=SelfAttribute("..manuscript")
    )
    reviewer = SubFactory(UserFactory)
    assigned_by = SubFactory(UserFactory)
    assigned_at = LazyFunction(timezone.now)
    due_at = LazyAttribute(lambda o: o.assigned_at + timedelta(days=ASSIGNMENT_DAYS))


class EvaluationFactory(DjangoModelFactory):
    """A private ``DRAFT`` evaluation of its assignment."""

    class Meta:
        model = Evaluation

    assignment = SubFactory(AssignmentFactory)
    manuscript = SelfAttribute("assignment.manuscript")
    version = SelfAttribute("assignment.version")
    reviewer = SelfAttribute("assignment.reviewer")
    status = Evaluation.Status.DRAFT


class FinalEvaluationFactory(EvaluationFactory):
    """A complete ``FINAL`` evaluation; immutable once created."""

    status = Evaluation.Status.FINAL
    recommendation = Evaluation.Recommendation.ACCEPT
    comments_for_author = "Comentarios para el autor."
    originality_score = 4
    methodology_score = 4
    clarity_score = 4
    relevance_score = 4
    ethics_score = 5
    submitted_at = LazyFunction(timezone.now)


class IncidentReportFactory(DjangoModelFactory):
    """An ``OPEN`` identity-leak report written by the assignment's reviewer.

    It writes only the row: no notification, revocation or status change.
    """

    class Meta:
        model = IncidentReport

    assignment = SubFactory(AssignmentFactory)
    manuscript = SelfAttribute("assignment.manuscript")
    reporter = SelfAttribute("assignment.reviewer")
    report_type = IncidentReport.ReportType.IDENTITY_LEAK
    description = "El texto menciona la afiliación de los autores."


class VerdictFactory(DjangoModelFactory):
    """A normal ``ACCEPTED`` verdict over a final evaluation.

    It writes only the row: no status change, round or catalog entry.
    Go through ``register_verdict`` to exercise the real flow.
    """

    class Meta:
        model = Verdict

    evaluation = SubFactory(FinalEvaluationFactory)
    manuscript = SelfAttribute("evaluation.manuscript")
    version = SelfAttribute("evaluation.version")
    editor = SubFactory(UserFactory)
    decision = Verdict.Decision.ACCEPTED


class CatalogEntryFactory(DjangoModelFactory):
    """An active catalog entry; it writes no file."""

    class Meta:
        model = CatalogEntry

    manuscript = SubFactory(ManuscriptFactory, status=Manuscript.Status.ACCEPTED)
    version = SubFactory(
        ManuscriptVersionFactory, manuscript=SelfAttribute("..manuscript")
    )
    public_file_path = LazyAttribute(lambda o: f"{o.manuscript.pk}/{o.version.pk}.pdf")
