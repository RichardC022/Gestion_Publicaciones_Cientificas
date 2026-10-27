#!/usr/bin/env bash
set -euo pipefail

umask 0077

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${PROJECT_DIR}"

if [[ ! -f .env ]]; then
  printf 'ERROR: no existe %s/.env\n' "${PROJECT_DIR}" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1091
. ./.env
set +a

: "${POSTGRES_DB:?La variable POSTGRES_DB es obligatoria}"
: "${POSTGRES_USER:?La variable POSTGRES_USER es obligatoria}"

BACKUP_ROOT="${BACKUP_ROOT:-/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
COMPOSE="${COMPOSE:-docker compose}"

if [[ "${BACKUP_ROOT}" != /* ]]; then
  printf 'ERROR: BACKUP_ROOT debe ser una ruta absoluta.\n' >&2
  exit 1
fi

case "${BACKUP_ROOT}" in
  "${PROJECT_DIR}"|"${PROJECT_DIR}"/*)
    printf 'ERROR: BACKUP_ROOT no debe estar dentro del repositorio.\n' >&2
    exit 1
    ;;
  /data/media|/data/media/*)
    printf 'ERROR: BACKUP_ROOT no debe estar dentro de /data/media.\n' >&2
    exit 1
    ;;
esac

if ! [[ "${RETENTION_DAYS}" =~ ^[1-9][0-9]*$ ]]; then
  printf 'ERROR: RETENTION_DAYS debe ser un entero mayor que 0.\n' >&2
  exit 1
fi

if ! command -v sha256sum >/dev/null 2>&1; then
  printf 'ERROR: sha256sum no está disponible en el host.\n' >&2
  exit 1
fi

install --directory --mode 0700 "${BACKUP_ROOT}"

STAMP="$(date +%Y%m%dT%H%M%S)"
DESTINATION="${BACKUP_ROOT}/${STAMP}"

if [[ -e "${DESTINATION}" ]]; then
  suffix=1
  while [[ -e "${BACKUP_ROOT}/${STAMP}-${suffix}" ]]; do
    suffix=$((suffix + 1))
  done
  DESTINATION="${BACKUP_ROOT}/${STAMP}-${suffix}"
fi

install --directory --mode 0700 "${DESTINATION}"

backup_completed=0
cleanup_incomplete_backup() {
  if (( backup_completed == 0 )) && [[ -d "${DESTINATION}" ]]; then
    rm -rf -- "${DESTINATION}"
  fi
}
trap cleanup_incomplete_backup EXIT

printf 'Generando respaldo en %s\n' "${DESTINATION}"

# shellcheck disable=SC2086
${COMPOSE} exec -T db pg_dump \
  --username="${POSTGRES_USER}" \
  --dbname="${POSTGRES_DB}" \
  --format=custom \
  --no-owner \
  --no-privileges \
  > "${DESTINATION}/database.dump"

# shellcheck disable=SC2086
${COMPOSE} exec -T backend tar \
  --create \
  --gzip \
  --file=- \
  --directory=/data/media \
  . \
  > "${DESTINATION}/media.tar.gz"

(
  cd "${DESTINATION}"
  sha256sum database.dump media.tar.gz > SHA256SUMS
)

chmod 0600 \
  "${DESTINATION}/database.dump" \
  "${DESTINATION}/media.tar.gz" \
  "${DESTINATION}/SHA256SUMS"

backup_completed=1
trap - EXIT

# Conserva siempre el respaldo más reciente y solo elimina respaldos completos
# que superen la retención configurada.
backup_dirs=()
while IFS= read -r -d '' backup_dir; do
  if [[ -f "${backup_dir}/SHA256SUMS" ]] \
    && [[ -f "${backup_dir}/database.dump" ]] \
    && [[ -f "${backup_dir}/media.tar.gz" ]]; then
    backup_dirs+=("${backup_dir}")
  fi
done < <(find "${BACKUP_ROOT}" -mindepth 1 -maxdepth 1 -type d -print0)

newest_dir=""
newest_mtime=0
for backup_dir in "${backup_dirs[@]}"; do
  backup_mtime="$(stat --format=%Y "${backup_dir}")"
  if (( backup_mtime >= newest_mtime )); then
    newest_mtime="${backup_mtime}"
    newest_dir="${backup_dir}"
  fi
done

now_epoch="$(date +%s)"
retention_seconds=$((RETENTION_DAYS * 86400))
for backup_dir in "${backup_dirs[@]}"; do
  backup_mtime="$(stat --format=%Y "${backup_dir}")"
  if [[ "${backup_dir}" == "${DESTINATION}" ]] \
    || (( backup_mtime == newest_mtime )); then
    continue
  fi

  backup_age=$((now_epoch - backup_mtime))
  if (( backup_age > retention_seconds )); then
    rm -rf -- "${backup_dir}"
    printf 'Respaldo eliminado por retención: %s\n' "${backup_dir}"
  fi
done

printf 'Respaldo completado: %s\n' "${DESTINATION}"
