"""Siembra las cuentas del E2E (TSK-91).

Se ejecuta DENTRO del contenedor del backend del stack aislado «gpc_e2e»:

    docker compose -p gpc_e2e ... exec -T -e E2E_PASSWORD backend python manage.py shell < scripts/e2e/seed_e2e.py

La contraseña (E2E_PASSWORD) se genera en cada corrida y no se guarda. Es idempotente.
Las personas tienen nombres reconocibles para comprobar que ninguna identidad cruza
el doble ciego (el Autor nunca ve al Revisor ni al revés).
"""

import os

from django.contrib.auth import get_user_model
from django.core.management import call_command

from apps.users.models import ReviewerProfile, Role, UserRole

PASSWORD = os.environ["E2E_PASSWORD"]
call_command("seed_roles", verbosity=0)
User = get_user_model()

PEOPLE = [
    ("e2e-autor-revisor", "Elena", "Cabrera Rojas", ["AUTHOR", "REVIEWER"]),
    ("e2e-autor", "Marcela", "Quizhpe Ordóñez", ["AUTHOR"]),
    ("e2e-editor", "Esteban", "Aguirre Mora", ["EDITOR"]),
    ("e2e-revisor", "Rodrigo", "Valarezo Cueva", ["REVIEWER"]),
    ("e2e-admin", "Adriana", "Paredes León", ["ADMIN"]),
]

for identifier, first_name, last_name, roles in PEOPLE:
    user, _ = User.objects.get_or_create(
        institutional_id=identifier,
        defaults={
            "username": identifier,
            "email": f"{identifier}@e2e.unl.edu.ec",
            "first_name": first_name,
            "last_name": last_name,
        },
    )
    user.set_password(PASSWORD)
    user.save(update_fields=["password"])
    for code in roles:
        UserRole.objects.get_or_create(user=user, role=Role.objects.get(code=code), is_active=True)
    if "REVIEWER" in roles:
        ReviewerProfile.objects.update_or_create(
            user=user, # Varias pruebas dejan una asignación activa cada una: el tope normal (3) las bloquearía.
            defaults={"expertise_areas": ["Agronomía"], "is_available": True, "max_active_assignments": 50}
        )
print(f"SEED_OK people={len(PEOPLE)}")
