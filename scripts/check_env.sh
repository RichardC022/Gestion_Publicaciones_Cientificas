#!/usr/bin/env bash
set -euo pipefail

required_vars=(
  DJANGO_SETTINGS_MODULE
  DJANGO_SECRET_KEY
  ALLOWED_HOSTS
  CSRF_TRUSTED_ORIGINS
  POSTGRES_DB
  POSTGRES_USER
  POSTGRES_PASSWORD
  POSTGRES_HOST
  POSTGRES_PORT
  APP_DB_USER
  APP_DB_PASSWORD
  JWT_ACCESS_MINUTES
  JWT_REFRESH_DAYS
  SESSION_IDLE_MINUTES
  MAX_PDF_SIZE_MB
  NGINX_CLIENT_MAX_BODY_SIZE
  MEDIA_ROOT
  TZ
  EMAIL_HOST
  EMAIL_PORT
  EMAIL_USE_TLS
  EMAIL_HOST_USER
  EMAIL_HOST_PASSWORD
  DEFAULT_FROM_EMAIL
)

secret_vars=(
  DJANGO_SECRET_KEY
  POSTGRES_PASSWORD
  APP_DB_PASSWORD
  EMAIL_HOST_PASSWORD
)

# En desarrollo local (DEBUG=1) se omite la validación estricta.
if [[ "${DEBUG:-0}" == "1" ]]; then
  exit 0
fi

missing_vars=()
for var in "${required_vars[@]}"; do
  if [[ -z "${!var:-}" ]]; then
    missing_vars+=("${var}")
  fi
done

if ((${#missing_vars[@]} > 0)); then
  printf 'ERROR: faltan variables obligatorias: %s\n' \
    "${missing_vars[*]}" >&2
  exit 1
fi

placeholder_vars=()
for var in "${secret_vars[@]}"; do
  if [[ "${!var}" == "change-me" ]]; then
    placeholder_vars+=("${var}")
  fi
done

if ((${#placeholder_vars[@]} > 0)); then
  printf 'ERROR: estas variables contienen el valor de ejemplo "change-me": %s\n' \
    "${placeholder_vars[*]}" >&2
  exit 1
fi
