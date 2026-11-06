#!/usr/bin/env bash
# Prepara la referencia estática de la API (Swagger UI) del portal de documentación.
#
# Uso (con el entorno de Python del backend ya instalado):
#   ./scripts/build_docs_api.sh
#
# Hace dos cosas en docs-site/api/:
#   1. Exporta el schema OpenAPI del código con `manage.py spectacular`, validándolo y
#      fallando ante cualquier advertencia (openapi.yaml). No necesita base de datos.
#   2. Copia los archivos de Swagger UI que ya trae drf-spectacular-sidecar: así la copia
#      estática usa exactamente la misma versión que /api/v1/docs/ y no depende de una CDN.
#
# index.html y swagger-initializer.js sí se versionan; lo demás lo genera este script.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_DIR="$ROOT/docs-site/api"
PYTHON="${PYTHON:-python}"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

command -v "$PYTHON" >/dev/null 2>&1 || fail "no se encuentra '$PYTHON'. Active el entorno del backend o defina PYTHON."

mkdir -p "$API_DIR"

echo "→ Schema OpenAPI"
(
  cd "$ROOT/backend"
  export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-config.settings.development}"
  export API_DOCS_ENABLED=1
  # El schema se genera sin conectarse a la base: los valores solo satisfacen la configuración.
  export POSTGRES_DB="${POSTGRES_DB:-gpc_docs}" POSTGRES_USER="${POSTGRES_USER:-gpc_docs}"
  export POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-gpc_docs}" POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
  export POSTGRES_PORT="${POSTGRES_PORT:-5432}"
  "$PYTHON" manage.py spectacular --file "$API_DIR/openapi.yaml" --validate --fail-on-warn
)
[[ -s "$API_DIR/openapi.yaml" ]] || fail "no se generó openapi.yaml"

echo "→ Swagger UI (drf-spectacular-sidecar)"
DIST="$("$PYTHON" -c 'import pathlib, drf_spectacular_sidecar as s; print(pathlib.Path(s.__file__).parent / "static" / "drf_spectacular_sidecar" / "swagger-ui-dist")')"
[[ -d "$DIST" ]] || fail "drf-spectacular-sidecar no incluye swagger-ui-dist en $DIST"

for file in swagger-ui-bundle.js swagger-ui.css favicon-32x32.png LICENSE; do
  [[ -s "$DIST/$file" ]] || fail "falta $file en $DIST"
  cp "$DIST/$file" "$API_DIR/"
done
# La licencia de Swagger UI se conserva junto al código redistribuido.
mv "$API_DIR/LICENSE" "$API_DIR/LICENSE-swagger-ui.txt"

echo "  docs-site/api/ listo: openapi.yaml + Swagger UI"
