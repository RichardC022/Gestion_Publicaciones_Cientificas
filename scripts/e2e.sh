#!/usr/bin/env bash
# Pruebas E2E de los flujos críticos con Playwright (TSK-91).
#
# Levanta un stack AISLADO (proyecto «gpc_e2e», otros volúmenes y puertos; la base y
# los PDF de trabajo no se tocan), siembra cinco cuentas con una contraseña aleatoria
# que no se guarda y ejecuta Playwright contra https://localhost:<puerto> (Nginx real).
# Playwright corre en la imagen oficial de Microsoft (trae Chromium y sus librerías),
# así que el host no necesita navegadores ni dependencias del sistema. Al terminar,
# el stack se borra: las pruebas no dejan datos residuales (E2E_KEEP=1 lo conserva).
#
# Uso:
#   ./scripts/e2e.sh                       # todos los flujos
#   ./scripts/e2e.sh -g "fuga"             # solo los que coinciden (argumentos de playwright test)
#
# Variables: E2E_WEB_PORT (20080, HTTP→HTTPS), E2E_TLS_PORT (20443), E2E_KEEP=1 (conserva
# el stack), E2E_REUSE=1 (usa el stack ya levantado con E2E_KEEP=1: salta la construcción;
# vuelve a sembrar con una contraseña nueva y NO lo apaga).
set -euo pipefail

cd "$(dirname "$0")/.."

PROJECT="gpc_e2e"
export LOAD_WEB_PORT="${E2E_WEB_PORT:-20080}"
export LOAD_TLS_PORT="${E2E_TLS_PORT:-20443}"
export E2E_BASE_URL="https://localhost:${LOAD_TLS_PORT}"
export E2E_PASSWORD
E2E_PASSWORD="$(openssl rand -hex 16)"

compose() { docker compose -p "${PROJECT}" -f docker-compose.yml -f docker-compose.load.yml "$@"; }

if [ ! -f .env ]; then
    echo "ERROR: falta .env (cópialo de .env.example)." >&2
    exit 2
fi
if [ ! -d frontend/node_modules/@playwright/test ]; then
    echo "ERROR: faltan las dependencias del frontend (cd frontend && npm ci)." >&2
    exit 2
fi

# La imagen debe ser de la MISMA versión que @playwright/test, o no encuentra el navegador.
PW_VERSION="$(node -p "require('./frontend/node_modules/@playwright/test/package.json').version")"
IMAGE="mcr.microsoft.com/playwright:v${PW_VERSION}-noble"

cleanup() {
    if [ "${E2E_REUSE:-0}" = "1" ]; then
        :
    elif [ "${E2E_KEEP:-0}" = "1" ]; then
        echo "Stack conservado (docker compose -p ${PROJECT} -f docker-compose.yml -f docker-compose.load.yml down -v para borrarlo)."
    else
        compose down -v --remove-orphans >/dev/null 2>&1 || true
    fi
}
trap cleanup EXIT

if [ "${E2E_REUSE:-0}" != "1" ]; then
    ./scripts/make_dev_cert.sh >/dev/null

    echo "Levantando el stack aislado (${PROJECT}, HTTPS en el puerto ${LOAD_TLS_PORT})…"
    compose up -d --build db backend web

    echo "Esperando a que el backend esté sano…"
    for _ in $(seq 1 60); do
        state="$(docker inspect -f '{{.State.Health.Status}}' "${PROJECT}-backend-1" 2>/dev/null || true)"
        [ "${state}" = "healthy" ] && break
        sleep 3
    done
    [ "${state:-}" = "healthy" ] || { echo "ERROR: el backend no quedó sano." >&2; compose logs --tail 40 backend >&2; exit 2; }
fi

echo "Sembrando cuentas…"
compose exec -T -e E2E_PASSWORD backend python manage.py shell < scripts/e2e/seed_e2e.py | grep SEED_OK

echo "Ejecutando Playwright (${IMAGE})…"
status=0
docker run --rm --network host --ipc=host \
    --user "$(id -u):$(id -g)" -e HOME=/tmp \
    -e E2E_BASE_URL -e E2E_PASSWORD \
    -v "$PWD/frontend:/work" -w /work \
    "${IMAGE}" npx playwright test "$@" || status=$?

if [ "${status}" -ne 0 ]; then
    echo "Las pruebas fallaron. Capturas y trazas: frontend/test-results/ (npx playwright show-trace <trace.zip>)." >&2
fi
exit "${status}"
