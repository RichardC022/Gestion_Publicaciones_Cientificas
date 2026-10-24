#!/usr/bin/env bash
set -euo pipefail

umask 0077

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${PROJECT_DIR}"

usage() {
  printf 'Uso: %s [--yes] <directorio-de-respaldo>\n' "$0"
  printf '\n'
  printf 'Opciones:\n'
  printf '  --yes    No pedir confirmación antes de restaurar.\n'
  printf '  -h, --help  Mostrar esta ayuda.\n'
}

assume_yes=0
backup_dir=""

while (($# > 0)); do
  case "$1" in
    --yes)
      assume_yes=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      if [[ -n "${backup_dir}" ]]; then
        printf 'ERROR: solo se admite un directorio de respaldo.\n' >&2
        usage >&2
        exit 1
      fi
      backup_dir="$1"
      shift
      ;;
  esac
done

if [[ -z "${backup_dir}" ]]; then
  printf 'ERROR: falta el directorio del respaldo.\n' >&2
  usage >&2
  exit 1
fi

if [[ ! -d "${backup_dir}" ]]; then
  printf 'ERROR: el directorio de respaldo no existe: %s\n' "${backup_dir}" >&2
  exit 1
fi

backup_dir="$(cd "${backup_dir}" && pwd)"

for required_file in database.dump media.tar.gz SHA256SUMS; do
  if [[ ! -f "${backup_dir}/${required_file}" ]]; then
    printf 'ERROR: falta %s en %s\n' "${required_file}" "${backup_dir}" >&2
    exit 1
  fi
done

checksum_count="$(wc --lines < "${backup_dir}/SHA256SUMS")"
if [[ "${checksum_count}" != "2" ]]; then
  printf 'ERROR: SHA256SUMS debe contener exactamente database.dump y media.tar.gz.\n' >&2
  exit 1
fi

(
  cd "${backup_dir}"
  sha256sum --check --strict SHA256SUMS
)

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

COMPOSE="${COMPOSE:-docker compose}"

if (( assume_yes == 0 )); then
  printf 'Esto reemplazará la base de datos y el volumen media_data.\n' >&2
  printf 'Respaldo seleccionado: %s\n' "${backup_dir}" >&2
  read -r -p 'Escribe SI para continuar: ' confirmation
  if [[ "${confirmation}" != "SI" ]]; then
    printf 'Restauración cancelada.\n' >&2
    exit 1
  fi
fi

printf 'Deteniendo web y backend...\n'
${COMPOSE} up -d db
${COMPOSE} stop web backend

printf 'Restaurando PostgreSQL...\n'
${COMPOSE} exec -T db pg_restore \
  --username="${POSTGRES_USER}" \
  --dbname="${POSTGRES_DB}" \
  --clean \
  --if-exists \
  --exit-on-error \
  --no-owner \
  --no-privileges \
  < "${backup_dir}/database.dump"

printf 'Restaurando volumen media_data...\n'
${COMPOSE} run --rm --no-deps -T backend sh -c '
  find /data/media -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +
  tar --extract --gzip --file=- --directory=/data/media
' < "${backup_dir}/media.tar.gz"

${COMPOSE} run --rm --no-deps -T backend /app/scripts/init_media.sh

printf 'Verificando integridad...\n'
"${PROJECT_DIR}/scripts/verify_integrity.sh"

printf 'Levantando servicios...\n'
${COMPOSE} up -d db backend web

printf 'Ejecutando prueba de humo...\n'
${COMPOSE} exec -T backend python manage.py check
${COMPOSE} exec -T backend sh -c '
  test -d /data/media/private/drafts &&
  test -d /data/media/private/manuscripts &&
  test -d /data/media/public/catalog &&
  test -d /data/media/tmp/uploads
'

printf 'Restauración completada desde: %s\n' "${backup_dir}"
