"""Base Django settings shared by every environment."""

from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent


def env_bool(name: str, default: bool = False) -> bool:
    """Read a boolean value from the environment."""
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: tuple[str, ...] = ()) -> list[str]:
    """Read a comma-separated list from the environment."""
    value = os.environ.get(name)
    if value is None:
        return list(default)
    return [item.strip() for item in value.split(",") if item.strip()]


SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-development-key-change-me",
)

DEBUG = env_bool("DEBUG", False)

# Django Admin (D-31): fuera de la URL salvo que el entorno lo pida. Producción lo
# deja siempre apagado (`/admin/` responde 404); solo desarrollo lo enciende.
ADMIN_ENABLED = False

# Documentación interactiva de la API (`/api/v1/docs/` y `/api/v1/schema/`). Apagada por
# defecto: en cada despliegue se decide con `API_DOCS_ENABLED=1`; desarrollo la enciende.
API_DOCS_ENABLED = env_bool("API_DOCS_ENABLED", False)

ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", ("localhost", "127.0.0.1", "testserver"))
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    # Documentación OpenAPI (drf-spectacular); el sidecar sirve Swagger UI desde
    # /static/, sin CDN, para cumplir la CSP `script-src 'self'` de Nginx.
    "drf_spectacular",
    "drf_spectacular_sidecar",
    "apps.users",
    "apps.publications",
    "apps.reviews",
    "apps.audit",
    "apps.notifications",
]

MIDDLEWARE = [
    "config.middleware.RequestIdMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

# Usuario institucional del dominio (plan §1.3).
AUTH_USER_MODEL = "users.User"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "gpc"),
        "USER": os.environ.get("POSTGRES_USER", "gpc_app"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", ""),
        "HOST": os.environ.get("POSTGRES_HOST", "db"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# ---------------------------------------------------------------------------
# JWT, sesión y cookies del refresh token (plan §2.1 y §6.1).
#
# Invariantes del sistema:
#   - El refresh token viaja SIEMPRE en cookie `HttpOnly` con
#     `SameSite=Strict`; JavaScript nunca puede leerlo.
#   - El access token vive solo en memoria del cliente y NUNCA se persiste
#     en `localStorage` ni en cookies.
# `COOKIE_SECURE` controla el atributo `Secure` de las cookies: obligatorio
# (valor 1) en producción, donde el tráfico solo circula por HTTPS tras el
# TLS de Nginx. La autenticación de TSK-19 consume esta configuración.
# ---------------------------------------------------------------------------
JWT_ACCESS_MINUTES = int(os.environ.get("JWT_ACCESS_MINUTES", "15"))
JWT_REFRESH_DAYS = int(os.environ.get("JWT_REFRESH_DAYS", "7"))
SESSION_IDLE_MINUTES = int(os.environ.get("SESSION_IDLE_MINUTES", "30"))

COOKIE_SECURE = env_bool("COOKIE_SECURE", False)
REFRESH_COOKIE_HTTPONLY = True
REFRESH_COOKIE_SAMESITE = "Strict"

# Cookie que transporta el refresh token (TSK-19). El path se limita a los
# endpoints de autenticación para que el navegador nunca la envíe al resto
# de la API.
REFRESH_COOKIE_NAME = "gpc_refresh"
REFRESH_COOKIE_PATH = "/api/v1/auth/"

# Política de firma de los JWT emitidos con SimpleJWT (plan §6.1). El access
# token vive solo en memoria del cliente; el refresh token es de uso único:
# la rotación y la revocación se gobiernan desde la tabla
# ``users_refresh_token``, no desde la librería.
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=JWT_ACCESS_MINUTES),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=JWT_REFRESH_DAYS),
    # La rotación/revocación de TSK-19 usa una tabla propia del dominio.
    "ROTATE_REFRESH_TOKENS": False,
    "BLACKLIST_AFTER_ROTATION": False,
    "UPDATE_LAST_LOGIN": False,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": SECRET_KEY,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}

LANGUAGE_CODE = "es"
TIME_ZONE = os.environ.get("TZ", "America/Guayaquil")
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = Path(os.environ.get("STATIC_ROOT", BASE_DIR / "staticfiles"))

MEDIA_ROOT = Path(os.environ.get("MEDIA_ROOT", "/data/media"))

# Carga de PDF (plan sección 4.2 paso 3): Nginx acepta cuerpos de hasta
# 60 MB y los deriva a disco; Django también envía el archivo a disco en
# lugar de mantenerlo completo en memoria. El límite real de 50 MB por
# PDF lo aplica el dominio (PdfService, TSK-33/34) leyendo
# MAX_PDF_SIZE_BYTES; el margen de 60 MB absorbe el multipart y las
# cabeceras de la petición.
FILE_UPLOAD_MAX_MEMORY_SIZE = 2_621_440  # 2.5 MB: por encima se envía a disco.
DATA_UPLOAD_MAX_MEMORY_SIZE = 62_914_560  # 60 MB: techo del cuerpo completo.
MAX_PDF_SIZE_MB = int(os.environ.get("MAX_PDF_SIZE_MB", "50"))
MAX_PDF_SIZE_BYTES = MAX_PDF_SIZE_MB * 1024 * 1024

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    # Autenticación institucional JWT (TSK-19): toda denegación responde con
    # el mismo error genérico AUTH_INVALID (sin revelar la causa exacta).
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.users.authentication.InstitutionalJWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [],
    # Contrato JSON universal: {success, message, data, errors, meta}.
    "DEFAULT_RENDERER_CLASSES": [
        "config.renderers.EnvelopeJSONRenderer",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_PAGINATION_CLASS": "config.pagination.StandardPagination",
    "EXCEPTION_HANDLER": "config.exceptions.exception_handler",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "API de Gestión de Publicaciones Científicas",
    "DESCRIPTION": (
        "API REST del sistema de gestión editorial de la UNL: manuscritos, revisión por "
        "pares con doble ciego, veredictos, catálogo público y auditoría.\n\n"
        "## Contrato de respuesta\n"
        "Toda respuesta JSON usa el mismo sobre: "
        "`{success, message, data, errors, meta}`. En un éxito, `data` lleva la carga del "
        "endpoint y `errors` está vacío; en una lista, `meta.pagination` trae `count`, `next` "
        "y `previous`. En un error, `success` es `false`, `data` es `null` y `errors` lista "
        "entradas `{code, message, field, details}`. `meta.request_id` identifica la "
        "solicitud (cabecera `X-Request-ID`).\n\n"
        "## Autenticación\n"
        "`POST /auth/login/` entrega un token de acceso; envíelo como "
        "`Authorization: Bearer <token>`. La renovación usa una cookie `HttpOnly`.\n\n"
        "## Errores\n"
        "Cualquier endpoint puede responder `500` (`SERVER_ERROR`) sin detalles internos. "
        "Una ruta inexistente bajo `/api/` responde `404` con el mismo sobre."
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SCHEMA_PATH_PREFIX": r"/api/v1",
    "SWAGGER_UI_DIST": "SIDECAR",
    "SWAGGER_UI_FAVICON_HREF": "SIDECAR",
    "COMPONENT_SPLIT_REQUEST": True,
    # Nombres estables para los enums: sin esto drf-spectacular los llama `Status39bEnum`.
    "ENUM_NAME_OVERRIDES": {
        "ManuscriptStatusEnum": "apps.publications.models.Manuscript.Status",
        "AssignmentStatusEnum": "apps.reviews.models.Assignment.Status",
        "EvaluationStatusEnum": "apps.reviews.models.Evaluation.Status",
        "IncidentStatusEnum": "apps.reviews.models.IncidentReport.Status",
        "RoleEnum": "apps.users.models.Role.Code",
    },
    "POSTPROCESSING_HOOKS": [
        "drf_spectacular.hooks.postprocess_schema_enums",
        "config.openapi.wrap_in_envelope",
    ],
    "SWAGGER_UI_SETTINGS": {
        "deepLinking": True,
        "persistAuthorization": False,
        "displayOperationId": False,
        "tagsSorter": "alpha",
    },
    "TAGS": [
        {"name": "Sistema", "description": "Estado del servicio."},
        {"name": "Autenticación", "description": "Inicio, renovación y cierre de sesión."},
        {"name": "Tablero", "description": "Resumen por rol del usuario autenticado."},
        {"name": "Autor", "description": "Manuscritos propios, versiones y correcciones."},
        {"name": "Catálogo", "description": "Artículos publicados (público, sin sesión)."},
        {"name": "Editor", "description": "Bandeja, asignación de revisores, veredictos e incidentes."},
        {"name": "Revisor", "description": "Asignaciones y evaluaciones (doble ciego)."},
        {"name": "Administración", "description": "Auditoría y autorización de correcciones."},
        {"name": "Notificaciones", "description": "Avisos del usuario autenticado."},
    ],
}

# Correlación de logs con el request_id que asigna el middleware.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "request_id": {
            "()": "config.middleware.RequestIDLogFilter",
        },
    },
    "formatters": {
        "standard": {
            "format": "%(levelname)s %(asctime)s [request_id=%(request_id)s] %(name)s %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "filters": ["request_id"],
            "formatter": "standard",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
}
