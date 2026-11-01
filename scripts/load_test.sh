#!/usr/bin/env bash
# Prueba de carga de 50 MB y concurrencia a través de Nginx (TSK-86).
#
# Levanta un stack AISLADO (proyecto «gpc_load», otros volúmenes y otro puerto;
# la base y los PDF de trabajo no se tocan), siembra cuentas con una contraseña
# aleatoria que no se guarda, ejecuta scripts/load/load_test.py y lo apaga.
#
# Uso:
#   ./scripts/load_test.sh                # prueba completa (~5 min)
#   ./scripts/load_test.sh --timeouts     # añade el corte de 120 s (~+2 min)
#
# Variables: LOAD_WEB_PORT (18080), LOAD_USERS (50), LOAD_UPLOADS (5),
# LOAD_KEEP=1 conserva el stack al terminar, LOAD_OUTPUT=ruta.json guarda el informe.
set -euo pipefail

cd "$(dirname "$0")/.."

PROJECT="gpc_load"
export LOAD_WEB_PORT="${LOAD_WEB_PORT:-18080}"
export LOAD_COMPOSE="docker compose -p ${PROJECT} -f docker-compose.yml -f docker-compose.load.yml"
export LOAD_BASE_URL="http://localhost:${LOAD_WEB_PORT}"
export LOAD_PASSWORD
LOAD_PASSWORD="$(openssl rand -hex 16)"
# El driver invoca «docker compose» con el mismo proyecto y los mismos archivos.
export LOAD_COMPOSE_ARGS="-p ${PROJECT} -f docker-compose.yml -f docker-compose.load.yml"

compose() { docker compose -p "${PROJECT}" -f docker-compose.yml -f docker-compose.load.yml "$@"; }

if [ ! -f .env ]; then
    echo "ERROR: falta .env (cópialo de .env.example)." >&2
    exit 2
fi

cleanup() {
    if [ "${LOAD_KEEP:-0}" = "1" ]; then
        echo "Stack conservado (docker compose -p ${PROJECT} ... down -v para borrarlo)."
    else
        compose down -v --remove-orphans >/dev/null 2>&1 || true
    fi
}
trap cleanup EXIT

echo "Levantando el stack aislado (${PROJECT}, puerto ${LOAD_WEB_PORT})…"
compose up -d --build db backend web

echo "Esperando a que el backend esté sano…"
for _ in $(seq 1 60); do
    state="$(docker inspect -f '{{.State.Health.Status}}' "${PROJECT}-backend-1" 2>/dev/null || true)"
    [ "${state}" = "healthy" ] && break
    sleep 3
done
[ "${state:-}" = "healthy" ] || { echo "ERROR: el backend no quedó sano." >&2; compose logs --tail 40 backend >&2; exit 2; }

echo "Sembrando cuentas…"
compose exec -T -e LOAD_PASSWORD -e LOAD_USERS="${LOAD_USERS:-50}" backend \
    python manage.py shell < scripts/load/seed_users.py | grep SEED_OK

python3 scripts/load/load_test.py \
    --uploads "${LOAD_UPLOADS:-5}" \
    "$@"
