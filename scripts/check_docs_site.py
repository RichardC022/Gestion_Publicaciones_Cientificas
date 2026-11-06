#!/usr/bin/env python3
"""Comprueba el portal de documentación (docs-site/) antes y después de renderizarlo.

Quarto no falla ante un enlace roto ni ante una página olvidada en la navegación; este
script sí. Estático y rápido: no levanta nada.

Uso:
    python3 scripts/check_docs_site.py            # fuente: antes de `quarto render`
    python3 scripts/check_docs_site.py --built    # sitio: después de `quarto render`
    python3 scripts/check_docs_site.py --built --site-dir RUTA   # otro directorio de salida

Fuente (docs-site/):
  1. Toda página .qmd tiene cabecera YAML con `title` y aparece en la navegación de
     `_quarto.yml`; todo archivo que la navegación nombra existe.
  2. Los enlaces relativos entre páginas y a archivos del repositorio resuelven.
     Los archivos que genera el CI (docs-site/diagrams/out/) se omiten.
  3. Cada bloque ``` está cerrado y cada diagrama Mermaid declara un tipo conocido.

Sitio (docs-site/_site/):
  4. Todo enlace y recurso interno (`href`, `src`) de cada página HTML apunta a un
     archivo que existe.
  5. Están los archivos generados que el sitio promete: la referencia estática de la
     API, el visor BPMN y los diagramas C4.

Código de salida 1 si algo falla.
"""

from __future__ import annotations

import argparse
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlparse

import yaml

ROOT = Path(__file__).resolve().parents[1]
SITE_SRC = ROOT / "docs-site"
SITE_OUT = SITE_SRC / "_site"

# Archivos que no están en el repositorio: los produce el CI al publicar.
GENERATED_IN_SOURCE = ("diagrams/out/",)

# Lo que el sitio construido debe contener sí o sí.
REQUIRED_IN_BUILT = (
    "index.html",
    "search.json",
    "api/index.html",
    "api/openapi.yaml",
    "api/swagger-ui-bundle.js",
    "api/swagger-ui.css",
    "api/swagger-initializer.js",
    "diagrams/bpmn.html",
    "diagrams/proceso-editorial.bpmn",
    "diagrams/vendor/bpmn-navigated-viewer.production.min.js",
    "diagrams/vendor/diagram-js.css",
    "diagrams/vendor/bpmn-js.css",
    "diagrams/workspace.dsl",
    "diagrams/out/c1-contexto.svg",
    "diagrams/out/c2-contenedores.svg",
    "diagrams/out/c3-backend.svg",
    "diagrams/out/c4-codigo-envio.svg",
)

MERMAID_TYPES = re.compile(
    r"^(flowchart|graph|sequenceDiagram|stateDiagram-v2|stateDiagram|erDiagram|classDiagram|gantt|journey|C4Context)\b"
)
MD_LINK = re.compile(r"\]\(([^)\s]+?)(?:\s+\"[^\"]*\")?\)")
FENCED = re.compile(r"^```.*?^```", re.S | re.M)

problems: list[str] = []


def fail(message: str) -> None:
    problems.append(message)


def navigation_pages(config: dict) -> set[str]:
    """Todas las rutas `.qmd` que la navegación de `_quarto.yml` nombra."""
    found: set[str] = set()

    def walk(node) -> None:
        if isinstance(node, str):
            if node.endswith(".qmd"):
                found.add(node)
        elif isinstance(node, dict):
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(config.get("website", {}))
    return found


def check_source() -> None:
    config = yaml.safe_load((SITE_SRC / "_quarto.yml").read_text(encoding="utf-8"))
    in_nav = navigation_pages(config)
    pages = sorted(SITE_SRC.rglob("*.qmd"))

    for rel in sorted(in_nav):
        if not (SITE_SRC / rel).exists():
            fail(f"la navegación apunta a un archivo que no existe: {rel}")

    for page in pages:
        rel = page.relative_to(SITE_SRC).as_posix()
        if rel not in in_nav:
            fail(f"{rel}: la página no está en la navegación de _quarto.yml")

        text = page.read_text(encoding="utf-8")
        header = re.match(r"^---\n(.*?)\n---\n", text, re.S)
        if not header:
            fail(f"{rel}: falta la cabecera YAML")
            continue
        try:
            front = yaml.safe_load(header.group(1)) or {}
        except yaml.YAMLError as error:
            fail(f"{rel}: cabecera YAML inválida ({error})")
            continue
        if not front.get("title"):
            fail(f"{rel}: la cabecera no tiene `title`")

        body = text[header.end() :]
        if len(re.findall(r"^```", body, re.M)) % 2:
            fail(f"{rel}: hay un bloque ``` sin cerrar")

        for index, block in enumerate(re.findall(r"^```\{mermaid\}\n(.*?)^```", body, re.S | re.M), 1):
            first = block.strip().splitlines()[0].strip() if block.strip() else ""
            if not MERMAID_TYPES.match(first):
                fail(f"{rel}: el diagrama Mermaid #{index} no declara un tipo conocido ('{first}')")

        prose = FENCED.sub("", body)
        for target in MD_LINK.findall(prose):
            if re.match(r"^[a-z][a-z0-9+.-]*:", target) or target.startswith(("#", "/")):
                continue
            path = unquote(target.split("#", 1)[0].split("?", 1)[0])
            if not path:
                continue
            resolved = (page.parent / path).resolve()
            relative = resolved.relative_to(SITE_SRC).as_posix() if SITE_SRC in resolved.parents else ""
            if any(relative.startswith(prefix) for prefix in GENERATED_IN_SOURCE):
                continue
            if not resolved.exists():
                fail(f"{rel}: enlace roto -> {target}")

    print(f"fuente: {len(pages)} páginas, {len(in_nav)} en la navegación")


class LinkCollector(HTMLParser):
    """Reúne los `href` y `src` de una página HTML."""

    def __init__(self) -> None:
        super().__init__()
        self.targets: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for name, value in attrs:
            if name in ("href", "src") and value:
                self.targets.append(value)


def check_built(site_out: Path) -> None:
    if not site_out.is_dir():
        fail(f"no existe {site_out}: ejecute `quarto render docs-site` antes")
        return

    for rel in REQUIRED_IN_BUILT:
        if not (site_out / rel).is_file() or (site_out / rel).stat().st_size == 0:
            fail(f"falta en el sitio construido (o está vacío): {rel}")

    pages = sorted(site_out.rglob("*.html"))
    checked = 0
    for page in pages:
        rel = page.relative_to(site_out).as_posix()
        collector = LinkCollector()
        collector.feed(page.read_text(encoding="utf-8", errors="replace"))
        for target in collector.targets:
            parsed = urlparse(target)
            if parsed.scheme or parsed.netloc or target.startswith(("#", "data:", "mailto:", "javascript:")):
                continue
            path = unquote(parsed.path)
            if not path:
                continue
            resolved = (site_out / path.lstrip("/")) if path.startswith("/") else (page.parent / path)
            resolved = resolved.resolve()
            if resolved.is_dir():
                resolved = resolved / "index.html"
            checked += 1
            if not resolved.exists():
                fail(f"{rel}: enlace o recurso roto -> {target}")

    print(f"sitio: {len(pages)} páginas HTML, {checked} enlaces internos comprobados")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--built", action="store_true", help="comprueba docs-site/_site en lugar de la fuente")
    parser.add_argument("--site-dir", type=Path, default=SITE_OUT, help="directorio del sitio construido")
    args = parser.parse_args()

    if args.built:
        check_built(args.site_dir.resolve())
    else:
        check_source()

    if problems:
        print(f"\n{len(problems)} problema(s):")
        for problem in problems:
            print(f"  ✗ {problem}")
        return 1
    print("Todo en orden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
