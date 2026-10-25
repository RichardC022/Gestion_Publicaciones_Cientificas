"""Production settings with strict environment validation."""

from __future__ import annotations

import os

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401,F403
from .base import env_bool, env_list


def required_env(name: str) -> str:
    """Return a required environment variable or fail with a clear message."""
    value = os.environ.get(name)
    if not value:
        raise ImproperlyConfigured(
            f"La variable de entorno {name} es obligatoria en producción."
        )
    if value == "change-me":
        raise ImproperlyConfigured(
            f"La variable de entorno {name} contiene un valor de ejemplo."
        )
    return value


DEBUG = False

SECRET_KEY = required_env("DJANGO_SECRET_KEY")
POSTGRES_DB = required_env("POSTGRES_DB")
POSTGRES_USER = required_env("POSTGRES_USER")
POSTGRES_PASSWORD = required_env("POSTGRES_PASSWORD")
POSTGRES_HOST = required_env("POSTGRES_HOST")
POSTGRES_PORT = required_env("POSTGRES_PORT")

ALLOWED_HOSTS = env_list("ALLOWED_HOSTS")
if not ALLOWED_HOSTS:
    raise ImproperlyConfigured(
        "La variable de entorno ALLOWED_HOSTS es obligatoria en producción."
    )

CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")
if not CSRF_TRUSTED_ORIGINS:
    raise ImproperlyConfigured(
        "La variable de entorno CSRF_TRUSTED_ORIGINS es obligatoria en producción."
    )

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
# La redirección de HTTP a HTTPS es responsabilidad del borde Nginx (plan
# §5.3: «redirección 80 -> 443»), que la aplica en su bloque TLS. Django
# confía en `X-Forwarded-Proto` para distinguir conexiones seguras y no
# debe forzar una segunda redirección: durante el piloto sin TLS el
# tráfico llega por HTTP y un 301 aquí rompería el flujo de la SPA.
# El healthcheck de Docker Compose sondea a Gunicorn directamente por HTTP
# plano, por lo que el endpoint público de salud queda además exento de
# cualquier redirección futura.
SECURE_REDIRECT_EXEMPT = [r"^api/health/$"]
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
# Cookies del refresh token con atributo Secure en producción: el tráfico
# solo circula por HTTPS tras el TLS de Nginx. `COOKIE_SECURE=1` en `.env`
# deja el valor auditable; el navegador rechaza cookies Secure sobre HTTP.
COOKIE_SECURE = env_bool("COOKIE_SECURE", True)
SECURE_HSTS_SECONDS = 31_536_000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": POSTGRES_DB,
        "USER": POSTGRES_USER,
        "PASSWORD": POSTGRES_PASSWORD,
        "HOST": POSTGRES_HOST,
        "PORT": POSTGRES_PORT,
    }
}

EMAIL_HOST = required_env("EMAIL_HOST")
EMAIL_PORT = int(required_env("EMAIL_PORT"))
EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "1") == "1"
EMAIL_HOST_USER = required_env("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = required_env("EMAIL_HOST_PASSWORD")
DEFAULT_FROM_EMAIL = required_env("DEFAULT_FROM_EMAIL")
