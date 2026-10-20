"""Django settings for automated tests and CI.

This module reuses the project settings but swaps MySQL for an in-memory SQLite
database so the suite runs without external services. It is safe to commit
because it contains no secrets and is only imported with ``settings_test``.
"""

import os

# Default secrets must exist before importing the base settings, which read them
# eagerly from the environment. Tests never use real credentials.
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")
os.environ.setdefault("DEBUG", "False")

from config.settings import *

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]
