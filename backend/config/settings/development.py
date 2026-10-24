"""Development settings for local execution and tests."""

from .base import *  # noqa: F401,F403
from .base import env_list

DEBUG = True

ALLOWED_HOSTS = env_list(
    "ALLOWED_HOSTS",
    ("localhost", "127.0.0.1", "testserver"),
)

CSRF_TRUSTED_ORIGINS = env_list(
    "CSRF_TRUSTED_ORIGINS",
    ("http://localhost", "http://127.0.0.1"),
)

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
