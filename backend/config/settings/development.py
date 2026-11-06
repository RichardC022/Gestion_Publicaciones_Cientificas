"""Ajustes de desarrollo, para la ejecución local y las pruebas.

Parten de ``base.py`` y activan lo que ayuda a trabajar: ``DEBUG``, el Django Admin, la
documentación interactiva de la API y el correo por consola. **Nunca** se usan en producción.
"""

from .base import *  # noqa: F401,F403
from .base import env_bool, env_list

DEBUG = True

# En desarrollo el Admin está disponible para inspeccionar datos (en producción nunca).
ADMIN_ENABLED = env_bool("ADMIN_ENABLED", True)

# Swagger UI disponible por defecto en desarrollo (se apaga con API_DOCS_ENABLED=0).
API_DOCS_ENABLED = env_bool("API_DOCS_ENABLED", True)

ALLOWED_HOSTS = env_list(
    "ALLOWED_HOSTS",
    ("localhost", "127.0.0.1", "testserver"),
)

CSRF_TRUSTED_ORIGINS = env_list(
    "CSRF_TRUSTED_ORIGINS",
    ("http://localhost", "http://127.0.0.1"),
)

# Los correos no se envían: se imprimen en la consola, así no hace falta un servidor SMTP.
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
