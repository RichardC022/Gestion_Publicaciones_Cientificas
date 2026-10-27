#!/usr/bin/env bash
# Prueba de humo del aislamiento del volumen de archivos (TSK-58, plan 4.6).
#
# Levanta Nginx con la configuración REAL del proyecto (nginx/conf.d/default.conf),
# el volumen montado en solo lectura y un backend de mentira que solo responde con
# `X-Accel-Redirect`, y comprueba:
#
#   1. Desde fuera, `/_protected/`, `/_catalog/` y `/media/` no entregan archivos
#      (ni con rutas codificadas, dobles barras ni `..`) ni listan directorios.
#   2. Control positivo: cuando el backend autoriza, Nginx SÍ entrega el PDF desde
#      el árbol privado o el catálogo, con sus cabeceras de seguridad. Así los
#      rechazos anteriores no se deben a que el archivo no exista.
#   3. Una redirección interna hacia `/media/` también se deniega.
#   4. El volumen es de solo lectura para Nginx y, en docker-compose.yml, el
#      backend es el único servicio que lo monta con escritura.
#
# No usa la base de datos ni el stack en ejecución: es efímero y se limpia solo.
# Requiere docker, curl y python3. Uso:  scripts/smoke_media_isolation.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SUFFIX="$$"
NETWORK="gpc-smoke-net-${SUFFIX}"
VOLUME="gpc-smoke-media-${SUFFIX}"
NGINX="gpc-smoke-nginx-${SUFFIX}"
STUB="gpc-smoke-backend-${SUFFIX}"
NGINX_IMAGE="${NGINX_IMAGE:-nginx:1.27-alpine}"
PYTHON_IMAGE="${PYTHON_IMAGE:-python:3.12-slim-bookworm}"
WORK="$(mktemp -d)"
FAILURES=0
CREATED_ENV=0

cleanup() {
  if [[ "${CREATED_ENV}" == "1" ]]; then rm -f "${ROOT}/.env"; fi
  docker rm -f "${NGINX}" "${STUB}" >/dev/null 2>&1 || true
  docker network rm "${NETWORK}" >/dev/null 2>&1 || true
  docker volume rm "${VOLUME}" >/dev/null 2>&1 || true
  rm -rf "${WORK}"
}
trap cleanup EXIT

pass() { printf '  \033[32mOK\033[0m   %s\n' "$1"; }
fail() { printf '  \033[31mFALLA\033[0m %s\n' "$1"; FAILURES=$((FAILURES + 1)); }

# check <descripción> <estado esperado> <ruta> [curl extra...]
# El cuerpo nunca puede contener un PDF cuando se espera un rechazo.
check_denied() {
  local description="$1" expected="$2" path="$3"
  shift 3
  local status
  status="$(curl -s -o "${WORK}/body" -w '%{http_code}' --path-as-is "$@" "${BASE}${path}")"
  if [[ "${status}" == "${expected}" ]] && ! grep -q '%PDF' "${WORK}/body"; then
    pass "${description} → ${status}"
  else
    fail "${description}: esperaba ${expected} sin PDF y obtuve ${status}"
  fi
}

# `docker compose config` exige el archivo de entorno; en CI no existe.
if [[ ! -f "${ROOT}/.env" && -f "${ROOT}/.env.example" ]]; then
  cp "${ROOT}/.env.example" "${ROOT}/.env"
  CREATED_ENV=1
fi

echo "Preparando red, volumen y archivos de prueba…"
docker network create "${NETWORK}" >/dev/null
docker volume create "${VOLUME}" >/dev/null

# El «backend» es el único que escribe en el volumen (sin :ro).
docker run --rm -v "${VOLUME}:/data/media" "${NGINX_IMAGE}" sh -c '
  set -e
  mkdir -p /data/media/private/manuscripts/m1/v0001 /data/media/public/catalog/m1 /data/media/tmp/uploads
  printf "%%PDF-1.4 SMOKE-ORIGINAL"  > /data/media/private/manuscripts/m1/v0001/original.pdf
  printf "%%PDF-1.4 SMOKE-SANITIZED" > /data/media/private/manuscripts/m1/v0001/sanitized.pdf
  printf "%%PDF-1.4 SMOKE-CATALOG"   > /data/media/public/catalog/m1/v1.pdf
  printf "%%PDF-1.4 SMOKE-ROOT"      > /data/media/root-secret.pdf
'

cat > "${WORK}/stub.py" <<'PY'
"""Backend de mentira: solo responde con X-Accel-Redirect, como el real tras autorizar."""
import http.server

ROUTES = {
    "/api/ok-private": "/_protected/manuscripts/m1/v0001/sanitized.pdf",
    "/api/ok-catalog": "/_catalog/m1/v1.pdf",
    "/api/escape-media": "/media/root-secret.pdf",
}


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        target = ROUTES.get(self.path)
        if target is None:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("X-Accel-Redirect", target)
        self.send_header("Content-Type", "application/json")
        self.end_headers()

    def log_message(self, *args):
        pass


http.server.ThreadingHTTPServer(("0.0.0.0", 8000), Handler).serve_forever()
PY

mkdir -p "${WORK}/html"
printf '<!doctype html><title>SPA</title>' > "${WORK}/html/index.html"

docker run -d --name "${STUB}" --network "${NETWORK}" --network-alias backend \
  -v "${WORK}/stub.py:/stub.py:ro" "${PYTHON_IMAGE}" python /stub.py >/dev/null

# Nginx no debe empezar a proxyar antes de que el backend de prueba escuche.
for _ in $(seq 1 60); do
  if docker exec "${STUB}" python -c \
    "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/api/ok-private')" \
    >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done

# Nginx con la configuración real y el volumen de solo lectura, como en `web`.
docker run -d --name "${NGINX}" --network "${NETWORK}" -p 127.0.0.1::80 \
  -v "${ROOT}/nginx/conf.d/default.conf:/etc/nginx/conf.d/default.conf:ro" \
  -v "${VOLUME}:/data/media:ro" \
  -v "${WORK}/html:/usr/share/nginx/html:ro" \
  "${NGINX_IMAGE}" >/dev/null

PORT="$(docker port "${NGINX}" 80/tcp | head -n1 | sed 's/.*://')"
BASE="http://127.0.0.1:${PORT}"

for _ in $(seq 1 40); do
  if [[ "$(curl -s -o /dev/null -w '%{http_code}' "${BASE}/")" == "200" ]]; then break; fi
  sleep 0.5
done
if [[ "$(curl -s -o /dev/null -w '%{http_code}' "${BASE}/")" != "200" ]]; then
  docker logs "${NGINX}" >&2 || true
  echo "Nginx no arrancó con la configuración del proyecto." >&2
  exit 2
fi

echo
echo "1. Acceso directo desde fuera (no debe entregar archivos)"
check_denied "/_protected/ sanitizado"          404 "/_protected/manuscripts/m1/v0001/sanitized.pdf"
check_denied "/_protected/ original"            404 "/_protected/manuscripts/m1/v0001/original.pdf"
check_denied "/_catalog/ copia pública"         404 "/_catalog/m1/v1.pdf"
check_denied "/media/ archivo"                  403 "/media/root-secret.pdf"
check_denied "/media/ archivo privado"          403 "/media/private/manuscripts/m1/v0001/original.pdf"
check_denied "/media/ listado de directorio"    403 "/media/"
check_denied "/_protected/ listado"             404 "/_protected/"
check_denied "/_catalog/ listado"               404 "/_catalog/"
check_denied "doble barra //_protected/"        404 "//_protected/manuscripts/m1/v0001/sanitized.pdf"
check_denied "ruta codificada %5Fprotected"     404 "/%5Fprotected/manuscripts/m1/v0001/sanitized.pdf"
check_denied "retroceso /media/../_protected/"  404 "/media/../_protected/manuscripts/m1/v0001/sanitized.pdf"
check_denied "retroceso desde /static/"         404 "/static/../_protected/manuscripts/m1/v0001/sanitized.pdf"

# La SPA no debe poder servir el volumen: `/` solo entrega el index de Angular.
check_denied "ruta del volumen en la raíz"      200 "/data/media/root-secret.pdf"
if grep -q 'SPA' "${WORK}/body"; then
  pass "la raíz responde con el index de la SPA, no con el archivo"
else
  fail "la raíz no devolvió el index de la SPA para /data/media/..."
fi
check_denied "listado de /static/"              404 "/static/"

echo
echo "2. Control positivo: el backend autoriza y Nginx entrega"
fetch_authorized() {
  local description="$1" path="$2" marker="$3" cache="$4"
  local status
  status="$(curl -s -D "${WORK}/headers" -o "${WORK}/body" -w '%{http_code}' "${BASE}${path}")"
  if [[ "${status}" == "200" ]] && grep -q "${marker}" "${WORK}/body"; then
    pass "${description} → 200 con el contenido esperado"
  else
    fail "${description}: esperaba 200 con ${marker} y obtuve ${status}"
    return
  fi
  grep -qi "^cache-control: ${cache}" "${WORK}/headers" \
    && pass "${description}: Cache-Control ${cache}" \
    || fail "${description}: falta Cache-Control ${cache}"
  grep -qi '^x-content-type-options: nosniff' "${WORK}/headers" \
    && pass "${description}: X-Content-Type-Options nosniff" \
    || fail "${description}: falta X-Content-Type-Options"
}
fetch_authorized "PDF sanitizado del árbol privado" "/api/ok-private" "SMOKE-SANITIZED" "private, no-store"
fetch_authorized "copia pública del catálogo"       "/api/ok-catalog" "SMOKE-CATALOG"   "public, max-age=300"

echo
echo "3. Una redirección interna al árbol /media/ también se deniega"
check_denied "X-Accel-Redirect a /media/" 403 "/api/escape-media"

echo
echo "4. El backend es el único que escribe en el volumen"
if docker exec "${NGINX}" sh -c 'touch /data/media/escritura-de-nginx 2>/dev/null'; then
  fail "Nginx pudo escribir en el volumen: no está montado en solo lectura"
else
  pass "Nginx no puede escribir en el volumen (solo lectura)"
fi

COMPOSE_JSON="$(cd "${ROOT}" && docker compose config --format json 2>/dev/null || true)"
if [[ -n "${COMPOSE_JSON}" ]]; then
  if ! python3 - "${COMPOSE_JSON}" <<'PY'
import json, sys

services = json.loads(sys.argv[1])["services"]
writers, readers = [], []
for name, service in services.items():
    for volume in service.get("volumes", []):
        if volume.get("source") == "media_data":
            (readers if volume.get("read_only") else writers).append(name)
print(f"      con escritura: {writers or '—'} · solo lectura: {readers or '—'}")
sys.exit(0 if writers == ["backend"] and "web" in readers else 1)
PY
  then
    fail "docker-compose.yml: el backend debe ser el único servicio que monta media_data con escritura y web debe montarlo :ro"
  else
    pass "docker-compose.yml: solo el backend monta media_data con escritura; web lo monta :ro"
  fi
else
  fail "no se pudo leer docker-compose.yml con «docker compose config»"
fi

echo
if [[ "${FAILURES}" -gt 0 ]]; then
  printf '\033[31m%d comprobación(es) fallaron.\033[0m\n' "${FAILURES}"
  echo "--- registro de Nginx ---" >&2
  docker logs --tail 20 "${NGINX}" >&2 || true
  echo "--- registro del backend de prueba ---" >&2
  docker logs --tail 20 "${STUB}" >&2 || true
  exit 1
fi
printf '\033[32mAislamiento del volumen verificado.\033[0m\n'
