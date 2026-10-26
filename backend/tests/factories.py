"""factory_boy factories for the domain test data (plan section 7.1, TSK-23).

Shared by the test suites of every app; the publications factories
(TSK-40) live here, and the reviews, notifications and audit ones are
added by their own tasks (TSK-53, TSK-65, TSK-79) on this same module.

The users factories build accounts with unique identifiers and a known
password (:data:`FACTORY_PASSWORD`); the role assignments require
``seed_roles`` to have run, which the test helpers do beforehand.
"""

from __future__ import annotations

from django.contrib.auth.hashers import make_password
from factory import Faker, LazyAttribute, LazyFunction, SelfAttribute, Sequence, SubFactory
from factory.django import DjangoModelFactory

from apps.publications.models import (
    CorrectionRound,
    Manuscript,
    ManuscriptAuthor,
    ManuscriptVersion,
    StatusEvent,
)
from apps.users.models import Role, User, UserRole

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
