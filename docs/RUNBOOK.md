# Runbook del piloto — Sistema de Gestión de Publicaciones Científicas

Guía para quien opera el servidor **sin conocer el código**. Cada procedimiento da el comando exacto, por qué se hace y cómo saber que salió bien. Los comandos de esta guía se probaron en un despliegue limpio y aislado (TSK-88); lo que no se pudo probar fuera de un servidor real está marcado como **pendiente en el servidor**.

> Todos los comandos se ejecutan desde la raíz del repositorio (`/opt/gpc` en el servidor) y con `docker compose` v2. Los valores entre `<…>` los pones tú. Esta guía no contiene secretos: las contraseñas viven solo en `.env`.

## Índice

1. [Qué se está operando](#1-qué-se-está-operando)
2. [Decisiones Q1–Q5 y cómo comprobarlas](#2-decisiones-q1q5-y-cómo-comprobarlas)
3. [Requisitos del servidor](#3-requisitos-del-servidor)
4. [Despliegue inicial](#4-despliegue-inicial)
5. [TLS y certificados](#5-tls-y-certificados)
6. [Límites de 50/60 MB, volumen, PostgreSQL y `X-Accel-Redirect`](#6-límites-de-5060-mb-volumen-postgresql-y-x-accel-redirect)
7. [Operación diaria y actualizaciones](#7-operación-diaria-y-actualizaciones)
8. [Respaldos](#8-respaldos)
9. [Restauración](#9-restauración)
10. [Tareas programadas (cron) y logs](#10-tareas-programadas-cron-y-logs)
11. [Credenciales institucionales](#11-credenciales-institucionales)
12. [Incidentes](#12-incidentes)
13. [Criterios de aceptación del piloto](#13-criterios-de-aceptación-del-piloto)
14. [Anexo: registro de la prueba mensual de restauración](#14-anexo-registro-de-la-prueba-mensual-de-restauración)

---

## 1. Qué se está operando

Tres contenedores en un único servidor Linux (Docker Compose):

| Servicio | Qué hace | Puertos | Memoria máx. |
|---|---|---|---|
| `web` | Nginx: sirve la aplicación Angular, termina TLS, limita las cargas y entrega los PDF | **80** (solo redirige) y **443** — los únicos publicados | 256 MB |
| `backend` | Django + Gunicorn (3 workers, timeout 120 s): API, autorización, sanitizado de PDF | ninguno (red interna) | 1 GB |
| `db` | PostgreSQL 16 | ninguno (red interna) | 512 MB |

Datos persistentes (volúmenes de Docker): `postgres_data` (base) y `media_data` (todos los PDF). **Perder cualquiera de los dos sin respaldo es perder el expediente.** `static_data` es regenerable.

Roles de la aplicación: `AUTHOR`, `REVIEWER`, `EDITOR`, `ADMIN`. El flujo editorial es **doble ciego**: el Revisor nunca ve la identidad del Autor y viceversa; no hay instrucciones de operación que requieran saltarse eso.

Archivos que importan:

| Archivo | Para qué |
|---|---|
| `.env` (no versionado, permisos `0600`) | Todos los secretos y parámetros |
| `docker-compose.yml` | Servicios y límites de memoria |
| `nginx/conf.d/default.conf`, `nginx/certs/` | Nginx y su certificado |
| `scripts/backup.sh`, `restore.sh`, `verify_integrity.sh` | Respaldo, restauración, integridad |
| `scripts/cron/gpc.cron`, `scripts/cron/gpc.logrotate` | Tareas programadas y rotación de logs |
| `scripts/verify_pilot.sh`, `scripts/load_test.sh` | Verificación de restauración y de carga (pilas aisladas) |
| `scripts/check_runbook.py` | Comprueba que esta guía y las decisiones Q1–Q5 siguen siendo ciertas |

---

## 2. Decisiones Q1–Q5 y cómo comprobarlas

Son las cinco decisiones de infraestructura que fijó la especificación (`.spec-kit/clarify.md`). Se comprueban en estático con:

```bash
./scripts/check_runbook.py
```

*Por qué:* detecta el día que alguien cambie un límite o un puerto sin actualizar el resto. Termina con código distinto de cero si algo no coincide. El CI lo ejecuta en cada cambio.

| | Decisión | Dónde está implementada | Cómo se comprueba en vivo | Estado |
|---|---|---|---|---|
| **Q1** | PDF en **volumen local**: original y copia sanitizada inmutables, en rutas separadas | `media_data` en `/data/media` (`private/drafts`, `private/manuscripts`, `public/catalog`, `tmp/uploads`); lo crea `scripts/init_media.sh` al arrancar | `docker compose exec backend find /data/media -maxdepth 2 -type d` | ✅ |
| **Q2** | **50 MB** por PDF; **60 MB** en el proxy | `MAX_PDF_SIZE_MB=50`, `client_max_body_size 60m`, validador de Angular (50 MiB) y `DATA_UPLOAD_MAX_MEMORY_SIZE` de Django (60 MiB) | `./scripts/load_test.sh` (50 MB exactos → 201, 51 MB → 413, 61 MB → 413 de Nginx) | ✅ |
| **Q3** | **Un servidor Linux on-premise** con Compose; Nginx termina TLS | `docker-compose.yml` con `db`, `backend`, `web`; solo `web` publica 80/443 | `docker compose ps` y `./scripts/verify_pilot.sh` | ✅ (certificado institucional **pendiente en el servidor**) |
| **Q4** | **`X-Accel-Redirect`**: Django autoriza y Nginx entrega desde rutas internas separadas | `location /_protected/` (privado) y `/_catalog/` (público), ambas `internal`; `/media/` es `deny all` | `./scripts/smoke_media_isolation.sh` y `./scripts/verify_pilot.sh` | ✅ |
| **Q5** | Respaldo **diario completo cifrado** a almacenamiento **externo**, 30 días, prueba mensual | Diario 02:15 (`gpc.cron`), `RETENTION_DAYS=30`, prueba mensual (§14) | `ls -l /backups` y la prueba de §9.1 | 🟡 **Parcial**: el script respalda y retiene, pero **no cifra ni copia fuera del servidor**; eso se hace con §8.3 |

> **Q5 es la única decisión que no queda cubierta solo con configuración.** `backup.sh` deja el respaldo en `BACKUP_ROOT` (permisos `0700`). El cifrado y la copia externa dependen de §8.3: sin ellos el respaldo vive en el mismo servidor que los datos.

---

## 3. Requisitos del servidor

- Linux con **Docker Engine y Docker Compose v2**, `git`, `openssl`, `cron` y `logrotate`.
- **4 vCPU, 8 GB de RAM y 200 GB de disco SSD** (línea base del plan). Los contenedores suman como máximo 1,75 GB; el resto queda para el sistema y la compilación de las imágenes.
- Puertos **80 y 443** libres y alcanzables por los usuarios. **Ningún otro puerto** debe abrirse hacia fuera (ni 5432, ni 8000, ni 8888).
- Un nombre DNS para el servidor (en los ejemplos, `gpc.unl.edu.ec`).
- Un servidor SMTP institucional (host, puerto 587 con STARTTLS, usuario y contraseña).
- El certificado TLS institucional (`fullchain.pem` y `privkey.pem`).
- Un destino de respaldos **fuera de este servidor**, idealmente cifrado (§8.3).

---

## 4. Despliegue inicial

### 4.1 Preparar

```bash
sudo git clone https://github.com/RichardC022/Gestion_Publicaciones_Cientificas.git /opt/gpc
cd /opt/gpc
cp .env.example .env
chmod 600 .env
```

*Por qué `chmod 600`:* `.env` guarda las contraseñas; solo su dueño debe leerlo. Nunca lo versiones.

### 4.2 Configurar `.env`

Genera un valor aleatorio distinto para cada secreto (no inventes contraseñas a mano):

```bash
openssl rand -base64 48     # DJANGO_SECRET_KEY
openssl rand -base64 24     # POSTGRES_PASSWORD (otro valor)
openssl rand -base64 24     # APP_DB_PASSWORD (otro valor)
```

Edita `.env` y cambia, como mínimo:

| Variable | Qué poner |
|---|---|
| `DJANGO_SECRET_KEY`, `POSTGRES_PASSWORD`, `APP_DB_PASSWORD` | Los valores aleatorios de arriba. **Los tres distintos**; `APP_DB_USER` debe ser distinto de `POSTGRES_USER` |
| `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL` | Los datos del SMTP institucional |
| `ALLOWED_HOSTS` | El nombre DNS del servidor, separado por comas (p. ej. `gpc.unl.edu.ec`) |
| `CSRF_TRUSTED_ORIGINS` | `https://` + el nombre DNS (p. ej. `https://gpc.unl.edu.ec`) |
| `BACKUP_ROOT` | Ruta **absoluta** fuera del repositorio y de `/data/media` (por defecto `/backups`) |

Deja `DEBUG=0`, `DJANGO_SETTINGS_MODULE=config.settings.production` y `COOKIE_SECURE=1`. El arranque **se niega a continuar** si falta una variable obligatoria o si un secreto sigue siendo `change-me` (`scripts/check_env.sh`).

### 4.3 Certificado

Copia el institucional a `nginx/certs/fullchain.pem` y `nginx/certs/privkey.pem` (§5). **Nginx no arranca sin esos dos archivos.** Solo para un ensayo, sin certificado institucional:

```bash
./scripts/make_dev_cert.sh
```

### 4.4 Levantar

```bash
docker compose up -d --build
```

*Qué hace:* construye las imágenes y levanta `db`, `backend` y `web`. Al arrancar, el `backend` valida `.env`, prepara el volumen, aplica las migraciones, crea el rol restringido de la aplicación (`apply_db_privileges`), junta los estáticos y arranca Gunicorn. La primera vez tarda varios minutos.

### 4.5 Datos iniciales

```bash
docker compose exec backend python manage.py seed_roles
docker compose exec backend python manage.py createsuperuser
```

*Por qué:* `seed_roles` crea los cuatro roles (es idempotente: repetirlo no duplica nada). El superusuario es **solo para soporte** (Django Admin en `https://<host>/admin/`); no sustituye al flujo editorial. Las cuentas de las personas se crean según §11.

### 4.6 Verificar

```bash
docker compose ps                         # backend debe decir "healthy"
curl -ks https://localhost/api/health/    # {"status":"ok"}
curl -sI http://localhost/ | head -3      # 301 hacia https://
```

Y la verificación completa en una pila aparte, que no toca los datos:

```bash
./scripts/verify_pilot.sh                 # ~6 min; debe terminar en "61/61 criterios cumplidos"
```

Si algo no arranca, §12.1.

---

## 5. TLS y certificados

- Nginx sirve **solo HTTPS** (TLS 1.2 y 1.3); el puerto 80 únicamente responde `301` hacia `https://`.
- Nginx **no envía HSTS**; Django lo emite en las respuestas de la API.
- `server_tokens off`: la cabecera `Server` no revela la versión.

### 5.1 Instalar o renovar el certificado

```bash
sudo cp <fullchain.pem> nginx/certs/fullchain.pem
sudo cp <privkey.pem>   nginx/certs/privkey.pem
sudo chmod 600 nginx/certs/privkey.pem
docker compose exec web nginx -t          # valida la configuración y el certificado
docker compose exec web nginx -s reload   # lo aplica sin cortar conexiones
```

*Por qué `reload` y no `restart`:* recarga el certificado sin dejar a nadie sin servicio. Los `.pem` no se versionan (`.gitignore`).

### 5.2 Vigilar el vencimiento

```bash
openssl x509 -noout -subject -issuer -enddate -in nginx/certs/fullchain.pem
```

Si `subject` e `issuer` son iguales, el certificado es **autofirmado** y no sirve para usuarios reales. Anota la fecha de `notAfter` y renueva con al menos 30 días de margen.

### 5.3 HSTS con `preload` (decisión pendiente)

Django emite `Strict-Transport-Security: max-age=31536000; includeSubDomains; preload`. Con un certificado **autofirmado** eso es arriesgado (el navegador deja de permitir continuar tras el aviso). Con el certificado institucional válido, decide si conservar `preload` (`backend/config/settings/production.py`, deuda D-06).

---

## 6. Límites de 50/60 MB, volumen, PostgreSQL y `X-Accel-Redirect`

### 6.1 Cargas: por qué 50 y 60

```text
Navegador ──HTTPS──▶ Nginx (443)                       ──▶ Gunicorn/Django
                     client_max_body_size 60m              valida: PDF ≤ 50 MB
                     cuerpo completo a disco                (413 PDF_TOO_LARGE)
                     /var/cache/nginx/client_temp          sanitiza y guarda
```

- **50 MB** es el límite funcional por PDF (`MAX_PDF_SIZE_MB`), aplicado por Django y por el validador de Angular. 1 MB = 1.048.576 bytes.
- **60 MB** es el techo del cuerpo en Nginx: deja margen para el sobre multipart y las cabeceras. Un cuerpo mayor lo rechaza **Nginx** con `413` **sin que llegue a Gunicorn**.
- Nginx guarda el cuerpo entero en disco (`proxy_request_buffering on`) antes de pasarlo al backend: un cliente lento o que abandona **no ocupa un worker**. Los tiempos son de **120 s** (`client_body_timeout`, `proxy_read_timeout`, `proxy_send_timeout`, `--timeout` de Gunicorn).
- Cómo distinguir el rechazo: si la respuesta trae `{"error":{"code":"PDF_TOO_LARGE"…}}` fue Django (51–60 MB); si es una página corta de Nginx sin ese código, fue Nginx (> 60 MB).
- Si cambias estos límites, cambia **los cuatro sitios a la vez** (`.env`, `nginx/conf.d/default.conf`, `backend/config/settings/base.py`, `pdf-file.validation.ts`), reconstruye (`docker compose up -d --build`) y repite `./scripts/load_test.sh`.

### 6.2 El volumen `media_data`

```text
/data/media
├── private/drafts/        borradores del Autor
├── private/manuscripts/   por manuscrito y versión: original.pdf y sanitized.pdf (inmutables)
├── public/catalog/        copia pública de los artículos aceptados
└── tmp/uploads/           temporal; se vacía al arrancar
```

- Solo `backend` escribe; `web` lo monta **solo lectura**. Directorios `0750`, archivos `0640`, grupo `media`.
- Nunca se sirve como directorio público: `/media/` responde `403`.
- Ninguna versión se sobrescribe. Cada PDF tiene su SHA-256; `verify_integrity` los recalcula (§10).

### 6.3 PostgreSQL

- Volumen `postgres_data`; no publica puertos; solo alcanzable desde la red interna `backend_net`.
- **Dos roles:** `POSTGRES_USER` (administrador y dueño del esquema; migra, respalda y restaura) y `APP_DB_USER` (el que usa la aplicación: sin superusuario, y **sin `UPDATE`/`DELETE` sobre la auditoría**). El backend recrea el segundo en cada arranque.
- La auditoría es **append-only** (por trigger y por permisos). Comprobarlo:

```bash
docker compose exec backend python manage.py shell -c \
  "from django.db import connection; connection.cursor().execute('DELETE FROM audit_audit_log')"
```

Debe fallar con `permission denied for table audit_audit_log`.

### 6.4 `X-Accel-Redirect`: cómo se descargan los PDF

1. El navegador pide un PDF a la API (`/api/…/document/`). **Django** comprueba quién eres, si el PDF es tuyo o está asignado a ti, o si el artículo es público.
2. Si autoriza, responde **sin cuerpo** con la cabecera `X-Accel-Redirect: /_protected/…` (privado) o `/_catalog/…` (catálogo).
3. **Nginx** intercepta esa cabecera y entrega el archivo desde el volumen. Esas ubicaciones son `internal`: desde fuera devuelven `404`.

*Por qué importa al operar:* el backend nunca transmite el PDF (no se llena su memoria), y un archivo no se puede pedir por ruta. Si una descarga da `404` desde la API, mira primero que `web` monte `media_data` y que el archivo exista (§12.5).

---

## 7. Operación diaria y actualizaciones

### 7.1 Estado y logs

```bash
docker compose ps
docker compose logs --tail 100 backend
docker compose logs --tail 100 web
docker stats --no-stream                  # memoria y CPU frente a los límites
df -h /var/lib/docker /backups            # espacio en disco
docker compose exec backend du -sh /data/media
```

### 7.2 Detener, iniciar, reiniciar

```bash
docker compose stop          # detiene sin borrar nada
docker compose up -d         # inicia (o recrea lo que cambió)
docker compose restart web   # reinicia solo un servicio
```

**Nunca** uses `docker compose down -v`: `-v` **borra los volúmenes** (la base y todos los PDF).

### 7.3 Actualizar la aplicación

```bash
./scripts/backup.sh                       # 1. respaldo previo (permite volver atrás)
git fetch && git checkout <etiqueta-o-rama>
docker compose up -d --build              # 2. reconstruye; el backend migra solo
curl -ks https://localhost/api/health/    # 3. comprueba
./scripts/verify_integrity.sh             # 4. integridad intacta
```

**Volver atrás:** las migraciones solo avanzan. Si la versión nueva falla, `git checkout <versión-anterior>`, y restaura el respaldo del paso 1 (§9.2) para que la base coincida con el código.

### 7.4 Memoria

Los límites (`mem_limit`: 1 GB, 512 MB, 256 MB) salen de picos medidos de ~320, ~40 y ~100 MiB con 50 personas y cargas de 50 MB. Para ver si un contenedor llegó a su límite:

```bash
docker inspect -f '{{.Name}} OOMKilled={{.State.OOMKilled}} reinicios={{.RestartCount}}' \
  $(docker compose ps -q)
```

`OOMKilled=true` o reinicios que suben indican que el límite es corto para los datos reales: súbelo en `docker-compose.yml` y repite `./scripts/load_test.sh`.

---

## 8. Respaldos

### 8.1 Qué se respalda y cómo

```bash
./scripts/backup.sh
```

Crea `BACKUP_ROOT/<AAAAMMDDTHHMMSS>/` (modo `0700`) con:

| Archivo | Contenido |
|---|---|
| `database.dump` | PostgreSQL completo (`pg_dump -Fc`) |
| `media.tar.gz` | Todo `/data/media` |
| `SHA256SUMS` | Checksums de los dos anteriores |

Retiene `RETENTION_DAYS` (30) días y **siempre conserva el más reciente**. Si falla a medias, borra el directorio incompleto. Lo ejecuta el cron a las 02:15 (§10).

### 8.2 Comprobar que el último respaldo existe y es válido

```bash
ls -lt /backups | head -4
cd /backups/<el-más-reciente> && sha256sum --check --strict SHA256SUMS
```

Debe decir `La suma coincide` dos veces. Un respaldo que no se ha restaurado no cuenta como válido (§9.1).

### 8.3 Cifrar y sacar el respaldo del servidor (cumple Q5)

`backup.sh` **no cifra ni copia fuera**. Hazlo después de cada respaldo con una clave que **no** esté en el servidor de producción (guárdala en el gestor de secretos institucional):

```bash
# Cifrar el respaldo más reciente (la clave está en un archivo con permisos 0600)
respaldo=$(ls -1d /backups/*/ | sort | tail -1)
tar -C "$(dirname "$respaldo")" -cf - "$(basename "$respaldo")" \
  | openssl enc -aes-256-cbc -pbkdf2 -iter 600000 -salt -pass file:<ruta-de-la-clave> \
  -out <destino-externo>/$(basename "$respaldo").tar.enc
```

Para descifrar y comprobar:

```bash
openssl enc -d -aes-256-cbc -pbkdf2 -iter 600000 -pass file:<ruta-de-la-clave> \
  -in <destino-externo>/<AAAAMMDDTHHMMSS>.tar.enc | tar -C <directorio-vacío> -xf -
cd <directorio-vacío>/<AAAAMMDDTHHMMSS> && sha256sum --check --strict SHA256SUMS
```

*Por qué:* el respaldo contiene manuscritos inéditos y datos de las personas. Sin cifrar y sin copia externa, un robo o un fallo del disco del servidor se lleva datos y respaldos juntos. Se probó la ida y vuelta (checksums válidos tras descifrar); el **destino externo y su programación son pendiente en el servidor** (deuda D-30).

---

## 9. Restauración

### 9.1 Prueba (mensual, en un entorno aislado)

Un respaldo solo es válido si se ha restaurado. **No restaures sobre el sistema en producción para probar.** Hay dos formas:

**Automática (recomendada).** Hace respaldo → desastre → restauración sobre base vacía → compara todo → comprueba que detecta la manipulación:

```bash
./scripts/verify_pilot.sh        # ~6 min; pila "gpc_verify", no toca datos de producción
```

**Con un respaldo real**, en otra máquina o carpeta con el mismo código y `.env`:

```bash
./scripts/restore.sh --yes /ruta/al/respaldo/<AAAAMMDDTHHMMSS>
```

Debe terminar con `Restauración completada` y `Integridad correcta: sin discrepancias`. Anota el resultado en §14.

### 9.2 Restauración real (ante un desastre)

1. Si el servidor es nuevo: haz §4.1–§4.3 (código, `.env` con los **mismos** secretos, certificado) y levanta solo la base: `docker compose up -d db`.
2. Si hay cifrado, descifra el respaldo (§8.3) y comprueba `SHA256SUMS`.
3. Restaura:

```bash
./scripts/restore.sh /ruta/al/respaldo/<AAAAMMDDTHHMMSS>     # pide escribir SI
```

*Qué hace, en orden:* verifica los checksums (si no coinciden, **se niega sin tocar nada**) → detiene `web` y `backend` → `pg_restore --clean` → recrea el rol restringido de la aplicación y sus permisos (el volcado no los trae) → reemplaza `media_data` → normaliza permisos → ejecuta la verificación de integridad → levanta los servicios → `manage.py check`.

4. Comprueba: `docker compose ps`, `curl -ks https://localhost/api/health/`, `./scripts/verify_integrity.sh`, y entra con una cuenta de prueba.

**Lo que se pierde:** todo lo hecho entre el respaldo y el desastre (hasta 24 h). Avisa a las personas afectadas.

---

## 10. Tareas programadas (cron) y logs

### 10.1 Instalar

```bash
sudo cp scripts/cron/gpc.cron /etc/cron.d/gpc
sudo chown root:root /etc/cron.d/gpc && sudo chmod 0644 /etc/cron.d/gpc
sudo cp scripts/cron/gpc.logrotate /etc/logrotate.d/gpc
```

Si el repositorio no está en `/opt/gpc`, cambia la ruta en `/etc/cron.d/gpc`. Cada tarea lleva su propio `flock`, así que ninguna se solapa consigo misma.

| Tarea | Cuándo | Qué hace | Log |
|---|---|---|---|
| `backup.sh` | Diaria, 02:15 | Respaldo (§8) | `/var/log/gpc-backup.log` |
| `mark_expired_assignments` | Cada minuto | Marca como vencidas las asignaciones que superan sus 20 días; no revoca ni reasigna | `/var/log/gpc-expire.log` |
| `send_pending_notifications` | Cada minuto | Envía y reintenta los avisos por correo (1 min, 5 min, 15 min, 1 h, 4 h) | `/var/log/gpc-notify.log` |
| `cleanup_idempotency_keys` | Diaria, 03:00 | Borra claves de idempotencia vencidas | `/var/log/gpc-cleanup.log` |
| `verify_integrity` | Día 1, 03:30 | Recalcula los hashes de PDF y la cadena de auditoría; solo lee | `/var/log/gpc-integrity.log` |

Rotación (`gpc.logrotate`): semanal con 8 copias para los tres logs de ejecución frecuente; mensual con 12 copias para respaldo e integridad (son evidencia).

### 10.2 Comprobar que corre

```bash
grep CRON /var/log/syslog | grep gpc | tail     # (en algunas distribuciones: journalctl -u cron)
tail -5 /var/log/gpc-backup.log
tail -5 /var/log/gpc-integrity.log              # tras el día 1 debe decir "Integridad correcta"
sudo logrotate -d /etc/logrotate.d/gpc          # simula la rotación y muestra errores
```

*Pendiente en el servidor:* la instalación de estas dos plantillas no se pudo comprobar fuera de un servidor real. Comprueba el primer respaldo al día siguiente.

Cada comando se puede lanzar a mano (los cuatro se probaron y terminan con código 0):

```bash
docker compose exec backend python manage.py mark_expired_assignments
docker compose exec backend python manage.py send_pending_notifications
docker compose exec backend python manage.py cleanup_idempotency_keys
docker compose exec backend python manage.py verify_integrity
```

Los logs guardan conteos y códigos de error, **nunca** el contenido de los avisos, correos ni credenciales.

---

## 11. Credenciales institucionales

### 11.1 Qué credenciales existen

| Credencial | Dónde vive | Quién la usa |
|---|---|---|
| `POSTGRES_USER` / `POSTGRES_PASSWORD` | `.env` | Administrador de la base: migra, respalda y restaura |
| `APP_DB_USER` / `APP_DB_PASSWORD` | `.env` | La aplicación en ejecución (rol restringido) |
| `DJANGO_SECRET_KEY` | `.env` | Firma de sesiones y tokens |
| `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` | `.env` | Envío de correo institucional |
| Superusuario de soporte | Base de datos | Django Admin (`/admin/`) |
| Certificado TLS (`privkey.pem`) | `nginx/certs/` | Nginx |
| Clave de cifrado de respaldos | **Fuera del servidor** | Quien restaura |
| Cuentas de las personas | Base de datos | Autores, Revisores, Editores y Administradores |

Ninguna se versiona ni se escribe en esta guía. `.env` es `0600`; el certificado privado, `0600`.

### 11.2 Crear una cuenta institucional

Las cuentas las provisiona el soporte desde **Django Admin** (`https://<host>/admin/`), con el superusuario:

1. **Users → Añadir:** `institutional_id` (con el que la persona inicia sesión), `username`, correo y una contraseña inicial; indícale que la cambie.
2. **User roles → Añadir:** asigna el rol (`AUTHOR`, `REVIEWER`, `EDITOR` o `ADMIN`). Una persona puede tener varios y verá todos sus apartados.
3. Para un **Revisor**, crea además su **Reviewer profile** con las áreas de pericia y `is_available` activo; sin eso el Editor no puede asignarle.
4. Para dar de baja: desactiva la cuenta (`is_active`). No se borran cuentas: la auditoría las referencia.

El correo de la cuenta de un Autor debe coincidir con el del autor registrado en sus manuscritos.

### 11.3 Rotar credenciales

| Credencial | Procedimiento | Efecto |
|---|---|---|
| `APP_DB_PASSWORD` | Cambia el valor en `.env` y ejecuta `docker compose up -d --force-recreate backend` | El arranque reaplica la contraseña al rol. **Un reinicio simple no basta**: no relee `.env`. Hasta recrear, el backend responde con error |
| `POSTGRES_PASSWORD` | 1) `docker compose exec db psql -U <POSTGRES_USER> -d <POSTGRES_DB> -c "ALTER ROLE <POSTGRES_USER> PASSWORD '<nueva>'"`; 2) cambia `.env`; 3) `docker compose up -d --force-recreate backend` | Solo cambiar `.env` **no** cambia la contraseña de la base ya creada (el valor del contenedor se usa solo la primera vez) |
| `DJANGO_SECRET_KEY` | Cambia `.env` y recrea `backend` | Invalida las sesiones abiertas: todos deben iniciar sesión de nuevo |
| `EMAIL_HOST_PASSWORD` | Cambia `.env` y recrea `backend` | Los avisos fallidos entretanto se reintentan solos |
| Certificado | §5.1 | Sin corte |
| Superusuario | Admin → Users, o `docker compose exec backend python manage.py changepassword <usuario>` | — |

Tras cualquier rotación, comprueba `curl -ks https://localhost/api/health/` e inicia sesión.

> **Credencial publicada (D-01).** Hay un archivo de credenciales que estuvo versionado y **sigue en el historial de Git** (commit `ad22b2c`, presente en varias ramas remotas). Aunque ya no se versione, hay que tratarla como comprometida: **rótala en el sistema al que pertenece**. Reescribir el historial requiere `push --force` y la aprobación del responsable del repositorio; nadie debe hacerlo sin ella.

---

## 12. Incidentes

Regla general: **primero preserva, luego arregla**. Antes de tocar nada, anota la hora, copia los logs relevantes (`docker compose logs --since 1h > incidente.log`) y no borres volúmenes.

### 12.1 El sistema no responde o `backend` no queda `healthy`

```bash
docker compose ps
docker compose logs --tail 80 backend
```

| Lo que dice el log | Causa | Acción |
|---|---|---|
| `faltan variables obligatorias` o `contiene un valor de ejemplo` | `.env` incompleto | Corrige `.env`, `docker compose up -d` |
| `password authentication failed for user …` | Contraseña de `.env` distinta de la de la base | §11.3 |
| `permission denied` en `/data/media` | Permisos del volumen | `docker compose up -d --force-recreate backend` (reaplica permisos con `init_media.sh`) |
| `OOMKilled` | Memoria insuficiente | §7.4 |
| `web` reinicia en bucle y dice `cannot load certificate` | Falta o es inválido el certificado | §5.1 |

### 12.2 Los usuarios ven `502` o `504`

`502`: el backend no está sano (§12.1). `504`: el backend tarda más de 120 s; mira `docker stats` y `docker compose logs backend`. Con una carga lenta de PDF no debería ocurrir: Nginx la acumula en disco antes de pasarla.

### 12.3 La carga de un PDF falla

| Síntoma | Causa | Acción |
|---|---|---|
| `PDF_TOO_LARGE` | Supera 50 MB | Pedir que reduzca el archivo |
| `413` sin ese código | Supera 60 MB (lo rechaza Nginx) | Ídem |
| `PDF_INVALID` / `PDF_UNSUPPORTED` | No es un PDF válido, está cifrado o tiene contenido activo | Es el comportamiento esperado |
| `STORAGE_UNAVAILABLE` / `503` | Disco lleno o volumen no escribible | §12.4 |
| La conexión se corta a los ~2 min | Cliente demasiado lento (120 s sin enviar datos) | Reintentar con mejor conexión |

### 12.4 Disco lleno

```bash
df -h; docker system df; docker compose exec backend du -sh /data/media
```

Libera primero lo seguro: respaldos antiguos ya copiados fuera (`/backups`), imágenes sin usar (`docker image prune`), logs. **No borres nada dentro de `media_data` ni de `postgres_data`.** Si el crecimiento es normal, amplía el disco.

### 12.5 Un PDF no se descarga (`404` o archivo vacío)

Desde la API, un `404` puede ser legítimo (el recurso no es tuyo o no es público: la API no revela existencia). Si el recurso debería estar disponible:

```bash
./scripts/verify_integrity.sh                         # ¿falta o cambió algún archivo?
docker compose exec web ls /data/media/public/catalog | head   # ¿web ve el volumen?
```

Un `410` es normal: la copia pública del catálogo se retiró.

### 12.6 `verify_integrity` informa discrepancias

Significa que un PDF no coincide con su hash, o que la cadena de auditoría se rompió. **Puede ser una manipulación: no corrijas nada.**

1. Guarda la salida (`/var/log/gpc-integrity.log`) y avisa al responsable de la plataforma.
2. No reinicies ni restaures aún: conserva el estado como evidencia (haz un respaldo aparte con `./scripts/backup.sh`).
3. Identifica el archivo o evento citado y, con el responsable, decide si se restaura (§9.2) desde un respaldo anterior a la discrepancia.

### 12.7 Un respaldo falló o no se hizo

```bash
tail -30 /var/log/gpc-backup.log
```

Causas típicas: contenedores detenidos, disco de `BACKUP_ROOT` lleno, `BACKUP_ROOT` dentro del repositorio (el script lo prohíbe). Corrige y ejecuta `./scripts/backup.sh` a mano ese mismo día.

### 12.8 No llegan los correos

El **panel funciona igual** (los avisos son visibles ahí). Los correos fallidos se reintentan a 1 min, 5 min, 15 min, 1 h y 4 h; después quedan `FAILED` con su error. Comprueba `EMAIL_*` en `.env`, la conectividad con el SMTP y `/var/log/gpc-notify.log`. Al corregir, recrea `backend` (§11.3).

### 12.9 Una persona no puede iniciar sesión

- Tras **5 intentos fallidos en 15 minutos** la cuenta se bloquea (`429` con el tiempo de espera). **Se desbloquea sola** al pasar la ventana; no hay desbloqueo manual, y los intentos bloqueados no la alargan. Los intentos se ven (solo lectura) en Admin → Login attempts.
- Cuenta desactivada o sin rol: Admin → Users / User roles.
- Tras rotar `DJANGO_SECRET_KEY`, todos deben volver a iniciar sesión.

### 12.10 Error `503` / `AUDIT_UNAVAILABLE`

La auditoría es obligatoria: si no se puede registrar, la acción se revierte. Suele ser la base de datos (§12.1). No hay forma de saltarse la auditoría, y no debe buscarse.

### 12.11 Sospecha de fuga de identidad (doble ciego) o de credenciales

- **Fuga de identidad:** el flujo editorial tiene un reporte propio de incidente; el Editor lo gestiona en la aplicación. A nivel de sistema, preserva logs y auditoría (§12.6) y avisa al responsable.
- **Credencial expuesta:** rótala de inmediato (§11.3), revisa la auditoría de ese periodo y deja constancia.

### 12.12 El certificado venció

Los navegadores bloquean el acceso. Instala el nuevo (§5.1). Mientras tanto no hay alternativa por HTTP: el puerto 80 solo redirige.

---

## 13. Criterios de aceptación del piloto

El piloto se acepta cuando **todo** lo siguiente se cumple. «Hecho» indica la tarea que lo comprobó en un entorno de pruebas; «Pendiente en el servidor» exige repetirlo en el servidor real.

### 13.1 Operativos

| # | Criterio | Cómo se comprueba | Estado |
|---|---|---|---|
| 1 | Solo `web` publica puertos (80 y 443) | `docker compose ps`; `./scripts/verify_pilot.sh` | Hecho (TSK-87) |
| 2 | HTTPS con TLS 1.2/1.3, redirección 80→443 y las cinco cabeceras de seguridad | `./scripts/verify_pilot.sh` | Hecho con certificado autofirmado; **pendiente con el institucional** |
| 3 | `/_protected/`, `/_catalog/` y `/media/` no responden desde fuera | `./scripts/verify_pilot.sh`, `./scripts/smoke_media_isolation.sh` | Hecho (TSK-58, 87) |
| 4 | Carga de 50 MB exactos aceptada, 51 MB y 61 MB rechazadas, 50 personas concurrentes | `./scripts/load_test.sh --timeouts` (35/35) | Hecho (TSK-86); **pendiente en el servidor** |
| 5 | Memoria por debajo del 90 % del límite, sin `OOMKilled` | Misma prueba y `docker stats` | Hecho (TSK-86) |
| 6 | Restauración sobre base vacía idéntica al original (filas, archivos, auditoría) | `./scripts/verify_pilot.sh` | Hecho (TSK-87); **pendiente con un respaldo real** |
| 7 | `verify_integrity` sin discrepancias | `./scripts/verify_integrity.sh` | Hecho |
| 8 | Respaldo diario instalado, un respaldo reciente válido y **cifrado y copiado fuera** | §8.2, §8.3 | **Pendiente en el servidor** |
| 9 | Cron y logrotate instalados y ejecutándose | §10.2 | **Pendiente en el servidor** |
| 10 | Certificado institucional instalado y vigente | §5.2 | **Pendiente en el servidor** |
| 11 | Credencial publicada (D-01) rotada | §11.3 | **Pendiente** |
| 12 | `.env` con secretos únicos y permisos `0600` | `stat -c %a .env` → `600` | **Pendiente en el servidor** |
| 13 | Cuentas institucionales y Revisores con perfil creados | §11.2 | **Pendiente en el servidor** |
| 14 | `./scripts/check_runbook.py` termina sin fallos | En el CI | Hecho (TSK-88) |

### 13.2 Funcionales (criterios de éxito SC-01 a SC-15 de la especificación)

Los comprueban las pruebas automáticas del repositorio (1580 de backend y 1302 de frontend en verde en la última corrida completa); varios exigen además revisión de personas:

| Criterio | Automatizado | Requiere personas |
|---|---|---|
| SC-03 archivos inválidos rechazados · SC-05 doble ciego en todos los canales · SC-06 un solo Revisor activo · SC-07 vencimiento a los 20 días · SC-08 veredicto con evaluación · SC-09 sin sobrescrituras · SC-10 auditoría inmutable · SC-13 contador de rondas · SC-14 avisos sin fugas · SC-15 acceso no autorizado denegado | ✅ pruebas del backend | Revisión de muestra en el piloto |
| SC-04 el aceptado aparece en el catálogo en ≤ 5 min | ✅ | Muestreo tras cada veredicto |
| SC-11 búsquedas del catálogo < 2 s con 50 personas | ✅ `load_test.sh` (p95 0,32 s) | Repetir en el servidor |
| SC-01 panel unificado sin elegir rol · SC-02 envío en < 10 min · SC-12 evaluación en < 15 min | Parcial (pruebas de interfaz) | **Prueba de usabilidad con personas reales** |

### 13.3 Qué NO prueba este piloto todavía

El recorrido manual completo en navegador (Playwright, TSK-91), la accesibilidad (TSK-92) y la auditoría de seguridad e IDOR (TSK-89) son tareas posteriores; el piloto con usuarios reales debe esperar a que se cierren o aceptar el riesgo por escrito.

---

## 14. Anexo: registro de la prueba mensual de restauración

Copia esta tabla a la bitácora del equipo y complétala cada mes (§9.1):

| Fecha | Responsable | Respaldo usado | Método (`verify_pilot.sh` / respaldo real) | Resultado (`61/61` / `Integridad correcta`) | Observaciones |
|---|---|---|---|---|---|
| | | | | | |
