#!/usr/bin/env bash
set -euo pipefail

if (($# > 0)); then
  printf 'ERROR: este comando no admite argumentos adicionales.\n' >&2
  exit 1
fi

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${PROJECT_DIR}"

COMPOSE="${COMPOSE:-docker compose}"

printf 'Verificando hashes de PDFs y cadena de auditoría...\n'
# shellcheck disable=SC2086
${COMPOSE} run --rm --no-deps -T backend \
  python manage.py verify_integrity
