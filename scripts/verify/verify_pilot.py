#!/usr/bin/env python3
"""Verifica restauración, integridad y superficie expuesta (TSK-87).

Lo lanza ``scripts/verify_pilot.sh`` contra un stack AISLADO (proyecto
``gpc_verify``), nunca contra el de trabajo. Recorre, con datos sembrados por la
API real:

1. Respaldo con ``scripts/backup.sh`` y huella del estado (filas por modelo,
   SHA-256 de cada archivo, último hash de la cadena de auditoría).
2. Un respaldo alterado se rechaza SIN tocar la base.
3. Desastre (se borran los volúmenes) y ``scripts/restore.sh`` sobre una base vacía.
4. La huella restaurada es idéntica y ``verify_integrity`` pasa; un PDF alterado
   se detecta, y volver a restaurar lo repara.
5. Superficie expuesta: puertos publicados, ubicaciones internas y ``/media/``,
   redirección a HTTPS, versiones TLS, certificado, cookies y cabeceras.

Solo biblioteca estándar. Código de salida 0 si todo se cumple, 1 si no.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlencode, urlparse

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "load"))
import load_test  # noqa: E402  (reutiliza Api, Report, Scenario y make_pdf)

COMPOSE = load_test.COMPOSE
SECURITY_HEADERS = {
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "strict-origin-when-cross-origin",
}


def run(command: list[str], *, stdin: bytes | None = None, env: dict | None = None,
        timeout: int = 900) -> subprocess.CompletedProcess:
    return subprocess.run(command, input=stdin, capture_output=True, check=False, timeout=timeout,
                          env={**os.environ, **(env or {})}, cwd=ROOT)


def compose(*args: str, stdin: bytes | None = None) -> subprocess.CompletedProcess:
    return run([*COMPOSE, *args], stdin=stdin)


def text(result: subprocess.CompletedProcess) -> str:
    return (result.stdout + result.stderr).decode(errors="replace")


class Verifier:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.report = load_test.Report()
        self.api = load_test.Api(args.base_url, self.report)
        self.http = load_test.Api(args.http_url, self.report)
        self.workdir = Path(tempfile.mkdtemp(prefix="gpc_verify_"))
        self.backups = self.workdir / "backups"
        self.script_env = {"COMPOSE": " ".join(COMPOSE), "BACKUP_ROOT": str(self.backups)}
        self.scenario: load_test.Scenario | None = None

    def check(self, name: str, ok: bool, detail: str = "") -> bool:
        return self.report.check(name, ok, detail)

    # -- utilidades -------------------------------------------------------
    def wait_healthy(self, timeout: int = 240) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            status, _, _ = self.api.call("GET", "/api/health/", phase="health")
            if status == 200:
                return True
            time.sleep(3)
        return False

    def fingerprint(self) -> dict:
        source = (ROOT / "scripts" / "verify" / "fingerprint.py").read_bytes()
        result = compose("exec", "-T", "backend", "python", "manage.py", "shell", stdin=source)
        for line in text(result).splitlines():
            if line.startswith("FINGERPRINT "):
                return json.loads(line.removeprefix("FINGERPRINT "))
        raise RuntimeError("no se obtuvo la huella: " + text(result)[-400:])

    def api_snapshot(self) -> dict:
        """Lo que ve un usuario: el catálogo y el PDF que se descarga por Nginx."""
        scenario = self.scenario
        _, _, payload = self.api.call("GET", "/api/catalog/", phase="snapshot")
        codes = sorted(row["code"] for row in load_test.as_json(payload).get("results", []))
        documents = {}
        for code in codes:
            status, _, body = self.api.call("GET", f"/api/catalog/{code}/document/", phase="snapshot")
            documents[code] = hashlib.sha256(body).hexdigest() if status == 200 else f"HTTP {status}"
        status, _, body = self.api.call(
            "GET", f"/api/reviewer/assignments/{scenario.review_assignment}/document/",
            phase="snapshot", token=scenario.login("load-reviewer"))
        return {"codes": codes, "catalog": documents,
                "sanitized": hashlib.sha256(body).hexdigest() if status == 200 else f"HTTP {status}"}

    def script(self, name: str, *argv: str) -> subprocess.CompletedProcess:
        return run([str(ROOT / "scripts" / name), *argv], env=self.script_env)

    def latest_backup(self) -> Path:
        return sorted(p for p in self.backups.iterdir() if p.is_dir())[-1]

    # -- 1. datos y respaldo ----------------------------------------------
    def phase_backup(self) -> None:
        print("\n1. Siembra por la API real y respaldo", flush=True)
        scenario = load_test.Scenario(SimpleNamespace(
            base_url=self.args.base_url, password=self.args.password, users=self.args.authors,
            articles=self.args.articles, big_mb=1, uploads=0, sanitized=0, slow_seconds=0,
            timeouts=False, output=""))
        self.scenario = scenario
        scenario.phase_login()
        scenario.phase_seed()
        self.before_api = self.api_snapshot()
        self.check("el catálogo sembrado tiene artículos con PDF",
                   len(self.before_api["catalog"]) >= self.args.articles
                   and all(not v.startswith("HTTP") for v in self.before_api["catalog"].values()),
                   f"{len(self.before_api['catalog'])} artículos")
        self.before = self.fingerprint()
        self.check("hay filas, archivos y auditoría que respaldar",
                   sum(self.before["rows"].values()) > 0 and len(self.before["files"]) >= 4
                   and bool(self.before["audit_last_hash"]),
                   f"{sum(self.before['rows'].values())} filas, {len(self.before['files'])} archivos")

        result = self.script("backup.sh")
        self.check("backup.sh termina bien", result.returncode == 0, text(result).strip()[-120:])
        backup = self.latest_backup()
        names = sorted(p.name for p in backup.iterdir())
        self.check("el respaldo contiene database.dump, media.tar.gz y SHA256SUMS",
                   names == ["SHA256SUMS", "database.dump", "media.tar.gz"], ", ".join(names))
        check = subprocess.run(["sha256sum", "--check", "--strict", "SHA256SUMS"], cwd=backup,
                               capture_output=True, text=True, check=False)
        self.check("los checksums del respaldo son válidos", check.returncode == 0, check.stdout.strip())
        modes = {p.name: oct(p.stat().st_mode & 0o777) for p in backup.iterdir()}
        self.check("el respaldo no es legible por otros usuarios (0600/0700)",
                   all(mode == "0o600" for mode in modes.values())
                   and (backup.stat().st_mode & 0o777) == 0o700, str(modes))
        self.backup = backup

    # -- 2. respaldo alterado ---------------------------------------------
    def phase_tampered_backup(self) -> None:
        print("\n2. Un respaldo alterado se rechaza sin tocar la base", flush=True)
        tampered = self.workdir / "tampered"
        shutil.copytree(self.backup, tampered)
        with open(tampered / "database.dump", "ab") as handle:
            handle.write(b"x")
        result = self.script("restore.sh", "--yes", str(tampered))
        self.check("restore.sh rechaza un respaldo con checksum inválido", result.returncode != 0,
                   text(result).strip().splitlines()[-1] if text(result).strip() else "")
        self.check("la base y los archivos siguen intactos tras el rechazo",
                   self.fingerprint() == self.before)
        shutil.rmtree(tampered)

    # -- 3. desastre y restauración ---------------------------------------
    def phase_restore(self) -> None:
        print("\n3. Desastre: se borran los volúmenes y se restaura sobre una base vacía", flush=True)
        compose("down", "-v", "--remove-orphans")
        compose("up", "-d", "db")
        for _ in range(40):
            health = run(["docker", "inspect", "-f", "{{.State.Health.Status}}",
                          f"{os.environ['VERIFY_PROJECT']}-db-1"])
            if health.stdout.decode().strip() == "healthy":
                break
            time.sleep(2)
        result = self.script("restore.sh", "--yes", str(self.backup))
        output = text(result)
        self.restore_output = output
        self.check("restore.sh termina bien sobre una base vacía", result.returncode == 0,
                   output.strip().splitlines()[-1] if output.strip() else "")
        if result.returncode != 0:
            print(output[-2500:], flush=True)
        self.check("la restauración ejecutó verify_integrity", "Integridad correcta" in output)
        self.check("el stack vuelve a estar sano", self.wait_healthy())

    # -- 4. la huella restaurada ------------------------------------------
    def phase_compare(self) -> None:
        print("\n4. El estado restaurado es idéntico y la integridad se detecta", flush=True)
        after = self.fingerprint()
        self.check("mismas filas en todos los modelos", after["rows"] == self.before["rows"],
                   self.diff(self.before["rows"], after["rows"]))
        self.check("mismos archivos con el mismo SHA-256", after["files"] == self.before["files"],
                   self.diff(self.before["files"], after["files"]))
        self.check("la cadena de auditoría termina en el mismo hash",
                   after["audit_last_hash"] == self.before["audit_last_hash"])
        result = self.script("verify_integrity.sh")
        self.check("verify_integrity: sin discrepancias tras restaurar", result.returncode == 0,
                   text(result).strip().splitlines()[-1] if text(result).strip() else "")
        self.scenario.tokens.clear()
        self.check("las cuentas restauradas inician sesión con su contraseña",
                   bool(self.scenario.login("load-editor")))
        self.check("el catálogo y los PDF entregados por Nginx son los mismos",
                   self.api_snapshot() == self.before_api)

        victim = next(path for path in self.before["files"] if path.endswith("sanitized.pdf"))
        compose("exec", "-T", "backend", "sh", "-c", f"printf x >> '/data/media/{victim}'")
        broken = self.script("verify_integrity.sh")
        self.check("verify_integrity detecta un PDF alterado (sale distinto de cero)",
                   broken.returncode != 0 and "DISCREPANCIA" in text(broken),
                   text(broken).strip().splitlines()[-1] if text(broken).strip() else "")
        repaired = self.script("restore.sh", "--yes", str(self.backup))
        self.check("restaurar de nuevo repara el PDF alterado",
                   repaired.returncode == 0 and self.wait_healthy() and self.fingerprint()["files"]
                   == self.before["files"])

    @staticmethod
    def diff(before: dict, after: dict) -> str:
        keys = sorted(k for k in before.keys() | after.keys() if before.get(k) != after.get(k))
        return ", ".join(keys[:4])

    # -- 5. superficie expuesta -------------------------------------------
    def phase_ports(self) -> None:
        print("\n5. Puertos publicados", flush=True)
        base = run(["docker", "compose", "-f", "docker-compose.yml", "config", "--format", "json"])
        services = json.loads(base.stdout)["services"]
        published = {name: [(p.get("published"), p.get("host_ip", "")) for p in svc.get("ports", [])]
                     for name, svc in services.items()}
        self.check("compose base: solo existen db, backend y web (sin adminer)",
                   sorted(services) == ["backend", "db", "web"], ", ".join(sorted(services)))
        self.check("compose base: db y backend no publican puertos",
                   not published["db"] and not published["backend"])
        self.check("compose base: web publica solo 80 y 443",
                   sorted(port for port, _ in published["web"]) == ["443", "80"], str(published["web"]))
        dev = run(["docker", "compose", "-f", "docker-compose.yml", "-f", "docker-compose.dev.yml",
                   "config", "--format", "json"])
        extra = [p for svc in json.loads(dev.stdout)["services"].values() for p in svc.get("ports", [])
                 if p.get("published") not in ("80", "443")]
        self.check("compose de desarrollo: db y adminer solo escuchan en 127.0.0.1",
                   bool(extra) and all(p.get("host_ip") == "127.0.0.1" for p in extra),
                   ", ".join(f"{p.get('host_ip')}:{p.get('published')}" for p in extra))

        project = os.environ["VERIFY_PROJECT"]
        listing = run(["docker", "ps", "--filter", f"label=com.docker.compose.project={project}",
                       "--format", "{{.Names}}|{{.Ports}}"]).stdout.decode().splitlines()
        runtime = {line.split("|")[0].removeprefix(f"{project}-").removesuffix("-1"): line.split("|")[1]
                   for line in listing}
        self.check("en ejecución: solo web tiene puertos enlazados al host",
                   sorted(runtime) == ["backend", "db", "web"]
                   and "->" in runtime["web"] and "->" not in runtime["db"] and "->" not in runtime["backend"],
                   str(runtime))
        internal = run(["docker", "network", "inspect", f"{project}_backend_net",
                        "--format", "{{.Internal}}"]).stdout.decode().strip()
        self.check("backend_net es interna (sin salida al exterior)", internal == "true", internal)

    def raw(self, api, path: str, headers: dict | None = None, method: str = "GET", token: str | None = None):
        """Respuesta sin normalizar: conserva las cabeceras repetidas."""
        connection = api.connect()
        send = dict(headers or {})
        if token:
            send["Authorization"] = f"Bearer {token}"
        try:
            connection.request(method, path, headers=send)
            response = connection.getresponse()
            return response.status, response.getheaders(), response.read(2_000_000)
        except Exception as error:  # noqa: BLE001  (red caída, TLS roto, etc.)
            return 0, [], repr(error).encode()
        finally:
            connection.close()

    def phase_internal(self) -> None:
        print("\n6. Ubicaciones internas y /media/ desde el exterior", flush=True)
        files = sorted(self.before["files"])
        private = next(f for f in files if f.startswith("private/") and f.endswith("sanitized.pdf"))
        original = next(f for f in files if f.startswith("private/") and f.endswith("original.pdf"))
        catalog = next(f for f in files if f.startswith("public/catalog/"))
        inner = {"private": private.removeprefix("private/"), "original": original.removeprefix("private/"),
                 "catalog": catalog.removeprefix("public/catalog/")}
        probes = {
            "/_protected/ sanitizado": f"/_protected/{inner['private']}",
            "/_protected/ original": f"/_protected/{inner['original']}",
            "/_catalog/ copia pública": f"/_catalog/{inner['catalog']}",
            "/media/ archivo privado": f"/media/{private}",
            "/media/ copia pública": f"/media/{catalog}",
            "/media/ raíz": "/media/",
            "doble barra //_protected/": f"//_protected/{inner['private']}",
            "ruta codificada %5Fprotected": f"/%5Fprotected/{inner['private']}",
            "retroceso /media/../_protected/": f"/media/../_protected/{inner['private']}",
            "retroceso codificado %2e%2e": f"/static/%2e%2e/_protected/{inner['private']}",
        }
        for label, path in probes.items():
            status, _, body = self.raw(self.api, path)
            served_spa = b"<app-root" in body
            self.check(f"HTTPS {label} → {status} sin PDF",
                       status in (403, 404) or (served_spa and b"%PDF" not in body[:8]),
                       "")
            if status == 200:
                self.check(f"{label}: el 200 es el index de la SPA, no un archivo",
                           served_spa and b"%PDF" not in body)
        # Un cliente no puede pedir la entrega interna con su propia cabecera.
        status, _, body = self.raw(self.api, "/api/health/",
                                   {"X-Accel-Redirect": f"/_protected/{inner['private']}"})
        self.check("X-Accel-Redirect enviado por el cliente se ignora", status == 200 and b"%PDF" not in body)
        # Por HTTP plano nada se entrega: solo la redirección.
        status, hdrs, body = self.raw(self.http, f"/_protected/{inner['private']}")
        self.check("HTTP /_protected/ → 301 sin cuerpo con PDF", status == 301 and b"%PDF" not in body)

        # Control positivo: lo autorizado sí se entrega por Nginx.
        code = self.before_api["codes"][0]
        status, hdrs, body = self.raw(self.api, f"/api/catalog/{code}/document/")
        headers = {k.lower(): v for k, v in hdrs}
        self.check("control positivo: el catálogo entrega el PDF por Nginx",
                   status == 200 and body.startswith(b"%PDF") and headers.get("content-type") == "application/pdf",
                   f"{status} {headers.get('content-type')}")

    def phase_tls_and_headers(self) -> None:
        print("\n7. HTTPS, certificado, cookies y cabeceras de seguridad", flush=True)
        status, hdrs, body = self.raw(self.http, "/api/health/?x=1")
        location = dict((k.lower(), v) for k, v in hdrs).get("location", "")
        self.check("HTTP redirige (301) a HTTPS conservando ruta y consulta",
                   status == 301 and location.startswith("https://") and location.endswith("/api/health/?x=1"),
                   location)
        self.check("HTTP no sirve contenido de la aplicación", b"<app-root" not in body and b"status" not in body)

        host, port = self.api.host, self.api.port
        for label, version in (("TLS 1.2", ssl.TLSVersion.TLSv1_2), ("TLS 1.3", ssl.TLSVersion.TLSv1_3)):
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            context.check_hostname, context.verify_mode = False, ssl.CERT_NONE
            context.minimum_version = context.maximum_version = version
            try:
                with context.wrap_socket(socket.create_connection((host, port), 10),
                                         server_hostname=host) as tls:
                    self.check(f"{label} se negocia", tls.version() == label.replace("TLS ", "TLSv"), tls.version())
            except (OSError, ssl.SSLError) as error:
                self.check(f"{label} se negocia", False, repr(error))
        for flag, label in (("-tls1_1", "TLS 1.1"), ("-tls1", "TLS 1.0")):
            probe = subprocess.run(
                ["openssl", "s_client", "-connect", f"{host}:{port}", flag, "-cipher", "ALL:@SECLEVEL=0"],
                input=b"", capture_output=True, timeout=20, check=False)
            output = (probe.stdout + probe.stderr).decode(errors="replace")
            client_cannot = re.search(r"no protocols available|unsupported protocol|Unknown option", output)
            # Un rechazo del servidor llega como alerta «protocol version» y ningún cifrado negociado.
            rejected = "alert protocol version" in output or "Cipher is (NONE)" in output
            if client_cannot:
                print(f"      aviso: {label} no se pudo probar (este OpenSSL no lo ofrece); "
                      "solo cuenta la comprobación de ssl_protocols", flush=True)
            else:
                self.check(f"{label} rechazado por el servidor", rejected,
                           "alerta «protocol version»" if rejected else "negociado")
        nginx = text(compose("exec", "-T", "web", "nginx", "-T"))
        self.check("Nginx: ssl_protocols TLSv1.2 TLSv1.3", "ssl_protocols             TLSv1.2 TLSv1.3;" in nginx)

        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname, context.verify_mode = False, ssl.CERT_NONE
        with context.wrap_socket(socket.create_connection((host, port), 10),
                                 server_hostname=host) as tls:
            served = hashlib.sha256(tls.getpeercert(binary_form=True)).hexdigest()
        pem = (ROOT / "nginx" / "certs" / "fullchain.pem").read_text()
        leaf = hashlib.sha256(ssl.PEM_cert_to_DER_cert(pem.split("-----END CERTIFICATE-----")[0]
                                                       + "-----END CERTIFICATE-----\n")).hexdigest()
        self.check("el certificado servido es el de nginx/certs/", served == leaf)
        end = subprocess.run(["openssl", "x509", "-noout", "-enddate", "-subject", "-issuer", "-in",
                              str(ROOT / "nginx" / "certs" / "fullchain.pem")],
                             capture_output=True, text=True, check=False).stdout
        expires = re.search(r"notAfter=(.+)", end).group(1).strip()
        days = (ssl.cert_time_to_seconds(expires) - time.time()) / 86400
        subject = re.search(r"subject=(.+)", end).group(1).strip()
        issuer = re.search(r"issuer=(.+)", end).group(1).strip()
        self.check("el certificado vence en más de 30 días", days > 30, f"{days:.0f} días")
        if subject == issuer:
            print("      aviso: el certificado es AUTOFIRMADO (piloto); producción necesita el institucional", flush=True)

        # Cabeceras en respuestas de todo tipo (éxito, error, estático, SPA, PDF).
        token = self.scenario.login("load-reviewer")
        urls = {
            "SPA /": ("/", None), "SPA /catalog": ("/catalog", None),
            "API salud": ("/api/health/", None), "API catálogo": ("/api/catalog/", None),
            "API 404": ("/api/no-existe/", None), "estático inexistente": ("/static/no-existe.css", None),
            "/media/ denegado": ("/media/x", None), "/_protected/ denegado": ("/_protected/x", None),
            "PDF del catálogo": (f"/api/catalog/{self.before_api['codes'][0]}/document/", None),
            "PDF sanitizado del revisor": (
                f"/api/reviewer/assignments/{self.scenario.review_assignment}/document/", token),
            "API sin credenciales (401)": ("/api/manuscripts/", None),
        }
        for label, (path, bearer) in urls.items():
            status, hdrs, _ = self.raw(self.api, path, token=bearer)
            names = [k.lower() for k, _ in hdrs]
            values = {k.lower(): v for k, v in hdrs}
            missing = [h for h, v in SECURITY_HEADERS.items() if values.get(h) != v]
            csp = values.get("content-security-policy", "")
            if "permissions-policy" not in values:
                missing.append("permissions-policy")
            if "frame-ancestors 'none'" not in csp or "object-src 'none'" not in csp:
                missing.append("content-security-policy")
            repeated = sorted({n for n in names if n in (*SECURITY_HEADERS, "content-security-policy",
                                                         "permissions-policy") and names.count(n) > 1})
            self.check(f"cabeceras de seguridad en {label} ({status})", not missing and not repeated,
                       f"faltan {missing}" if missing else (f"repetidas {repeated}" if repeated else ""))
            self.check(f"{label}: no se filtra la ruta interna (X-Accel-Redirect)", "x-accel-redirect" not in names)
        status, hdrs, _ = self.raw(self.api, "/")
        server = {k.lower(): v for k, v in hdrs}.get("server", "")
        self.check("la cabecera Server no revela la versión", not re.search(r"\d", server), server)
        status, hdrs, _ = self.raw(self.api, "/api/health/")
        hsts = {k.lower(): v for k, v in hdrs}.get("strict-transport-security", "")
        self.check("la API envía HSTS por HTTPS", "max-age=" in hsts, hsts)

        connection = self.api.connect()
        body = json.dumps({"identifier": "load-editor", "password": self.args.password})
        connection.request("POST", "/api/auth/login/", body=body, headers={"Content-Type": "application/json"})
        response = connection.getresponse()
        response.read()
        cookies = [v for k, v in response.getheaders() if k.lower() == "set-cookie"]
        connection.close()
        self.check("la cookie del refresh es Secure, HttpOnly y SameSite",
                   bool(cookies) and all("Secure" in c and "HttpOnly" in c and "SameSite" in c for c in cookies),
                   "; ".join(c.split(";")[0].split("=")[0] for c in cookies))

    def phase_admin(self) -> None:
        print("\n8. Django Admin a través de Nginx (alta de cuentas)", flush=True)
        password = self.args.password
        created = compose("exec", "-T", "-e", "DJANGO_SUPERUSER_USERNAME=soporte",
                          "-e", "DJANGO_SUPERUSER_EMAIL=soporte@example.invalid",
                          "-e", f"DJANGO_SUPERUSER_PASSWORD={password}",
                          "backend", "python", "manage.py", "createsuperuser", "--noinput")
        self.check("se crea el superusuario de soporte", created.returncode == 0, text(created).strip()[-80:])

        def request(method, path, cookies, fields=None):
            connection = self.api.connect()
            headers = {"Cookie": "; ".join(f"{k}={v}" for k, v in cookies.items()),
                       "Referer": f"{self.args.base_url}/admin/login/"}
            body = None
            if fields is not None:
                body = urlencode(fields)
                headers["Content-Type"] = "application/x-www-form-urlencoded"
            try:
                connection.request(method, path, body=body, headers=headers)
                response = connection.getresponse()
                payload = response.read().decode(errors="replace")
                for key, value in response.getheaders():
                    if key.lower() == "set-cookie":
                        name, _, rest = value.partition("=")
                        cookies[name] = rest.partition(";")[0]
                return response.status, response.getheaders(), payload
            finally:
                connection.close()

        def login(user, secret):
            cookies: dict[str, str] = {}
            status, hdrs, page = request("GET", "/admin/login/", cookies)
            token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', page)
            if status != 200 or not token:
                return status, cookies, hdrs, page
            status, hdrs, page = request("POST", "/admin/login/", cookies, {
                "username": user, "password": secret, "next": "/admin/",
                "csrfmiddlewaretoken": token.group(1)})
            return status, cookies, hdrs, page

        status, cookies, hdrs, _ = login("soporte", password)
        cookie_lines = [v for k, v in hdrs if k.lower() == "set-cookie"]
        self.check("el superusuario entra al Admin por HTTPS (302)", status == 302 and "sessionid" in cookies, str(status))
        self.check("la cookie de sesión del Admin es Secure y HttpOnly",
                   any("sessionid" in c and "Secure" in c and "HttpOnly" in c for c in cookie_lines))
        status, hdrs, page = request("GET", "/admin/users/user/add/", cookies)
        self.check("el formulario de alta de cuentas carga", status == 200 and "institutional_id" in page, str(status))
        names = [k.lower() for k, _ in hdrs]
        values = {k.lower(): v for k, v in hdrs}
        self.check("cabeceras de seguridad, una sola vez, en el Admin",
                   all(values.get(h) == v for h, v in SECURITY_HEADERS.items())
                   and all(names.count(h) == 1 for h in SECURITY_HEADERS))
        status, _, _ = request("GET", "/static/admin/css/base.css", {})
        self.check("los estáticos del Admin los sirve Nginx", status == 200, str(status))

        status, cookies, _, _ = login("load-author-00", password)
        self.check("una cuenta de autor (sin staff) no entra al Admin", status == 200 and "sessionid" not in cookies, str(status))

        results = [login("soporte", "contraseña-equivocada")[0] for _ in range(12)]
        self.check("Nginx limita los intentos del login del Admin (429)", 429 in results, str(results))

    # -- orquestación -----------------------------------------------------
    def run(self) -> int:
        try:
            if not self.wait_healthy():
                print("El stack no responde en /api/health/", file=sys.stderr)
                return 2
            self.phase_backup()
            self.phase_tampered_backup()
            self.phase_restore()
            self.phase_compare()
            self.phase_ports()
            self.phase_internal()
            self.phase_tls_and_headers()
            self.phase_admin()
        finally:
            shutil.rmtree(self.workdir, ignore_errors=True)
        failed = [c for c in self.report.checks if not c.ok]
        if self.args.output:
            Path(self.args.output).write_text(json.dumps(
                {"checks": [c.__dict__ for c in self.report.checks]}, indent=2, ensure_ascii=False),
                encoding="utf-8")
        print(f"\nResultado: {len(self.report.checks) - len(failed)}/{len(self.report.checks)} criterios cumplidos",
              flush=True)
        return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--base-url", default=os.environ.get("VERIFY_BASE_URL", "https://localhost:19443"))
    parser.add_argument("--http-url", default=os.environ.get("VERIFY_HTTP_URL", "http://localhost:19080"))
    parser.add_argument("--password", default=os.environ.get("LOAD_PASSWORD", ""))
    parser.add_argument("--authors", type=int, default=5)  # un autor por artículo sembrado + 1
    parser.add_argument("--articles", type=int, default=3)
    parser.add_argument("--output", default=os.environ.get("VERIFY_OUTPUT", ""))
    args = parser.parse_args()
    if not args.password or not os.environ.get("VERIFY_PROJECT"):
        parser.error("faltan LOAD_PASSWORD y VERIFY_PROJECT (los define scripts/verify_pilot.sh)")
    return Verifier(args).run()


if __name__ == "__main__":
    sys.exit(main())
