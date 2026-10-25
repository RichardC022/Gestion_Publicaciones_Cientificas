"""factory_boy factories for the domain test data (plan section 7.1, TSK-23).

Shared by the test suites of every app; the publications, reviews,
notifications and audit factories are added by their own tasks
(TSK-40, TSK-53, TSK-65, TSK-79) on this same module.

The users factories build accounts with unique identifiers and a known
password (:data:`FACTORY_PASSWORD`); the role assignments require
``seed_roles`` to have run, which the test helpers do beforehand.
"""

from __future__ import annotations

from django.contrib.auth.hashers import make_password
from factory import Faker, LazyAttribute, LazyFunction, Sequence, SubFactory
from factory.django import DjangoModelFactory

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
