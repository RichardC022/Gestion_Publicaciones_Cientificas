"""Siembra las cuentas de la prueba de carga (TSK-86).

Se ejecuta DENTRO del contenedor del backend, contra la base del stack
aislado de la prueba (nunca contra la base de trabajo):

    docker compose -p gpc_load ... exec -T backend python manage.py shell < scripts/load/seed_users.py

Variables: LOAD_PASSWORD (obligatoria, se genera en cada corrida y no se
guarda), LOAD_USERS (cantidad de autores, 50 por defecto). Es idempotente.
"""

import os

from django.contrib.auth import get_user_model
from django.core.management import call_command

from apps.users.models import ReviewerProfile, Role, UserRole

PASSWORD = os.environ["LOAD_PASSWORD"]
AUTHORS = int(os.environ.get("LOAD_USERS", "50"))

call_command("seed_roles", verbosity=0)
User = get_user_model()


def ensure(identifier: str, first_name: str, role_code: str) -> None:
    user, created = User.objects.get_or_create(
        institutional_id=identifier,
        defaults={
            "username": identifier,
            "email": f"{identifier}@carga.invalid",
            "first_name": first_name,
            "last_name": "Carga",
        },
    )
    # La contraseña se fija siempre: cada corrida usa una nueva.
    user.set_password(PASSWORD)
    user.save(update_fields=["password"])
    UserRole.objects.get_or_create(
        user=user, role=Role.objects.get(code=role_code), is_active=True
    )


for number in range(AUTHORS):
    ensure(f"load-author-{number:02d}", f"Autor{number:02d}", "AUTHOR")
ensure("load-editor", "Editor", "EDITOR")
ensure("load-reviewer", "Revisor", "REVIEWER")
# Sin perfil disponible y con el área del manuscrito, el Editor no puede asignarlo.
ReviewerProfile.objects.update_or_create(
    user=User.objects.get(institutional_id="load-reviewer"),
    defaults={"expertise_areas": ["Agronomía"], "is_available": True},
)
print(f"SEED_OK authors={AUTHORS}")
