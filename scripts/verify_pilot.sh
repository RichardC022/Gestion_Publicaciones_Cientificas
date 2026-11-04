#!/usr/bin/env bash
# Verificación de restauración, integridad y superficie expuesta (TSK-87).
#
# Levanta un stack AISLADO (proyecto «gpc_verify», otros volúmenes y puertos; la
# base y los PDF de trabajo no se tocan), siembra datos por la API real y ejecuta
# scripts/verify/verify_pilot.py: respaldo → desastre → restore.sh → huella
# idéntica → verify_integrity, y pruebas de puertos, ubicaciones internas, TLS y
# cabeceras. Se apaga al terminar (VERIFY_KEEP=1 lo conserva).
#
# Uso:  ./scripts/verify_pilot.sh
# Variables: VERIFY_WEB_PORT (19080, HTTP), VERIFY_TLS_PORT (19443, HTTPS),
# VERIFY_OUTPUT=ruta.json guarda el informe.
set -euo pipefail

cd "$(dirname "$0")/.."

export VERIFY_PROJECT="gpc_verify"
export LOAD_WEB_PORT="${VERIFY_WEB_PORT:-19080}"
export LOAD_TLS_PORT="${VERIFY_TLS_PORT:-19443}"
export VERIFY_HTTP_URL="http://localhost:${LOAD_WEB_PORT}"
export VERIFY_BASE_URL="https://localhost:${LOAD_TLS_PORT}"
export LOAD_COMPOSE_ARGS="-p ${VERIFY_PROJECT} -f docker-compose.yml -f docker-compose.load.yml"
export LOAD_PASSWORD
LOAD_PASSWORD="$(openssl rand -hex 16)"

compose() { docker compose ${LOAD_COMPOSE_ARGS} "$@"; }

if [ ! -f .env ]; then
    echo "ERROR: falta .env (cópialo de .env.example)." >&2
    exit 2
fi

cleanup() {
    if [ "${VERIFY_KEEP:-0}" = "1" ]; then
        echo "Stack conservado (docker compose ${LOAD_COMPOSE_ARGS} down -v para borrarlo)."
    else
        compose down -v --remove-orphans >/dev/null 2>&1 || true
    fi
}
trap cleanup EXIT

# Nginx exige certificado: si no hay uno, se crea uno autofirmado.
./scripts/make_dev_cert.sh >/dev/null

echo "Levantando el stack aislado (${VERIFY_PROJECT}, HTTPS en el puerto ${LOAD_TLS_PORT})…"
compose up -d --build db backend web

echo "Esperando a que el backend esté sano…"
for _ in $(seq 1 60); do
    state="$(docker inspect -f '{{.State.Health.Status}}' "${VERIFY_PROJECT}-backend-1" 2>/dev/null || true)"
    [ "${state}" = "healthy" ] && break
    sleep 3
done
[ "${state:-}" = "healthy" ] || { echo "ERROR: el backend no quedó sano." >&2; compose logs --tail 40 backend >&2; exit 2; }

echo "Sembrando cuentas…"
compose exec -T -e LOAD_PASSWORD -e LOAD_USERS=5 backend \
    python manage.py shell < scripts/load/seed_users.py | grep SEED_OK

python3 scripts/verify/verify_pilot.py "$@"
