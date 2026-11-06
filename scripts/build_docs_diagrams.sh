#!/usr/bin/env bash
# Prepara los diagramas del portal de documentación (docs-site/diagrams).
#
# Uso:
#   ./scripts/build_docs_diagrams.sh            # todo
#   ./scripts/build_docs_diagrams.sh bpmn       # solo el visor BPMN
#   ./scripts/build_docs_diagrams.sh c4         # solo el modelo C4 (Structurizr + PlantUML)
#
# Pasos:
#   bpmn  Copia el visor bpmn-js (versión fija) a docs-site/diagrams/vendor/ para que
#         bpmn.html muestre proceso-editorial.bpmn sin depender de una CDN.
#   c4    Exporta workspace.dsl (Structurizr) a PlantUML con la imagen oficial
#         structurizr/cli y renderiza a SVG, junto con c4-codigo-envio.puml, en
#         docs-site/diagrams/out/.
#
# Requisitos: bpmn → node y npm. c4 → docker, graphviz y PlantUML. PlantUML se ejecuta como
# `java -jar` si PLANTUML_JAR apunta a un plantuml.jar (lo que hace el CI, con una versión
# reciente); si no, se usa el comando `plantuml` del sistema (apt-get install plantuml graphviz),
# cuya versión en Ubuntu 24.04 es demasiado antigua para el .puml que exporta Structurizr.
# Lo generado (vendor/ y out/) no se versiona: lo produce el CI en cada publicación.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIAGRAMS="$ROOT/docs-site/diagrams"
BPMN_JS_VERSION="${BPMN_JS_VERSION:-18.31.1}"
# Versión fija: desde 2026-03 la etiqueta 'latest' de structurizr/cli es un aviso de
# obsolescencia que termina con éxito sin exportar nada (el build fallaba más tarde con
# "Structurizr no produjo la vista ..."). 2025.11.09 es la última versión funcional.
STRUCTURIZR_IMAGE="${STRUCTURIZR_IMAGE:-structurizr/cli:2025.11.09}"
# Ruta a plantuml.jar. Vacío = usar el comando `plantuml` instalado en el sistema.
PLANTUML_JAR="${PLANTUML_JAR:-}"
VIEWS=(c1-contexto c2-contenedores c3-backend)

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

need() {
  command -v "$1" >/dev/null 2>&1 || fail "falta el comando '$1'. $2"
}

# Ejecuta PlantUML con el .jar indicado (modo headless: no hay pantalla en el CI) o con el
# comando del sistema.
plantuml_run() {
  if [[ -n "$PLANTUML_JAR" ]]; then
    java -Djava.awt.headless=true -jar "$PLANTUML_JAR" "$@"
  else
    plantuml "$@"
  fi
}

build_bpmn() {
  need npm "Instale Node.js (https://nodejs.org)."
  local work dist
  work="$(mktemp -d)"
  # shellcheck disable=SC2064
  trap "rm -rf '$work'" RETURN

  echo "→ bpmn-js ${BPMN_JS_VERSION}"
  npm install --prefix "$work" --no-audit --no-fund --silent "bpmn-js@${BPMN_JS_VERSION}"
  dist="$work/node_modules/bpmn-js"

  mkdir -p "$DIAGRAMS/vendor"
  cp "$dist/dist/bpmn-navigated-viewer.production.min.js" "$DIAGRAMS/vendor/"
  cp "$dist/dist/assets/diagram-js.css" "$dist/dist/assets/bpmn-js.css" "$DIAGRAMS/vendor/"
  # La licencia de bpmn-js obliga a conservar su aviso junto al código redistribuido.
  cp "$dist/LICENSE" "$DIAGRAMS/vendor/LICENSE-bpmn-js.txt"

  for file in bpmn-navigated-viewer.production.min.js diagram-js.css bpmn-js.css; do
    [[ -s "$DIAGRAMS/vendor/$file" ]] || fail "no se generó vendor/$file"
  done
  echo "  vendor/ listo"
}

build_c4() {
  need docker "Instale Docker (el modelo C4 se exporta con la imagen structurizr/cli)."
  if [[ -n "$PLANTUML_JAR" ]]; then
    need java "Instale un JRE (PlantUML se ejecuta con PLANTUML_JAR)."
    [[ -s "$PLANTUML_JAR" ]] || fail "PLANTUML_JAR='${PLANTUML_JAR}' no existe o está vacío."
  else
    need plantuml "Instale PlantUML (apt-get install plantuml graphviz) o defina PLANTUML_JAR."
  fi

  local out="$DIAGRAMS/out" src="$DIAGRAMS/out/src"
  rm -rf "$out"
  mkdir -p "$src"

  echo "→ Structurizr (${STRUCTURIZR_IMAGE}): workspace.dsl → PlantUML"
  # --user evita que los archivos exportados queden como propiedad de root.
  docker run --rm --user "$(id -u):$(id -g)" \
    -v "$DIAGRAMS:/usr/local/structurizr" \
    "$STRUCTURIZR_IMAGE" export -workspace workspace.dsl -format plantuml -output out/src

  cp "$DIAGRAMS/c4-codigo-envio.puml" "$src/"

  echo "→ PlantUML: .puml → SVG"
  plantuml_run -tsvg -charset UTF-8 "$src"/*.puml

  # Structurizr nombra los archivos structurizr-<clave>.puml y, junto a cada uno, una
  # leyenda structurizr-<clave>-key.puml. Se toma el nombre exacto (un patrón con comodines
  # también coincidiría con la leyenda) y se normaliza a <clave>.svg.
  local key found
  for key in "${VIEWS[@]}"; do
    found="$src/structurizr-${key}.svg"
    [[ -s "$found" ]] || fail "Structurizr no produjo la vista '${key}'. Revise workspace.dsl."
    cp "$found" "$out/${key}.svg"
  done
  cp "$src/c4-codigo-envio.svg" "$out/c4-codigo-envio.svg" \
    || fail "PlantUML no produjo c4-codigo-envio.svg. Revise c4-codigo-envio.puml."

  for file in "${VIEWS[@]/%/.svg}" c4-codigo-envio.svg; do
    [[ -s "$out/$file" ]] || fail "falta out/$file"
  done
  echo "  out/ listo: ${VIEWS[*]} c4-codigo-envio"
}

case "${1:-all}" in
  bpmn) build_bpmn ;;
  c4) build_c4 ;;
  all)
    build_bpmn
    build_c4
    ;;
  *) fail "paso desconocido '${1}'. Use: bpmn | c4 | all" ;;
esac
