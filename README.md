# Sistema de Gestión de Publicaciones Científicas

Sistema cliente-servidor para gestionar el ciclo editorial de publicaciones científicas: registro de manuscritos, revisión por pares bajo doble ciego, veredictos editoriales, catálogo público y auditoría.

El proyecto sigue una arquitectura SPA + API REST:

- **Frontend:** Angular 17+ con TypeScript.
- **Backend:** Python 3.12, Django 5.2 LTS y Django REST Framework.
- **Base de datos:** PostgreSQL 16.
- **Servidor web:** Nginx 1.27.
- **Servidor de aplicación:** Gunicorn.
- **Contenedores:** Docker y Docker Compose.
- **Almacenamiento:** volumen Docker `media_data`.

No se usa MySQL, SQLite ni otro motor de base de datos. El entorno completo se ejecuta con Docker Compose.

---

## 1. Requisitos previos

- Git.
- Docker Engine con Docker Compose v2.
- Al menos 4 vCPU, 8 GB de RAM y 200 GB de disco SSD para el piloto.
- Certificado TLS institucional para producción.
- Credenciales institucionales de PostgreSQL y SMTP.

---

## 2. Estructura del proyecto

```text
Gestion_Publicaciones_Cientificas/
├── backend/
│   ├── manage.py
│   ├── config/
│   │   ├── settings/
│   │   │   ├── base.py
│   │   │   ├── development.py
│   │   │   └── production.py
│   │   ├── urls.py
│   │   ├── api.py
│   │   ├── asgi.py
│   │   └── wsgi.py
│   ├── apps/
│   ├── requirements/
│   │   ├── base.txt
│   │   ├── development.txt
│   │   └── production.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   └── Dockerfile
├── nginx/
│   ├── nginx.conf
│   ├── conf.d/
│   │   └── default.conf
│   └── certs/
├── scripts/
│   ├── backup.sh
│   ├── restore.sh
│   ├── verify_integrity.sh
│   ├── init_media.sh
│   ├── check_env.sh
│   └── cron/
│       └── gpc.cron
├── .github/workflows/
│   └── ci.yml
├── docker-compose.yml
├── .env.example
└── README.md
```

El directorio `frontend/` está reservado para la SPA Angular. Su proyecto base se crea en la tarea `TSK-13`.

---

## 3. Instalación en un entorno limpio

Ejecuta todos los comandos desde la raíz del repositorio.

### 3.1 Clonar el repositorio

```bash
git clone https://github.com/RichardC022/Gestion_Publicaciones_Cientificas.git
cd Gestion_Publicaciones_Cientificas
```

### 3.2 Crear el archivo de entorno

Copia el ejemplo y ajusta los valores reales:

```bash
cp .env.example .env
chmod 600 .env
```

Edita `.env` y cambia al menos:

- `DJANGO_SECRET_KEY`
- `POSTGRES_PASSWORD`
- `APP_DB_PASSWORD`
- `EMAIL_HOST_PASSWORD`
- `ALLOWED_HOSTS`
- `CSRF_TRUSTED_ORIGINS`
- `EMAIL_HOST`
- `EMAIL_HOST_USER`
- `DEFAULT_FROM_EMAIL`

No uses los valores de ejemplo `change-me` en producción.

> **Seguridad de sesión (TSK-16).** El refresh token viaja siempre en una
> cookie `HttpOnly` con `SameSite=Strict` (JavaScript no puede leerla) y el
> access token vive solo en memoria del navegador: nunca se guarda en
> `localStorage` ni en cookies. `COOKIE_SECURE=1` mantiene el atributo
> `Secure` en producción, de modo que la cookie solo circula por HTTPS tras
> el TLS de Nginx. Los tiempos de vida llegan de `JWT_ACCESS_MINUTES=15`,
> `JWT_REFRESH_DAYS=7` y `SESSION_IDLE_MINUTES=30`.

**Los valores de producción son distintos de los de desarrollo.** El archivo
`.env` describe un entorno de producción (`DJANGO_SETTINGS_MODULE=config.settings.production`,
`DEBUG=0`, hosts y orígenes CSRF reales, SMTP institucional y `COOKIE_SECURE=1`).
Para un entorno de desarrollo local usa `DJANGO_SETTINGS_MODULE=config.settings.development`,
`DEBUG=1`, `ALLOWED_HOSTS=localhost,127.0.0.1`, `CSRF_TRUSTED_ORIGINS=https://localhost`
(Nginx solo sirve por HTTPS y el puerto 80 redirige), correo por consola (ya
configurado en `config.settings.development`) y `COOKIE_SECURE=1` con el
certificado autofirmado de la sección 7. Nunca reutilices secretos de producción en desarrollo.

### 3.3 Validar la configuración

```bash
docker compose config --quiet
```

Si el comando termina sin errores, la configuración de Compose es válida.

### 3.4 Construir las imágenes

```bash
docker compose build
```

### 3.5 Levantar la base de datos

```bash
docker compose up -d db
```

Espera a que el servicio esté saludable:

```bash
docker compose ps db
```

### 3.6 Aplicar migraciones

```bash
docker compose run --rm -e DB_USE_ADMIN=1 backend python manage.py migrate --noinput
docker compose run --rm -e DB_USE_ADMIN=1 backend python manage.py apply_db_privileges
```

`DB_USE_ADMIN=1` hace que el comando use el administrador de la base (`POSTGRES_USER`) en lugar del rol de aplicación (§3.6.1). El contenedor `backend` ya ejecuta ambos pasos al arrancar.

Las migraciones se aplican sobre PostgreSQL 16. No existe ningún paso de MySQL y no se admiten bases SQLite en ejecución.


### 3.6.1 Privilegios de base de datos (TSK-72)

Hay dos usuarios de PostgreSQL con funciones distintas:

| Variable | Rol | Qué puede hacer |
|---|---|---|
| `POSTGRES_USER` (`gpc_app`) | Administrador y dueño del esquema | Migrar, respaldar y restaurar. Superusuario del contenedor `db`; **no lo usa la aplicación** en ejecución. |
| `APP_DB_USER` (`gpc_runtime`) | Rol de aplicación | `SELECT`/`INSERT`/`UPDATE`/`DELETE` en las tablas operativas; en `audit_audit_log` solo `SELECT` e `INSERT`. Sin superusuario, sin `CREATEDB`, sin `CREATE` en el esquema. |

El rol de aplicación no puede alterar ni borrar la auditoría aunque alguien intente deshabilitar el trigger (un superusuario ignoraría `GRANT`/`REVOKE`, por eso la aplicación no se conecta como tal). `apply_db_privileges` es idempotente y el contenedor `backend` lo ejecuta después de cada `migrate`: sirve para una base nueva, una existente y una restaurada (los respaldos se toman con `--no-privileges`, así que los permisos se reaplican en el arranque).

Para una base ya existente basta con añadir `APP_DB_USER` y `APP_DB_PASSWORD` al `.env` (distintos de `POSTGRES_USER` y sin `change-me`) y reiniciar `backend`. Para comprobarlo, el backend corre con el rol de aplicación, así que un `DELETE` sobre la auditoría debe fallar:

```bash
docker compose exec backend python manage.py shell -c \
  "from django.db import connection; connection.cursor().execute('DELETE FROM audit_audit_log')"
```

Debe terminar con `permission denied for table audit_audit_log`.

### 3.7 Sembrar los roles institucionales

El flujo funcional usa cuatro roles:

- `AUTHOR`
- `REVIEWER`
- `EDITOR`
- `ADMIN`

El comando de inicialización es:

```bash
docker compose run --rm backend python manage.py seed_roles
```

Este comando es idempotente y forma parte de la Fase 1 del plan. Cuando se ejecuta en una base vacía, crea exactamente los cuatro roles; si ya existen, no duplica registros.

> **Nota de fase:** `seed_roles` se implementa junto con los modelos de identidad en `TSK-17`. En la fase de cimientos puede devolver `Unknown command`; hasta esa tarea, el aprovisionamiento operativo puede realizarse temporalmente desde Django Admin.

### 3.8 Crear el superusuario operativo

```bash
docker compose run --rm backend python manage.py createsuperuser
```

El superusuario es solo para soporte operativo y Django Admin. No reemplaza el flujo editorial de la API ni la SPA.

### 3.9 Levantar el sistema completo

Nginx exige un certificado desde que sirve HTTPS (sección 7). Si no tienes el institucional, crea uno autofirmado (no sobrescribe uno existente):

```bash
./scripts/make_dev_cert.sh
docker compose up -d
```

La aplicación queda en `https://localhost` (el puerto 80 redirige a 443; el navegador avisará del certificado autofirmado). **Solo `web` publica puertos (80 y 443)**: PostgreSQL y el backend no son alcanzables desde fuera. Si necesitas PostgreSQL o Adminer en desarrollo, hay un compose aparte que los liga a `127.0.0.1`:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d
# PostgreSQL en 127.0.0.1:5432 · Adminer en http://127.0.0.1:8888 (servidor «db»)
```

No uses `docker-compose.dev.yml` en el servidor del piloto.

El backend ejecuta automáticamente:

1. Validación de variables obligatorias.
2. Inicialización del volumen `media_data`.
3. Migraciones.
4. Recolección de archivos estáticos.
5. Gunicorn en `0.0.0.0:8000`.

### 3.10 Verificar el despliegue

Revisa el estado de los servicios:

```bash
docker compose ps
```

Verifica la configuración de Django:

```bash
docker compose exec backend python manage.py check
```

Inspecciona los logs del backend:

```bash
docker compose logs backend
```

El endpoint de salud `/api/health/` forma parte de la tarea `TSK-12`. Hasta que esa tarea se implemente, usa `manage.py check` y `docker compose ps` como verificación operativa de la fase de cimientos.

---

## 4. Carga de prueba

Para una prueba inicial de la infraestructura:

1. Verifica que el volumen esté inicializado:

   ```bash
   docker compose exec backend find /data/media -maxdepth 2 -type d
   ```

2. Verifica que el backend pueda escribir y Nginx solo leer:

   ```bash
   docker compose exec backend sh -c 'umask 0027; printf test > /data/media/tmp/uploads/smoke.txt'
   docker compose exec -u 101:101 web sh -c 'cat /data/media/tmp/uploads/smoke.txt'
   docker compose exec backend rm /data/media/tmp/uploads/smoke.txt
   ```

3. Valida que los archivos estáticos estén disponibles:

   ```bash
   docker compose exec backend find /app/staticfiles -maxdepth 2 -type f | head
   ```

Cuando se implemente el flujo de autor, la carga funcional de un PDF de prueba se realizará con un archivo de máximo **50 MB**. Nginx admite cuerpos de hasta **60 MB**, pero Django rechaza archivos que superen 50 MB.

---

## 5. Operación diaria

### 5.1 Servicios

```bash
docker compose ps
docker compose logs -f
docker compose logs -f backend
docker compose logs -f db
docker compose logs -f web
```

### 5.2 Iniciar y detener

```bash
docker compose up -d
docker compose stop
docker compose down
```

### 5.3 Acceso a los contenedores

```bash
docker compose exec backend bash
docker compose exec db sh
docker compose exec web sh
```

### 5.4 Migraciones

Generar migraciones durante el desarrollo:

```bash
docker compose exec backend python manage.py makemigrations
```

Aplicar migraciones:

```bash
docker compose exec -e DB_USE_ADMIN=1 backend python manage.py migrate --noinput
```

### 5.5 Archivos estáticos

```bash
docker compose exec backend python manage.py collectstatic --noinput
```

### 5.6 Django Admin

Django Admin queda disponible para soporte operativo en:

```text
https://<host>/admin/
```

No es la interfaz del flujo editorial. El flujo funcional se expone por `/api/` y se consume desde Angular.

---

## 6. Volumen y almacenamiento

El volumen `media_data` está montado:

- En el backend: `/data/media` con lectura y escritura.
- En Nginx: `/data/media` en modo solo lectura.

Estructura esperada:

```text
/data/media/
├── private/
│   ├── drafts/
│   └── manuscripts/
├── public/
│   └── catalog/
└── tmp/
    └── uploads/
```

Reglas operativas:

- Directorios: `0750`.
- Archivos: `0640`.
- Grupo compartido: `media`.
- El backend crea archivos con `umask 0027`.
- Nginx nunca escribe en el volumen.
- `/data/media` no se publica como directorio estático.
- Los PDF internos se entregan mediante `X-Accel-Redirect` y ubicaciones `internal`.

El script `scripts/init_media.sh` crea y normaliza la estructura. Se ejecuta automáticamente al iniciar el backend.

---

## 7. TLS y Nginx

`web` es el único servicio que publica puertos: **80**, que solo responde `301` hacia `https://`, y **443**, que sirve la SPA, la API y las descargas con TLS 1.2 y 1.3 (`ssl_protocols TLSv1.2 TLSv1.3`). Nginx no arranca sin certificado.

Coloca el certificado institucional en:

```text
nginx/certs/fullchain.pem
nginx/certs/privkey.pem
```

Para un piloto local sin certificado institucional, genera uno autofirmado (el script no sobrescribe uno existente); el navegador mostrará una advertencia:

```bash
./scripts/make_dev_cert.sh
```

Requisitos que cumple la configuración:

- TLS 1.2 y TLS 1.3; TLS 1.0 y 1.1 se rechazan.
- Redirección de HTTP a HTTPS conservando ruta y consulta.
- `server_tokens off` (la cabecera `Server` no revela la versión).
- Cabeceras de seguridad en **todas** las respuestas (SPA, API, errores y PDF): `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy` y `Content-Security-Policy`. Para `/api/`, Nginx oculta las tres que Django también emite para que no lleguen repetidas.
- HSTS: Nginx **no** lo añade (con un certificado autofirmado dejaría al navegador sin acceso, D-06); Django lo emite en las respuestas de la API cuando la conexión es segura. Antes de abrir el piloto a usuarios reales, con el certificado institucional, valora retirar `preload`.

Los `.pem` no se versionan. Verificación automatizada: sección 10.5.

---

## 8. Respaldo y restauración

La documentación detallada está en:

```text
scripts/BACKUP.md
```

### 8.1 Respaldo manual

```bash
./scripts/backup.sh
```

El respaldo genera:

- `database.dump`
- `media.tar.gz`
- `SHA256SUMS`

La ruta por defecto es `/backups` y la retención es de 30 días. Puedes cambiarla en `.env`:

```dotenv
BACKUP_ROOT=/backups
RETENTION_DAYS=30
```

### 8.2 Programación diaria

Instala la plantilla de cron:

```bash
sudo cp scripts/cron/gpc.cron /etc/cron.d/gpc
sudo chown root:root /etc/cron.d/gpc
sudo chmod 0644 /etc/cron.d/gpc
```

Ajusta la ruta del repositorio en el archivo si no está en `/opt/gpc`.

La plantilla incluye también la expiración de asignaciones (TSK-45 y TSK-49): cada minuto ejecuta `mark_expired_assignments`, que marca como `EXPIRED` las asignaciones `ACTIVE` con `due_at <= now()`, sin revocar ni reasignar, y escribe en `/var/log/gpc-expire.log` solo cuando hubo trabajo o un error. El contenedor `backend` debe estar en ejecución. Para probarla a mano:

```bash
docker compose exec backend python manage.py mark_expired_assignments
```

La plantilla incluye además las tareas de la Fase 5 (TSK-71 y TSK-76), todas dentro del contenedor `backend` y con un `flock` propio cada una:

| Tarea | Comando | Frecuencia | Log |
|---|---|---|---|
| Avisos por correo | `send_pending_notifications` | Cada minuto | `/var/log/gpc-notify.log` |
| Limpieza de idempotencia | `cleanup_idempotency_keys` | Diaria, 03:00 | `/var/log/gpc-cleanup.log` |
| Verificación de integridad | `verify_integrity` | Día 1 de cada mes, 03:30 | `/var/log/gpc-integrity.log` |

- **Reintentos de avisos:** un aviso de correo fallido queda en `FAILED` y se reintenta tras 1 min, 5 min, 15 min, 1 h y 4 h; tras el sexto intento fallido deja de reintentarse y permanece `FAILED` con su `last_error`. Un aviso `SENT` no se reenvía y el aviso del panel no depende del correo. `EMAIL_TIMEOUT` (10 s por defecto) limita la espera al SMTP.
- **Limpieza:** solo elimina las claves con `expires_at` vencido (24 h tras guardarse); las vigentes no se tocan.
- **Verificación:** solo lee. Si encuentra discrepancias de hash en PDFs o en la cadena de auditoría las lista en el log y termina con código distinto de cero; no corrige nada.
- Los logs registran conteos y códigos de error, nunca el contenido de los avisos, correos ni credenciales.

Para probarlas a mano:

```bash
docker compose exec backend python manage.py send_pending_notifications
docker compose exec backend python manage.py cleanup_idempotency_keys
docker compose exec backend python manage.py verify_integrity
```

### 8.3 Restauración

```bash
./scripts/restore.sh /backups/<timestamp>
```

Para pruebas automatizadas:

```bash
./scripts/restore.sh --yes /backups/<timestamp>
```

La restauración:

1. Verifica los checksums.
2. Detiene `web` y `backend`.
3. Restaura PostgreSQL.
4. Recrea el rol de ejecución de la aplicación y sus privilegios (`apply_db_privileges`): el volcado se toma con `--no-privileges`, así que en una base nueva ese rol no existe y, sin este paso, ni `verify_integrity` ni el backend podrían conectarse.
5. Restaura el volumen `media_data`.
6. Normaliza permisos.
7. Ejecuta la verificación de integridad.
8. Levanta los servicios.
9. Ejecuta `manage.py check`.

> **Nota:** la restauración sobre una base **vacía** (recuperación ante desastre) se comprueba de extremo a extremo con `./scripts/verify_pilot.sh` (sección 10.5).

### 8.4 Prueba mensual

Un respaldo solo se considera válido cuando se restaura en un entorno aislado y pasa la verificación. Registra:

- Fecha de la prueba.
- Responsable.
- Respaldo utilizado.
- Resultado.

---

## 9. Integración continua

El pipeline está en:

```text
.github/workflows/ci.yml
```

Jobs incluidos:

- Django system check.
- Backend tests sobre PostgreSQL 16, sin tolerar «ninguna prueba recolectada». Antes de las pruebas verifica que el motor sea PostgreSQL y que no haya migraciones pendientes (`makemigrations --check`). Mide cobertura y **falla si el dominio (servicios) y los permisos bajan del 80 %** (`COVERAGE_MIN`); la configuración está en `backend/.coveragerc`.
- Auditoría de dependencias del backend (`pip-audit` sobre `requirements/production.txt` y `development.txt`). Falla con cualquier vulnerabilidad conocida: la herramienta no clasifica por severidad. Una excepción justificada se documenta con `--ignore-vuln`.
- Angular: comprobación de tipos (`tsc` de la aplicación y de los specs) y `ng test --watch=false`.
- Angular production build.
- Auditoría de dependencias del frontend: `npm audit --omit=dev --audit-level=high` falla con críticas o altas; las herramientas de desarrollo se auditan solo de forma informativa.
- Docker Compose validation y verificación de que `.env` y `credentials.txt` no están versionados.
- Aislamiento del volumen de archivos (`scripts/smoke_media_isolation.sh`).

Artefactos disponibles en cada ejecución (14 días): `backend-coverage` (`coverage.xml` y `htmlcov/`) y `frontend-dist` (el build de producción).

El pipeline usa PostgreSQL, nunca SQLite, y no consume secretos de producción.

Para medir la cobertura en local:

```bash
docker compose run --rm --no-deps -v "$PWD/backend:/app" backend sh -c "python -m pip install --quiet --user -r requirements/development.txt; python -m pytest -q -p no:cacheprovider --cov --cov-report=term:skip-covered"
```

---

## 10. Pruebas locales

### 10.1 Backend

Las dependencias de desarrollo están en:

```text
backend/requirements/development.txt
```

Para ejecutar pruebas desde un entorno de desarrollo:

```bash
docker compose run --rm backend sh -c "python -m pip install --user --requirement requirements/development.txt && python -m pytest"
```

### 10.2 Compose

```bash
docker compose config --quiet
```

### 10.3 Nginx

Verifica que las rutas internas no sean accesibles directamente:

```bash
curl -kI https://127.0.0.1/media/
curl -kI https://127.0.0.1/_protected/
curl -kI https://127.0.0.1/_catalog/
```

Las respuestas esperadas son de denegación o recurso no disponible, no la entrega de archivos.

La **prueba de humo completa** del aislamiento del volumen es un script que no necesita la base de datos ni el stack en ejecución:

```bash
./scripts/smoke_media_isolation.sh
```

Levanta, de forma efímera, Nginx con la configuración real (`nginx/conf.d/default.conf`, con un certificado autofirmado que genera para la prueba), el volumen en solo lectura y un backend de prueba que responde con `X-Accel-Redirect`, y comprueba que:

- desde fuera, `/_protected/`, `/_catalog/` y `/media/` no entregan archivos (tampoco con rutas codificadas, dobles barras o `..`) ni listan directorios;
- cuando el backend autoriza, Nginx sí entrega el PDF con `Cache-Control` y `nosniff` (control positivo);
- una redirección interna a `/media/` también se deniega;
- Nginx no puede escribir en el volumen y, en `docker-compose.yml`, solo `backend` lo monta con escritura.

Requiere Docker, `curl` y `python3`; termina con código distinto de cero si algo falla y limpia sus contenedores y su volumen.

### 10.4 Prueba de carga (50 MB y 50 personas concurrentes)

```bash
./scripts/load_test.sh              # ~6 min
./scripts/load_test.sh --timeouts   # añade el corte por inactividad de 120 s (~+2 min)
```

Levanta un **stack aislado** (`docker compose -p gpc_load -f docker-compose.yml -f docker-compose.load.yml`, HTTPS en `LOAD_TLS_PORT` —18443 por defecto— y HTTP en `LOAD_WEB_PORT` —18080—, con sus propios volúmenes), siembra cuentas con una contraseña aleatoria que no se guarda, ejecuta `scripts/load/load_test.py` por el puerto público de Nginx y lo apaga al terminar (`LOAD_KEEP=1` lo conserva). La base y los PDF de trabajo no se tocan. Todo pasa por la API real (autor, editor, revisor), no por atajos en la base.

Comprueba, y falla con código distinto de cero si algo no se cumple:

- la configuración efectiva de Nginx (`client_max_body_size 60m`, timeouts de 120 s, `proxy_request_buffering on`) y de Gunicorn (`--timeout 120`, 3 workers);
- 50 logins simultáneos, y 50 personas × 6 consultas al catálogo con p95 < 2 s (SC-11);
- 50 descargas simultáneas del PDF grande del catálogo (`X-Accel-Redirect`) y 5 sanitizadas del revisor;
- 5 cargas simultáneas de PDF de ~50 MB, un PDF de exactamente 50 MB (201), uno de 51 MB (413 `PDF_TOO_LARGE` de Django) y un cuerpo de 61 MB que **Nginx** rechaza con 413 sin que llegue a Gunicorn;
- que una carga lenta se acumula en el buffer en disco de Nginx (se mide por el archivo temporal abierto) y que seis clientes lentos (el doble de workers) no impiden que `/api/health/` responda;
- con `--timeouts`, que Nginx corta a los ~120 s un cuerpo detenido;
- la memoria de cada contenedor durante toda la corrida: pico por debajo del 90 % de su límite, sin `OOMKilled` ni reinicios.

Los límites de memoria viven en `docker-compose.yml` (`mem_limit`: backend 1 GB, db 512 MB, web 256 MB) y salen de los picos medidos (≈ 320, 40 y 100 MiB). Requiere Docker, `openssl` y `python3`. Se ejecuta a mano (no está en CI: construye imágenes y dura minutos) cuando cambian Nginx, Gunicorn, los límites de memoria o la carga de PDF.

### 10.5 Restauración, integridad y superficie expuesta (TSK-87)

```bash
./scripts/verify_pilot.sh           # ~6 min
```

Igual que la prueba de carga, usa un **stack aislado** (`gpc_verify`, HTTPS en `VERIFY_TLS_PORT`, 19443 por defecto; HTTP en 19080), contraseñas aleatorias y se apaga al terminar (`VERIFY_KEEP=1` lo conserva). No toca la base ni los PDF de trabajo. Siembra artículos aceptados por la API real y comprueba, con código de salida distinto de cero si algo falla:

- **Restauración:** `backup.sh` produce `database.dump`, `media.tar.gz` y `SHA256SUMS` (permisos `0600/0700`); un respaldo alterado lo rechaza `restore.sh` **sin tocar la base**; se borran los volúmenes y `restore.sh` reconstruye todo sobre una base vacía. La huella del estado (filas de cada modelo, SHA-256 de cada archivo y último hash de la cadena de auditoría) es idéntica a la de antes del desastre, las cuentas inician sesión con su contraseña y el catálogo entrega por Nginx los mismos PDF.
- **Integridad:** `verify_integrity` pasa tras restaurar, detecta un PDF alterado (sale distinto de cero) y volver a restaurar lo repara.
- **Puertos:** el compose base solo tiene `db`, `backend` y `web`; solo `web` publica y solo 80 y 443; `backend_net` es interna; el compose de desarrollo liga PostgreSQL y Adminer a `127.0.0.1`. El CI repite la comprobación estática.
- **Ubicaciones internas:** `/_protected/`, `/_catalog/` y `/media/` no entregan archivos reales del volumen restaurado (tampoco con `//`, `%5F`, `..` ni `%2e%2e`), un `X-Accel-Redirect` enviado por el cliente se ignora y por HTTP plano solo hay redirección. Control positivo: lo autorizado sí se entrega.
- **TLS y cabeceras:** redirección `301` a HTTPS con ruta y consulta, TLS 1.2 y 1.3 se negocian y 1.0/1.1 se rechazan, el certificado servido es el de `nginx/certs/` y no está por vencer, la cookie del refresh es `Secure; HttpOnly; SameSite`, la API envía HSTS, `Server` no revela versión y las cinco cabeceras de seguridad están (una sola vez) en SPA, API, errores 401/404/403 y PDF.

Requiere Docker, `openssl` y `python3`. Hay que repetirla en el servidor del piloto con el certificado institucional y antes de cada cambio de Nginx, del compose o de los scripts de respaldo.

---

## 11. Seguridad

- PostgreSQL no publica puertos al host.
- Solo el servicio `web` expone el puerto `80`.
- El backend ejecuta con el usuario no root `app`.
- `.env` debe tener permisos `0600`.
- No se versionan secretos reales.
- No se usa MySQL ni SQLite como motor de ejecución.
- El PDF máximo funcional es de 50 MB.
- Nginx limita el cuerpo de la solicitud a 60 MB.
- Los respaldos se guardan con permisos `0700`.
- El volumen de medios nunca se sirve como directorio público.

---

## 12. Estado del proyecto

Este repositorio está en **Fase 0: Fundación**.

Ya está implementada la base de:

- Estructura `/backend` y `/frontend`.
- PostgreSQL 16.
- Docker Compose.
- Nginx.
- Volumen `media_data`.
- Respaldo y restauración.
- Pipeline de integración continua.
- Documentación operativa inicial.

Las fases siguientes agregan:

- Apps de dominio y salud del backend.
- Autenticación institucional.
- Panel unificado.
- Manuscritos, evaluaciones, veredictos y catálogo.
- Endurecimiento y prueba de carga.

---

## 13. Metodología y ramas

El proyecto usa Specification-Driven Development con los artefactos en `.spec-kit/`.

Estrategia de ramas:

- `main`: producción.
- `develop`: integración principal.
- `dev/<integrante>-setup`: ramas de trabajo por integrante.

Los commits y la documentación operativa están en español. El código fuente y los nombres técnicos están en inglés.
