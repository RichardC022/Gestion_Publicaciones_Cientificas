#!/usr/bin/env python3
"""Comprueba que el runbook (docs/RUNBOOK.md) y las decisiones Q1–Q5 siguen siendo ciertos (TSK-88).

Es estático y rápido: no levanta contenedores. Solo necesita ``docker compose config``
(con ``.env``; en CI se copia de ``.env.example``). Termina con código 1 si algo falla.

1. Decisiones Q1–Q5: el límite de 50/60 MB coincide en .env, Nginx, Django y Angular;
   el compose solo publica 80/443; las ubicaciones internas existen y el backend usa
   ``X-Accel-Redirect``; el respaldo diario conserva 30 días.
2. Higiene del runbook: sin secretos ni instrucciones de MySQL, cada script y cada
   comando de ``manage.py`` que cita existe, cada variable de entorno es real y los
   enlaces internos apuntan a un título que existe.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNBOOK = ROOT / "docs" / "RUNBOOK.md"
failures = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global failures
    failures += 0 if ok else 1
    print(f"  [{'OK' if ok else 'FALLA'}] {name}" + (f" — {detail}" if detail else ""))


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def contains(relative: str, pattern: str) -> bool:
    return re.search(pattern, read(relative), re.M) is not None


# --------------------------------------------------------------------------
# 1. Decisiones Q1–Q5
# --------------------------------------------------------------------------
def decisions() -> None:
    compose = subprocess.run(
        ["docker", "compose", "config", "--format", "json"],
        capture_output=True, text=True, cwd=ROOT, check=False,
    )
    services = json.loads(compose.stdout)["services"] if compose.returncode == 0 else {}
    nginx = "nginx/conf.d/default.conf"

    print("Q1 — PDF en volumen local, original y sanitizado separados")
    init = read("scripts/init_media.sh")
    check("init_media.sh crea private/drafts, private/manuscripts, public/catalog y tmp/uploads",
          all(part in init for part in ("private/drafts", "private/manuscripts", "public/catalog", "tmp/uploads")))
    mounts = {name: [(v.get("source"), v.get("read_only", False)) for v in svc.get("volumes", [])]
              for name, svc in services.items()}
    check("solo backend monta media_data con escritura; web lo monta en solo lectura",
          ("media_data", False) in mounts.get("backend", []) and ("media_data", True) in mounts.get("web", [])
          and ("media_data", False) not in mounts.get("web", []))

    print("Q2 — 50 MB por PDF, 60 MB en el proxy")
    check(".env.example: MAX_PDF_SIZE_MB=50 y NGINX_CLIENT_MAX_BODY_SIZE=60m",
          contains(".env.example", r"^MAX_PDF_SIZE_MB=50$") and contains(".env.example", r"^NGINX_CLIENT_MAX_BODY_SIZE=60m$"))
    check("Nginx: client_max_body_size 60m", contains(nginx, r"client_max_body_size\s+60m;"))
    check("Django: techo del cuerpo de 60 MiB y 50 MB por PDF por defecto",
          contains("backend/config/settings/base.py", r"DATA_UPLOAD_MAX_MEMORY_SIZE = 62_914_560")
          and contains("backend/config/settings/base.py", r'"MAX_PDF_SIZE_MB", "50"'))
    check("Angular: MAX_PDF_BYTES de 50 MiB",
          contains("frontend/src/app/features/author/pdf-uploader/pdf-file.validation.ts",
                   r"MAX_PDF_BYTES = 50 \* 1024 \* 1024"))
    check("tiempos de 120 s en Nginx y Gunicorn",
          all(contains(nginx, rf"{d}\s+120s;") for d in ("client_body_timeout", "proxy_read_timeout", "proxy_send_timeout"))
          and "--timeout 120" in " ".join(services.get("backend", {}).get("command", [])))

    print("Q3 — un servidor con Docker Compose; solo web publica 80/443")
    published = {n: sorted(p["published"] for p in s.get("ports", [])) for n, s in services.items()}
    check("el compose tiene exactamente db, backend y web", sorted(services) == ["backend", "db", "web"], ", ".join(sorted(services)))
    check("solo web publica puertos, y son 80 y 443",
          published.get("web") == ["443", "80"] and not published.get("db") and not published.get("backend"), str(published))
    check("Nginx sirve TLS 1.2/1.3 y redirige 80→443",
          contains(nginx, r"ssl_protocols\s+TLSv1\.2 TLSv1\.3;") and contains(nginx, r"return\s+301\s+https://"))

    print("Q4 — X-Accel-Redirect con ubicaciones internas separadas")
    conf = read(nginx)
    check("/_protected/ y /_catalog/ son internal",
          all(re.search(rf"location {loc} \{{\s+internal;", conf) for loc in ("/_protected/", "/_catalog/")))
    check("/media/ es deny all", re.search(r"location /media/ \{\s+deny all;", conf) is not None)
    check("el backend entrega con X-Accel-Redirect", "X-Accel-Redirect" in read("backend/apps/publications/services/downloads.py"))

    print("Q5 — respaldo diario, 30 días, prueba mensual")
    cron = read("scripts/cron/gpc.cron")
    check("cron: backup.sh a las 02:15 con flock",
          re.search(r"^15 2 \* \* \* .*flock .*scripts/backup\.sh", cron, re.M) is not None)
    check("retención de 30 días por defecto y en .env.example",
          contains("scripts/backup.sh", r'RETENTION_DAYS="\$\{RETENTION_DAYS:-30\}"')
          and contains(".env.example", r"^RETENTION_DAYS=30$"))
    check("restore.sh recrea el rol de la aplicación (apply_db_privileges)",
          "apply_db_privileges" in read("scripts/restore.sh"))
    check("hay procedimiento de prueba mensual", "Prueba mensual" in read("scripts/BACKUP.md"))
    if not re.search(r"openssl|gpg|\bage\b", read("scripts/backup.sh")):
        print("      AVISO Q5: backup.sh no cifra ni copia fuera del servidor; "
              "queda como paso manual del runbook §8.3 (deuda D-30)")


# --------------------------------------------------------------------------
# 2. Higiene del runbook
# --------------------------------------------------------------------------
def slug(title: str) -> str:
    """Ancla de GitHub: minúsculas, sin signos (conserva letras con tilde y guiones)."""
    title = re.sub(r"[`*]", "", title.strip().lower())
    return re.sub(r"\s", "-", re.sub(r"[^\w\s-]", "", title))


def hygiene() -> None:
    print("Runbook — contenido")
    if not RUNBOOK.exists():
        check("docs/RUNBOOK.md existe", False)
        return
    text = RUNBOOK.read_text(encoding="utf-8")
    check("no menciona MySQL", "mysql" not in text.lower())

    secret_patterns = [
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
        r"(?:PASSWORD|SECRET_KEY|TOKEN)\s*=\s*(?!change-me|<)[^\s<`]{6,}",
        r"\bBearer [A-Za-z0-9._-]{20,}",
        r"\bAKIA[0-9A-Z]{16}\b",
    ]
    hits = [p for p in secret_patterns if re.search(p, text)]
    check("no contiene secretos", not hits, ", ".join(hits))

    scripts = sorted(set(re.findall(r"(?:\./)?(scripts/[\w./-]+\.(?:sh|py|cron|logrotate))", text)))
    missing = [s for s in scripts if not (ROOT / s).exists()]
    check(f"los {len(scripts)} archivos de scripts/ que cita existen", not missing, ", ".join(missing))
    not_exec = [s for s in scripts if s.endswith((".sh", ".py")) and (ROOT / s).exists()
                and not (ROOT / s).stat().st_mode & 0o111]
    check("los scripts que manda ejecutar son ejecutables", not not_exec, ", ".join(not_exec))

    builtin = {"check", "createsuperuser", "changepassword", "shell", "migrate", "showmigrations", "collectstatic"}
    available = {p.stem for p in (ROOT / "backend" / "apps").glob("*/management/commands/*.py") if p.stem != "__init__"}
    used = set(re.findall(r"manage\.py (\w+)", text))
    unknown = sorted(used - builtin - available)
    check(f"los {len(used)} comandos de manage.py que cita existen", not unknown, ", ".join(unknown))

    known = set(re.findall(r"^([A-Z][A-Z0-9_]+)=", read(".env.example"), re.M))
    # Variables de UNA sola ejecución (`docker compose exec -e …`): a propósito NO viven en `.env`.
    known |= {"ALLOW_DEV_USERS"}
    assigned = set(re.findall(r"\b([A-Z][A-Z0-9_]+)=", text))
    check("las variables de entorno que cita existen en .env.example", not (assigned - known),
          ", ".join(sorted(assigned - known)))

    headings = {slug(m) for m in re.findall(r"^#{1,6} (.+)$", text, re.M)}
    broken = sorted(a for a in re.findall(r"\]\(#([^)]+)\)", text) if a not in headings)
    check("los enlaces internos apuntan a un título", not broken, ", ".join(broken))

    check("documenta las cinco decisiones Q1–Q5", all(f"**Q{n}**" in text for n in range(1, 6)))
    check("documenta límites 50/60 MB, volumen, PostgreSQL y X-Accel-Redirect",
          all(term in text for term in ("50 MB", "60 MB", "media_data", "PostgreSQL", "X-Accel-Redirect")))
    check("cubre despliegue, TLS, respaldos, restauración, cron, incidentes, credenciales y aceptación",
          all(re.search(rf"^## \d+\. .*{t}", text, re.M | re.I)
              for t in ("Despliegue", "TLS", "Respaldos", "Restauración", "cron", "Incidentes",
                        "Credenciales", "aceptación")))


if __name__ == "__main__":
    decisions()
    hygiene()
    print(f"\n{'Todo en orden.' if not failures else f'{failures} comprobación(es) fallaron.'}")
    sys.exit(1 if failures else 0)
