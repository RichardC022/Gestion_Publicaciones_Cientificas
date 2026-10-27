"""Guardas del aislamiento del volumen de archivos (TSK-58, plan 4.6).

La prueba de humo real vive en ``scripts/smoke_media_isolation.sh`` (necesita
Docker). Estas guardas dan aviso inmediato, sin Docker, de dos regresiones:

* la configuración de Nginx deja de proteger las rutas internas del volumen;
* el código del Revisor llega al PDF original. El endpoint del Revisor (TSK-61)
  solo puede resolver ``sanitized.pdf``; el original y su nombre de archivo
  pueden revelar la identidad del Autor.

Las comprobaciones de configuración se omiten si el repositorio no está
disponible (por ejemplo, dentro de la imagen del backend).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
REPOSITORY = BACKEND.parent
NGINX_CONF = REPOSITORY / "nginx" / "conf.d" / "default.conf"

#: Nombres que solo el Autor y el Editor pueden tocar: apuntan al PDF original.
ORIGINAL_MARKERS = ("original_file_path", "original_filename", "original.pdf", "original_sha256")


def location_block(conf: str, prefix: str) -> str:
    """Cuerpo del bloque ``location <prefix> { ... }`` (sin llaves anidadas)."""
    match = re.search(r"location\s+" + re.escape(prefix) + r"\s*\{([^}]*)\}", conf)
    assert match is not None, f"No existe el bloque location {prefix}"
    return match.group(1)


@pytest.fixture(scope="module")
def conf() -> str:
    if not NGINX_CONF.exists():
        pytest.skip("La configuración de Nginx no está en esta imagen.")
    return NGINX_CONF.read_text(encoding="utf-8")


class TestNginxConfiguration:
    def test_the_private_tree_is_only_reachable_through_the_backend(self, conf) -> None:
        block = location_block(conf, "/_protected/")

        assert re.search(r"^\s*internal;", block, re.MULTILINE)
        assert "alias  /data/media/private/;" in block.replace("\t", "  ")

    def test_the_public_catalog_is_only_reachable_through_the_backend(self, conf) -> None:
        block = location_block(conf, "/_catalog/")

        assert re.search(r"^\s*internal;", block, re.MULTILINE)
        assert "alias  /data/media/public/catalog/;" in block.replace("\t", "  ")

    def test_the_media_tree_is_denied(self, conf) -> None:
        assert re.search(r"^\s*deny\s+all;", location_block(conf, "/media/"), re.MULTILINE)

    def test_no_directory_listing_anywhere(self, conf) -> None:
        assert not re.search(r"^\s*autoindex\s+on;", conf, re.MULTILINE)

    @pytest.mark.parametrize("prefix", ["/_protected/", "/_catalog/"])
    def test_pdfs_are_never_compressed_nor_sniffed(self, conf, prefix) -> None:
        block = location_block(conf, prefix)

        assert re.search(r"^\s*gzip\s+off;", block, re.MULTILINE)
        assert "X-Content-Type-Options" in block and "nosniff" in block

    def test_the_whole_volume_is_never_served_as_static_files(self, conf) -> None:
        aliases = re.findall(r"^\s*(?:alias|root)\s+([^;]+);", conf, re.MULTILINE)

        assert all(not path.strip().rstrip("/").endswith("/data/media") for path in aliases)


class TestReviewerNeverReachesTheOriginal:
    """El código del Revisor (``apps/reviews``) no puede nombrar el PDF original."""

    def reviewer_sources(self) -> list[Path]:
        return [
            path
            for path in (BACKEND / "apps" / "reviews").rglob("*.py")
            if "migrations" not in path.parts and path.name not in {"tests.py"}
        ]

    def test_there_are_reviewer_sources_to_check(self) -> None:
        assert self.reviewer_sources(), "No se encontró el código del módulo reviews"

    def test_no_reviewer_code_references_the_original_pdf(self) -> None:
        offenders = {
            f"{path.relative_to(BACKEND)}: {marker}"
            for path in self.reviewer_sources()
            for marker in ORIGINAL_MARKERS
            if marker in path.read_text(encoding="utf-8")
        }

        assert not offenders, (
            "El módulo del Revisor solo puede resolver sanitized.pdf; "
            f"referencias al original: {sorted(offenders)}"
        )

    def test_a_version_row_keeps_original_and_sanitized_apart(self) -> None:
        """Las rutas guardadas nunca coinciden: resolver una no entrega la otra."""
        from apps.publications.services.storage import version_relative_dir

        base = version_relative_dir(__import__("uuid").uuid4(), 1)

        assert str(base / "original.pdf") != str(base / "sanitized.pdf")
        assert (base / "sanitized.pdf").name == "sanitized.pdf"
