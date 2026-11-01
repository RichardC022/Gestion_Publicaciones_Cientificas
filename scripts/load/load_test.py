#!/usr/bin/env python3
"""Prueba de carga de 50 MB y concurrencia a través de Nginx (TSK-86).

Solo usa la biblioteca estándar. Se ejecuta contra el stack AISLADO que
levanta ``scripts/load_test.sh`` (nunca contra la base de trabajo) y recorre,
siempre por el puerto público de Nginx:

1. login de ``LOAD_USERS`` autores a la vez;
2. siembra de artículos aceptados por la API real (autor, editor, revisor);
3. catálogo con ``LOAD_USERS`` personas concurrentes (SC-11: p95 < 2 s);
4. descargas concurrentes: PDF del catálogo (``X-Accel-Redirect``) y copia
   sanitizada del revisor;
5. cargas concurrentes de PDF de ~50 MB;
6. bordes de Nginx: PDF de 50 MB exactos, PDF que Django rechaza (51 MB),
   cuerpo de 61 MB que Nginx rechaza sin llegar al backend, clientes lentos
   que no deben ocupar workers y, con ``--timeouts``, el corte a los 120 s;
7. memoria de los contenedores frente a sus límites, durante toda la corrida.

Código de salida: 0 si todo se cumple, 1 si falla algún criterio.
"""

from __future__ import annotations

import argparse
import http.client
import json
import os
import re
import socket
import ssl
import statistics
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from urllib.parse import urlparse

MIB = 1024 * 1024
PDF_LIMIT = 50 * MIB  # límite de Django por PDF (MAX_PDF_SIZE_MB)
NGINX_BODY_LIMIT = 60 * MIB  # client_max_body_size

# Orquestación Docker: la define scripts/load_test.sh.
COMPOSE = (
    ["docker", "compose", *os.environ["LOAD_COMPOSE_ARGS"].split()]
    if os.environ.get("LOAD_COMPOSE_ARGS")
    else ["docker", "compose", "-p", "gpc_load"]
)


# --------------------------------------------------------------------------
# Resultados y cliente HTTP
# --------------------------------------------------------------------------
@dataclass
class Check:
    name: str
    ok: bool
    detail: str


@dataclass
class Report:
    checks: list[Check] = field(default_factory=list)
    timings: dict[str, list[float]] = field(default_factory=dict)
    statuses: dict[str, dict[int, int]] = field(default_factory=dict)
    memory: dict[str, dict] = field(default_factory=dict)
    nginx_temp_peak_kib: int = 0

    def check(self, name: str, ok: bool, detail: str = "") -> bool:
        self.checks.append(Check(name, bool(ok), detail))
        print(f"  [{'OK' if ok else 'FALLA'}] {name}" + (f" — {detail}" if detail else ""), flush=True)
        return bool(ok)

    def record(self, phase: str, status: int, seconds: float) -> None:
        self.timings.setdefault(phase, []).append(seconds)
        counts = self.statuses.setdefault(phase, {})
        counts[status] = counts.get(status, 0) + 1


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(pct / 100 * len(ordered)) - 1))
    return ordered[index]


class Api:
    """Cliente mínimo: una conexión nueva por llamada, como un navegador sin reutilización."""

    def __init__(self, base_url: str, report: Report, timeout: float = 300.0) -> None:
        parsed = urlparse(base_url)
        self.tls = parsed.scheme == "https"
        self.host, self.port = parsed.hostname, parsed.port or (443 if self.tls else 80)
        self.report, self.timeout = report, timeout

    def open_socket(self, timeout: float):
        """Socket crudo hacia Nginx (con TLS si la URL es https; el certificado es autofirmado)."""
        sock = socket.create_connection((self.host, self.port), timeout=timeout)
        if self.tls:
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            sock = context.wrap_socket(sock, server_hostname=self.host)
        return sock

    def connect(self):
        if not self.tls:
            return http.client.HTTPConnection(self.host, self.port, timeout=self.timeout)
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        return http.client.HTTPSConnection(self.host, self.port, timeout=self.timeout, context=context)

    def call(
        self,
        method: str,
        path: str,
        *,
        phase: str,
        token: str | None = None,
        json_body: object | None = None,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
        read_body: bool = True,
    ) -> tuple[int, dict[str, str], bytes]:
        send_headers = {"Accept": "application/json", **(headers or {})}
        if token:
            send_headers["Authorization"] = f"Bearer {token}"
        if json_body is not None:
            body = json.dumps(json_body).encode()
            send_headers["Content-Type"] = "application/json"
        started = time.monotonic()
        connection = self.connect()
        status, response_headers, payload = 0, {}, b""
        try:
            connection.request(method, path, body=body, headers=send_headers)
            response = connection.getresponse()
            status = response.status
            response_headers = {key.lower(): value for key, value in response.getheaders()}
            payload = response.read() if read_body else b""
        except (OSError, http.client.HTTPException) as error:
            payload = repr(error).encode()
        finally:
            connection.close()
        self.report.record(phase, status, time.monotonic() - started)
        if os.environ.get("LOAD_DEBUG") and (status == 0 or status >= 400) and phase != "health":
            print(f"    DEBUG {method} {path} -> {status} {payload[:300]!r}", flush=True)
        return status, response_headers, payload


def as_json(payload: bytes) -> dict:
    try:
        return json.loads(payload or b"{}")
    except ValueError:
        return {}


# --------------------------------------------------------------------------
# PDF válidos de tamaño exacto
# --------------------------------------------------------------------------
def make_pdf(total_size: int) -> bytes:
    """PDF mínimo y válido de ``total_size`` bytes exactos.

    Una página cuyo contenido es un flujo de bytes aleatorios (no comprimibles
    y distintos en cada llamada): ningún intermediario puede reducirlo ni
    reconocerlo como duplicado, y la página lo referencia para que la copia
    sanitizada (que descarta los objetos huérfanos) conserve su tamaño.
    """

    def build(stream_length: int) -> bytes:
        stream = os.urandom(stream_length)
        parts: list[bytes] = [b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n"]
        offsets: list[int] = []

        def add(content: bytes) -> None:
            offsets.append(sum(len(p) for p in parts))
            parts.append(content)

        add(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")
        add(b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n")
        add(b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R >>\nendobj\n")
        add(
            b"4 0 obj\n<< /Length %d >>\nstream\n" % stream_length
            + stream
            + b"\nendstream\nendobj\n"
        )
        xref_at = sum(len(p) for p in parts)
        table = [b"xref\n0 5\n0000000000 65535 f \n"]
        table += [b"%010d 00000 n \n" % offset for offset in offsets]
        table.append(b"trailer\n<< /Size 5 /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % xref_at)
        return b"".join(parts + table)

    overhead = len(build(0))
    pdf = build(max(0, total_size - overhead))
    # El ancho de «/Length N» cambia con N: se ajusta una vez más.
    if len(pdf) != total_size:
        pdf = build(max(0, total_size - overhead) - (len(pdf) - total_size))
    return pdf


def multipart(field_name: str, filename: str, content: bytes) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    head = (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"{field_name}\"; "
        f"filename=\"{filename}\"\r\nContent-Type: application/pdf\r\n\r\n"
    ).encode()
    tail = f"\r\n--{boundary}--\r\n".encode()
    return head + content + tail, f"multipart/form-data; boundary={boundary}"


# --------------------------------------------------------------------------
# Muestreo de contenedores
# --------------------------------------------------------------------------
UNITS = {"B": 1, "KIB": 1024, "MIB": MIB, "GIB": 1024 * MIB, "KB": 1000, "MB": 1000**2, "GB": 1000**3}


def to_bytes(text: str) -> int:
    match = re.match(r"([\d.]+)\s*([A-Za-z]+)", text.strip())
    return int(float(match.group(1)) * UNITS[match.group(2).upper()]) if match else 0


def watch_nginx_temp(seconds: int) -> subprocess.Popen:
    """Sondea DENTRO del contenedor, cada 0,1 s, el mayor cuerpo en el buffer de Nginx.

    Nginx borra el archivo temporal de `client_body_temp_path` en cuanto lo crea
    (sigue abierto, sin nombre), así que `du` no lo ve: se miden los descriptores
    abiertos de sus procesos (como el usuario `nginx`: sin CAP_SYS_PTRACE, root no
    puede leerlos). Un `docker compose exec` por muestra tarda segundos,
    más que la propia carga; por eso el bucle vive en el contenedor y emite una
    línea (bytes, o 0) por muestra.
    """
    script = (
        f"for i in $(seq 1 {seconds * 10}); do m=0; "
        'for f in /proc/[0-9]*/fd/*; do case "$(readlink "$f" 2>/dev/null)" in '
        '*/client_temp/*) n=$(stat -L -c %s "$f" 2>/dev/null || echo 0); '
        '[ "${n:-0}" -gt "$m" ] && m=$n;; esac; done; echo $m; sleep 0.1; done'
    )
    return subprocess.Popen(
        [*COMPOSE, "exec", "-T", "-u", "nginx", "web", "sh", "-c", script],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
    )


def nginx_logged_buffering() -> int:
    """Avisos de Nginx «request body is buffered to a temporary file» acumulados."""
    logs = subprocess.run([*COMPOSE, "logs", "--no-log-prefix", "web"],
                          capture_output=True, text=True, check=False).stdout
    return logs.count("client request body is buffered to a temporary file")


class Sampler(threading.Thread):
    """Lee ``docker stats`` y el buffer de cuerpos de Nginx mientras dura la prueba."""

    def __init__(self, report: Report) -> None:
        super().__init__(daemon=True)
        self.report, self.stop_event = report, threading.Event()

    def run(self) -> None:
        while not self.stop_event.is_set():
            self.sample()
            self.stop_event.wait(1.0)

    def sample(self) -> None:
        stats = subprocess.run(
            ["docker", "stats", "--no-stream", "--format", "{{.Name}}|{{.MemUsage}}"],
            capture_output=True, text=True, check=False,
        ).stdout
        project = COMPOSE[COMPOSE.index("-p") + 1] if "-p" in COMPOSE else ""
        for line in stats.splitlines():
            name, _, usage = line.partition("|")
            if project and not name.startswith(project):
                continue
            used = to_bytes(usage.split("/")[0])
            entry = self.report.memory.setdefault(name, {"peak": 0, "limit": 0})
            entry["peak"] = max(entry["peak"], used)

    def finish(self) -> None:
        self.stop_event.set()
        self.join(timeout=15)
        for name, entry in self.report.memory.items():
            inspected = subprocess.run(
                ["docker", "inspect", "-f",
                 "{{.HostConfig.Memory}}|{{.State.OOMKilled}}|{{.RestartCount}}", name],
                capture_output=True, text=True, check=False,
            ).stdout.strip().split("|")
            if len(inspected) == 3:
                entry["limit"] = int(inspected[0] or 0)
                entry["oom"] = inspected[1] == "true"
                entry["restarts"] = int(inspected[2] or 0)


# --------------------------------------------------------------------------
# Escenarios
# --------------------------------------------------------------------------
class Scenario:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.report = Report()
        self.api = Api(args.base_url, self.report)
        self.tokens: dict[str, str] = {}

    # -- utilidades -------------------------------------------------------
    def login(self, identifier: str, phase: str = "login") -> str | None:
        status, _, payload = self.api.call(
            "POST", "/api/auth/login/", phase=phase,
            json_body={"identifier": identifier, "password": self.args.password},
        )
        return as_json(payload).get("access") if status == 200 else None

    def parallel(self, count: int, function) -> list:
        """Ejecuta ``function(i)`` con ``count`` hilos liberados a la vez."""
        barrier = threading.Barrier(count)

        def run(index: int):
            barrier.wait()
            return function(index)

        with ThreadPoolExecutor(max_workers=count) as pool:
            return list(pool.map(run, range(count)))

    def health_ok(self) -> bool:
        status, _, _ = self.api.call("GET", "/api/health/", phase="health")
        return status == 200

    # -- 0. configuración efectiva ----------------------------------------
    def phase_config(self) -> None:
        print("\n0. Configuración efectiva de Nginx y Gunicorn", flush=True)
        nginx = subprocess.run([*COMPOSE, "exec", "-T", "web", "nginx", "-T"],
                               capture_output=True, text=True, check=False)
        text = nginx.stdout + nginx.stderr
        for directive in ("client_max_body_size      60m", "client_body_timeout       120s",
                          "proxy_read_timeout        120s", "proxy_send_timeout        120s",
                          "proxy_request_buffering   on",
                          "client_body_temp_path     /var/cache/nginx/client_temp"):
            self.report.check(f"Nginx: {' '.join(directive.split())}", directive in text)
        gunicorn = subprocess.run(
            [*COMPOSE, "exec", "-T", "backend", "sh", "-c", "tr '\\0' ' ' < /proc/1/cmdline"],
            capture_output=True, text=True, check=False).stdout
        self.report.check("Gunicorn: --timeout 120 y 3 workers",
                          "--timeout 120" in gunicorn and "--workers 3" in gunicorn,
                          gunicorn.strip()[-90:])

    # -- 1. login ---------------------------------------------------------
    def phase_login(self) -> None:
        users = self.args.users
        print(f"\n1. Login de {users} autores a la vez", flush=True)
        results = self.parallel(users, lambda i: self.login(f"load-author-{i:02d}"))
        for i, token in enumerate(results):
            if token:
                self.tokens[f"author-{i:02d}"] = token
        ok = sum(1 for token in results if token)
        self.report.check("los logins concurrentes responden 200", ok == users, f"{ok}/{users}")
        p95 = percentile(self.report.timings["login"], 95)
        self.report.check("p95 del login menor a 10 s", p95 < 10, f"p95={p95:.2f} s")
        for who in ("editor", "reviewer"):
            self.tokens[who] = self.login(f"load-{who}") or ""
        self.report.check("editor y revisor inician sesión",
                          bool(self.tokens["editor"] and self.tokens["reviewer"]))

    # -- 2. siembra por la API real ---------------------------------------
    def create_submitted(self, index: int, pdf: bytes, phase: str) -> tuple[str, str] | None:
        token = self.tokens[f"author-{index:02d}"]
        authors = [{
            "full_name": f"Autor{index:02d} Carga", "email": f"load-author-{index:02d}@carga.invalid",
            "affiliation": "Universidad Nacional de Loja", "is_corresponding": True,
        }]
        status, _, payload = self.api.call(
            "POST", "/api/manuscripts/", phase=phase, token=token,
            json_body={
                "title": f"Artículo de carga {index:02d} {uuid.uuid4().hex[:6]}",
                "abstract": "Resumen del estudio de carga.", "keywords": ["carga", "prueba"],
                "area": "Agronomía", "language": "es", "authors": authors,
            },
        )
        if status != 201:
            return None
        manuscript_id = as_json(payload)["id"]
        body, content_type = multipart("file", "articulo.pdf", pdf)
        status, _, _ = self.api.call(
            "POST", f"/api/manuscripts/{manuscript_id}/draft-file/", phase=phase, token=token,
            body=body, headers={"Content-Type": content_type},
        )
        if status != 201:
            return None
        status, _, payload = self.api.call(
            "POST", f"/api/manuscripts/{manuscript_id}/submit/", phase=phase, token=token,
            headers={"Idempotency-Key": uuid.uuid4().hex},
        )
        return (manuscript_id, as_json(payload)["code"]) if status == 201 else None

    def start_review(self, manuscript_id: str, code: str) -> str | None:
        """Asigna al revisor y devuelve el id de su asignación (se busca por código)."""
        me = self.api.call("GET", "/api/auth/me/", phase="setup", token=self.tokens["reviewer"])
        reviewer_id = as_json(me[2])["user"]["id"]
        status, _, _ = self.api.call(
            "POST", f"/api/editor/submissions/{manuscript_id}/start-review/", phase="setup",
            token=self.tokens["editor"], json_body={"reviewer_id": reviewer_id},
        )
        if status != 200:
            return None
        _, _, payload = self.api.call(
            "GET", "/api/reviewer/assignments/", phase="setup", token=self.tokens["reviewer"]
        )
        for row in as_json(payload).get("results", []):
            if row.get("manuscript_code") == code:
                return row.get("id")
        return None

    def accept(self, manuscript_id: str, assignment_id: str) -> bool:
        reviewer = self.tokens["reviewer"]
        base = f"/api/reviewer/assignments/{assignment_id}/evaluation/"
        evaluation = {
            "originality_score": 4, "methodology_score": 4, "clarity_score": 4,
            "relevance_score": 4, "ethics_score": 4, "recommendation": "ACCEPT",
            "comments_for_author": "Trabajo sólido.", "confidential_comments": "Sin observaciones.",
        }
        status, headers, _ = self.api.call(
            "PUT", base, phase="setup", token=reviewer, json_body=evaluation,
            headers={"If-Match": '"0"'},
        )
        if status != 200:
            return False
        status, _, _ = self.api.call(
            "POST", f"{base}submit/", phase="setup", token=reviewer,
            headers={"If-Match": headers.get("etag", '"1"')},
        )
        if status != 200:
            return False
        status, headers, _ = self.api.call(
            "GET", f"/api/editor/submissions/{manuscript_id}/", phase="setup",
            token=self.tokens["editor"],
        )
        status, _, _ = self.api.call(
            "POST", f"/api/editor/manuscripts/{manuscript_id}/verdicts/", phase="setup",
            token=self.tokens["editor"], json_body={"decision": "ACCEPTED"},
            headers={"Idempotency-Key": uuid.uuid4().hex, "If-Match": headers.get("etag", '"0"')},
        )
        return status == 201

    def phase_seed(self) -> None:
        count = self.args.articles
        print(f"\n2. Siembra de {count} artículos aceptados por la API real "
              f"(el primero de {self.args.big_mb} MB)", flush=True)
        self.big_size = self.args.big_mb * MIB
        accepted: list[str] = []
        for index in range(count):
            size = self.big_size if index == 0 else 64 * 1024
            created = self.create_submitted(index, make_pdf(size), "setup")
            assignment = self.start_review(*created) if created else None
            if created and assignment and self.accept(created[0], assignment):
                accepted.append(created[0])
        self.report.check("artículos aceptados en el catálogo", len(accepted) == count,
                          f"{len(accepted)}/{count}")
        # Un manuscrito más, con el PDF grande, que queda EN REVISIÓN para la
        # descarga sanitizada del revisor.
        created = self.create_submitted(count, make_pdf(self.big_size), "setup")
        self.review_assignment = self.start_review(*created) if created else None
        self.report.check("manuscrito grande en revisión para la descarga del revisor",
                          bool(self.review_assignment))

    # -- 3. catálogo ------------------------------------------------------
    def phase_catalog(self) -> None:
        users, rounds = self.args.users, 6
        print(f"\n3. Catálogo: {users} personas × {rounds} consultas", flush=True)
        status, _, payload = self.api.call("GET", "/api/catalog/", phase="catalog_probe")
        results = as_json(payload).get("results", [])
        self.codes = [row.get("code") for row in results if row.get("code")]
        self.report.check("el catálogo lista artículos", status == 200 and bool(self.codes),
                          f"{len(self.codes)} códigos")

        def person(i: int) -> int:
            bad = 0
            paths = ["/api/catalog/", "/api/catalog/?search=carga", "/api/catalog/?page=1&page_size=5",
                     f"/api/catalog/{self.codes[i % len(self.codes)]}/", "/api/catalog/?area=Agronom%C3%ADa",
                     "/api/catalog/?search=prueba&language=es"]
            for path in paths[:rounds]:
                status, _, _ = self.api.call("GET", path, phase="catalog")
                bad += status != 200
            return bad

        failures = sum(self.parallel(users, person))
        self.report.check("todas las consultas del catálogo responden 200", failures == 0,
                          f"{failures} fallidas de {users * rounds}")
        p95 = percentile(self.report.timings["catalog"], 95)
        self.report.check("SC-11: p95 del catálogo menor a 2 s", p95 < 2.0, f"p95={p95:.3f} s")

    # -- 4. descargas -----------------------------------------------------
    def phase_downloads(self) -> None:
        users = self.args.users
        print(f"\n4. Descargas concurrentes ({users} del catálogo + "
              f"{self.args.sanitized} sanitizadas del revisor)", flush=True)
        big_code = None
        for code in self.codes:
            _, headers, _ = self.api.call(
                "GET", f"/api/catalog/{code}/document/", phase="catalog_probe", read_body=False
            )
            if int(headers.get("content-length", "0")) >= self.big_size // 2:
                big_code = code
                break
        self.report.check("hay un PDF grande en el catálogo", big_code is not None)
        if big_code is None:
            return

        def catalog_download(i: int) -> tuple[int, int]:
            status, headers, payload = self.api.call(
                "GET", f"/api/catalog/{big_code}/document/", phase="download_catalog"
            )
            return status, len(payload)

        def reviewer_download(i: int) -> tuple[int, int]:
            status, _, payload = self.api.call(
                "GET", f"/api/reviewer/assignments/{self.review_assignment}/document/",
                phase="download_sanitized", token=self.tokens["reviewer"],
            )
            return status, len(payload)

        sanitized = self.args.sanitized
        total = users + sanitized

        def mixed(i: int) -> tuple[str, int, int]:
            if i < users:
                return ("catalog", *catalog_download(i))
            return ("sanitized", *reviewer_download(i))

        outcome = self.parallel(total, mixed)
        catalog = [r for r in outcome if r[0] == "catalog"]
        reviewer = [r for r in outcome if r[0] == "sanitized"]
        self.report.check("las descargas del catálogo devuelven 200 con el PDF completo",
                          all(s == 200 and size >= self.big_size // 2 for _, s, size in catalog),
                          f"{sum(1 for _, s, _ in catalog if s == 200)}/{len(catalog)}")
        self.report.check("las descargas sanitizadas del revisor devuelven 200",
                          all(s == 200 and size > 0 for _, s, size in reviewer),
                          f"{sum(1 for _, s, _ in reviewer if s == 200)}/{len(reviewer)}")

    # -- 5. cargas --------------------------------------------------------
    def phase_uploads(self) -> None:
        count = self.args.uploads
        size = PDF_LIMIT - 4096
        print(f"\n5. {count} cargas concurrentes de PDF de {size / MIB:.1f} MB", flush=True)
        pdfs = [make_pdf(size) for _ in range(count)]
        base = 10  # autores 10 en adelante: no chocan con los del catálogo

        def upload(i: int) -> int:
            token = self.tokens[f"author-{base + i:02d}"]
            created = self.api.call(
                "POST", "/api/manuscripts/", phase="upload_setup", token=token,
                json_body={"title": f"Carga grande {i} {uuid.uuid4().hex[:6]}",
                           "abstract": "Resumen.", "keywords": ["carga"], "area": "Agronomía",
                           "language": "es", "authors": [{
                               "full_name": f"Autor{base + i:02d} Carga",
                               "email": f"load-author-{base + i:02d}@carga.invalid",
                               "affiliation": "UNL", "is_corresponding": True}]},
            )
            manuscript_id = as_json(created[2]).get("id")
            body, content_type = multipart("file", "grande.pdf", pdfs[i])
            status, _, _ = self.api.call(
                "POST", f"/api/manuscripts/{manuscript_id}/draft-file/", phase="upload", token=token,
                body=body, headers={"Content-Type": content_type},
            )
            return status

        statuses = self.parallel(count, upload)
        self.report.check("Nginx acepta y Django guarda las cargas de ~50 MB (201)",
                          all(s == 201 for s in statuses), f"estados {sorted(statuses)}")
        self.report.check("sin 502/503/504 durante las cargas",
                          not any(s >= 500 for s in statuses))

    def phase_disk_buffer(self) -> None:
        """Una carga lenta de 30 MB: Nginx debe acumularla en disco antes de pasarla a Gunicorn."""
        size, rate = 30 * MIB, 8 * MIB  # bytes y bytes por segundo
        print(f"\n   Buffer en disco: carga de {size // MIB} MB a {rate // MIB} MB/s", flush=True)
        token, manuscript_id = self.new_draft(43)
        body, content_type = multipart("file", "lenta.pdf", make_pdf(size))
        peak = [0]
        logged_before = nginx_logged_buffering()
        watcher = watch_nginx_temp(40)
        time.sleep(3)  # el bucle del contenedor ya está sondeando

        def read_samples() -> None:
            for line in watcher.stdout:
                if line.strip().isdigit():
                    peak[0] = max(peak[0], int(line) // 1024)

        reader = threading.Thread(target=read_samples, daemon=True)
        reader.start()
        sock = self.api.open_socket(120)
        head = (f"POST /api/manuscripts/{manuscript_id}/draft-file/ HTTP/1.1\r\nHost: localhost\r\n"
                f"Authorization: Bearer {token}\r\nContent-Type: {content_type}\r\n"
                f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n").encode()
        sock.sendall(head)
        chunk = rate // 8
        for offset in range(0, len(body), chunk):
            sock.sendall(body[offset:offset + chunk])
            time.sleep(0.125)
        answer = b""
        while b"\r\n" not in answer:
            data = sock.recv(4096)
            if not data:
                break
            answer += data
        sock.close()
        time.sleep(1)
        watcher.terminate()
        reader.join(timeout=5)
        status_line = answer.split(b"\r\n")[0].decode(errors="replace")
        self.report.check("la carga lenta termina en 201", " 201 " in status_line, status_line)
        self.report.nginx_temp_peak_kib = max(self.report.nginx_temp_peak_kib, peak[0])
        self.report.check("Nginx acumuló el cuerpo en su buffer en disco antes de pasarlo a Gunicorn",
                          peak[0] >= (size // 1024) * 0.6,
                          f"pico de client_temp: {peak[0] / 1024:.1f} MiB de {size // MIB} MiB enviados")
        self.report.check("Nginx registró el uso del archivo temporal",
                          nginx_logged_buffering() > logged_before)

    # -- 6. bordes de Nginx ----------------------------------------------
    def new_draft(self, index: int) -> tuple[str, str]:
        token = self.tokens[f"author-{index:02d}"]
        created = self.api.call(
            "POST", "/api/manuscripts/", phase="edge_setup", token=token,
            json_body={"title": f"Borde {uuid.uuid4().hex[:6]}", "abstract": "Resumen.",
                       "keywords": ["borde"], "area": "Agronomía", "language": "es",
                       "authors": [{"full_name": f"Autor{index:02d} Carga",
                                    "email": f"load-author-{index:02d}@carga.invalid",
                                    "affiliation": "UNL", "is_corresponding": True}]},
        )
        return token, as_json(created[2]).get("id", "")

    def upload_status(self, content: bytes, index: int = 40, phase: str = "edge") -> tuple[int, dict, bytes]:
        token, manuscript_id = self.new_draft(index)
        self.last_manuscript_id = manuscript_id
        body, content_type = multipart("file", "borde.pdf", content)
        return self.api.call(
            "POST", f"/api/manuscripts/{manuscript_id}/draft-file/", phase=phase, token=token,
            body=body, headers={"Content-Type": content_type},
        )

    def backend_saw(self, manuscript_id: str, since: str) -> int:
        """Líneas del registro de Gunicorn con una carga a ese borrador."""
        logs = subprocess.run(
            [*COMPOSE, "logs", "--no-log-prefix", "--since", since, "backend"],
            capture_output=True, text=True, check=False,
        ).stdout
        return len(re.findall(rf"POST /api/manuscripts/{manuscript_id}/draft-file/", logs))

    def phase_edges(self) -> None:
        print("\n6. Bordes de Nginx y del backend", flush=True)
        status, _, _ = self.upload_status(make_pdf(PDF_LIMIT), index=40)
        self.report.check("un PDF de exactamente 50 MB se acepta (201)", status == 201, f"estado {status}")

        status, _, payload = self.upload_status(make_pdf(PDF_LIMIT + MIB), index=41)
        self.report.check("un PDF de 51 MB llega a Django y se rechaza con 413 PDF_TOO_LARGE",
                          status == 413 and as_json(payload).get("error", {}).get("code") == "PDF_TOO_LARGE",
                          f"estado {status}")

        since = (datetime.now(timezone.utc) - timedelta(seconds=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        huge = b"\0" * (NGINX_BODY_LIMIT + MIB)  # 61 MB
        started = time.monotonic()
        status, headers, payload = self.upload_status(huge, index=42)
        elapsed = time.monotonic() - started
        self.report.check("un cuerpo de 61 MB lo rechaza Nginx con 413", status == 413,
                          f"estado {status} en {elapsed:.1f} s")
        self.report.check("la respuesta es de Nginx (no JSON del backend)",
                          "json" not in headers.get("content-type", "") and b"PDF_TOO_LARGE" not in payload)
        time.sleep(1)
        reached = self.backend_saw(self.last_manuscript_id, since)
        self.report.check("el cuerpo de 61 MB nunca llegó a Gunicorn", reached == 0,
                          f"{reached} peticiones de carga en el registro del backend")
        self.report.check("el backend sigue respondiendo tras el rechazo", self.health_ok())

        self.phase_disk_buffer()
        self.phase_slow_clients()

    def phase_slow_clients(self) -> None:
        workers = 3
        slow = workers * 2
        duration = self.args.slow_seconds
        print(f"\n   Clientes lentos: {slow} cargas a goteo ({workers} workers) durante ~{duration} s", flush=True)
        stop = threading.Event()

        def trickle(i: int) -> None:
            body = b"x" * (2 * MIB)
            head = (f"POST /api/manuscripts/00000000-0000-0000-0000-000000000000/draft-file/ HTTP/1.1\r\n"
                    f"Host: localhost\r\nContent-Type: application/octet-stream\r\n"
                    f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n").encode()
            sock = self.api.open_socket(30)
            try:
                sock.sendall(head)
                step = max(1, len(body) // (duration * 2))
                sent = 0
                while sent < len(body) and not stop.is_set():
                    sock.sendall(body[sent:sent + step])
                    sent += step
                    time.sleep(0.5)
            except OSError:
                pass
            finally:
                sock.close()

        threads = [threading.Thread(target=trickle, args=(i,), daemon=True) for i in range(slow)]
        for thread in threads:
            thread.start()
        latencies = []
        end = time.monotonic() + duration
        while time.monotonic() < end:
            started = time.monotonic()
            ok = self.health_ok()
            latencies.append((time.monotonic() - started, ok))
            time.sleep(0.5)
        stop.set()
        for thread in threads:
            thread.join(timeout=5)
        worst = max(seconds for seconds, _ in latencies)
        self.report.check("con clientes lentos el backend responde siempre (sin workers ocupados)",
                          all(ok for _, ok in latencies) and worst < 1.5,
                          f"{len(latencies)} sondeos, peor {worst:.2f} s")

    def phase_timeouts(self) -> None:
        print("\n7. Corte por inactividad del cuerpo (client_body_timeout 120 s)", flush=True)
        sock = self.api.open_socket(150)
        sock.sendall((b"POST /api/manuscripts/00000000-0000-0000-0000-000000000000/draft-file/ HTTP/1.1\r\n"
                      b"Host: localhost\r\nContent-Type: application/octet-stream\r\n"
                      b"Content-Length: 1048576\r\n\r\n") + b"x" * 1024)
        started = time.monotonic()
        answer = b""
        try:
            while b"\r\n" not in answer:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                answer += chunk
        except OSError:
            pass
        finally:
            sock.close()
        elapsed = time.monotonic() - started
        line = answer.split(b"\r\n")[0].decode(errors="replace")
        # Nginx registra este cierre a nivel `info`, que `error_log warn` no emite:
        # la evidencia es el instante del cierre.
        self.report.check("Nginx corta el cuerpo detenido a los ~120 s (cierra o responde 408)",
                          (not line or "408" in line) and 110 <= elapsed <= 135,
                          f"{line or 'conexión cerrada sin respuesta'} tras {elapsed:.0f} s")
        self.report.check("el backend sigue respondiendo", self.health_ok())

    # -- orquestación -----------------------------------------------------
    def run(self) -> int:
        if not self.health_ok():
            print("El stack no responde en /api/health/", file=sys.stderr)
            return 2
        sampler = Sampler(self.report)
        sampler.start()
        try:
            self.phase_config()
            self.phase_login()
            self.phase_seed()
            self.phase_catalog()
            self.phase_downloads()
            self.phase_uploads()
            self.phase_edges()
            if self.args.timeouts:
                self.phase_timeouts()
        finally:
            sampler.finish()
        return self.summary()

    def summary(self) -> int:
        report = self.report
        print("\n8. Memoria de los contenedores", flush=True)
        for name, entry in sorted(report.memory.items()):
            limit = entry.get("limit", 0)
            peak = entry["peak"]
            if limit:
                report.check(
                    f"{name}: pico {peak / MIB:.0f} MiB de {limit / MIB:.0f} MiB (<90 %), sin OOM ni reinicios",
                    peak < 0.9 * limit and not entry.get("oom") and entry.get("restarts", 0) == 0,
                )
            else:
                report.check(f"{name}: sin límite de memoria definido (pico {peak / MIB:.0f} MiB)", False)
        print("\nTiempos por fase (s):", flush=True)
        for phase, values in sorted(report.timings.items()):
            print(f"  {phase:<20} n={len(values):<4} p50={statistics.median(values):.3f} "
                  f"p95={percentile(values, 95):.3f} máx={max(values):.3f} estados={report.statuses[phase]}")
        failed = [c for c in report.checks if not c.ok]
        out = {
            "checks": [c.__dict__ for c in report.checks],
            "timings": {p: {"n": len(v), "p50": statistics.median(v), "p95": percentile(v, 95), "max": max(v)}
                        for p, v in report.timings.items()},
            "statuses": {p: {str(k): n for k, n in c.items()} for p, c in report.statuses.items()},
            "memory": report.memory, "nginx_temp_peak_kib": report.nginx_temp_peak_kib,
        }
        if self.args.output:
            with open(self.args.output, "w", encoding="utf-8") as handle:
                json.dump(out, handle, indent=2, ensure_ascii=False)
        print(f"\nResultado: {len(report.checks) - len(failed)}/{len(report.checks)} criterios cumplidos", flush=True)
        return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--base-url", default=os.environ.get("LOAD_BASE_URL", "https://localhost:18443"))
    parser.add_argument("--password", default=os.environ.get("LOAD_PASSWORD", ""))
    parser.add_argument("--users", type=int, default=int(os.environ.get("LOAD_USERS", "50")))
    parser.add_argument("--articles", type=int, default=int(os.environ.get("LOAD_ARTICLES", "8")))
    parser.add_argument("--big-mb", type=int, default=int(os.environ.get("LOAD_BIG_MB", "49")))
    parser.add_argument("--uploads", type=int, default=int(os.environ.get("LOAD_UPLOADS", "5")))
    parser.add_argument("--sanitized", type=int, default=int(os.environ.get("LOAD_SANITIZED", "5")))
    parser.add_argument("--slow-seconds", type=int, default=int(os.environ.get("LOAD_SLOW_SECONDS", "20")))
    parser.add_argument("--timeouts", action="store_true", help="incluye el corte de 120 s (tarda ~2 min)")
    parser.add_argument("--output", default=os.environ.get("LOAD_OUTPUT", ""))
    args = parser.parse_args()
    if not args.password:
        parser.error("falta --password o LOAD_PASSWORD")
    return Scenario(args).run()


if __name__ == "__main__":
    sys.exit(main())
