# Sistema de Gestión de Publicaciones Científicas

Sistema cliente-servidor para gestionar el ciclo editorial de publicaciones científicas: registro de manuscritos, revisión por pares bajo doble ciego, veredictos editoriales, catálogo público y auditoría.

El proyecto sigue una arquitectura SPA + API REST:

- **Frontend:** Angular 22 con TypeScript.
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
│   ├── tests/
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
├── .env.development.example
└── README.md
```

El directorio `frontend/` contiene la SPA Angular y su `Dockerfile` multi-stage.

---

## 3. Instalación en un entorno limpio

Ejecuta todos los comandos desde la raíz del repositorio.

### 3.1 Clonar el repositorio

```bash
git clone https://github.com/RichardC022/Gestion_Publicaciones_Cientificas.git
cd Gestion_Publicaciones_Cientificas
```

### 3.2 Crear el archivo de entorno

Para desarrollo local, parte de la plantilla de desarrollo (sin TLS ni SMTP
reales). Si ya existe un `.env`, no lo sobrescribas:

```bash
cp .env.development.example .env
chmod 600 .env
```

Para un despliegue real, parte de `.env.example` y ajusta los valores:

```bash
cp .env.example .env
chmod 600 .env
```

Si usas `.env.example` (despliegue real), edita `.env` y cambia al menos:

- `DJANGO_SECRET_KEY`
- `POSTGRES_PASSWORD`
- `EMAIL_HOST_PASSWORD`
- `ALLOWED_HOSTS`
- `CSRF_TRUSTED_ORIGINS`
- `EMAIL_HOST`
- `EMAIL_HOST_USER`
- `DEFAULT_FROM_EMAIL`

No uses los valores de ejemplo `change-me` en producción. La plantilla
`.env.development.example` ya trae valores locales funcionales.

> **Contraseña de PostgreSQL:** `POSTGRES_PASSWORD` solo se aplica al crear el
> volumen `postgres_data` por primera vez. Si el volumen ya existe y cambias la
> contraseña en `.env`, el backend fallará con `password authentication failed`.
> Actualiza la contraseña dentro de PostgreSQL o recrea la base con
> `docker compose down -v` (esto borra los datos).

> **Seguridad de sesión (TSK-16).** El refresh token viaja siempre en una
> cookie `HttpOnly` con `SameSite=Strict` (JavaScript no puede leerla) y el
> access token vive solo en memoria del navegador: nunca se guarda en
> `localStorage` ni en cookies. `COOKIE_SECURE=1` mantiene el atributo
> `Secure` en producción, de modo que la cookie solo circula por HTTPS tras
> el TLS de Nginx. Los tiempos de vida llegan de `JWT_ACCESS_MINUTES=15`,
> `JWT_REFRESH_DAYS=7` y `SESSION_IDLE_MINUTES=30`.

**Los valores de producción son distintos de los de desarrollo.**
`.env.example` describe un entorno de producción (`DJANGO_SETTINGS_MODULE=config.settings.production`,
`DEBUG=0`, hosts y orígenes CSRF reales, SMTP institucional y `COOKIE_SECURE=1`).
`.env.development.example` describe desarrollo local (`DJANGO_SETTINGS_MODULE=config.settings.development`,
`DEBUG=1`, `ALLOWED_HOSTS=localhost,127.0.0.1`, `CSRF_TRUSTED_ORIGINS=http://localhost`,
correo por consola y `COOKIE_SECURE=0`). Nunca reutilices secretos de producción en desarrollo.

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
docker compose run --rm backend python manage.py migrate --noinput
```

Las migraciones se aplican sobre PostgreSQL 16. No existe ningún paso de MySQL y no se admiten bases SQLite en ejecución.

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

El comando crea `AUTHOR`, `REVIEWER`, `EDITOR` y `ADMIN` si no existen y puede ejecutarse de nuevo sin duplicarlos.

### 3.8 Crear el superusuario operativo

```bash
docker compose run --rm backend python manage.py createsuperuser
```

El superusuario es solo para soporte operativo y Django Admin. No reemplaza el flujo editorial de la API ni la SPA.

### 3.9 Levantar el sistema completo

```bash
docker compose up -d
```

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

Comprueba también el endpoint de salud, que debe responder `200`:

```bash
curl -i http://localhost/api/health/
```

### 3.11 URLs de acceso

Con el stack levantado (`docker compose up -d`), las URLs locales son:

| Componente | URL local | Notas |
|---|---|---|
| Web / SPA (Nginx) | http://localhost/ | Entrada principal; redirige a `/catalog`. |
| Catálogo público | http://localhost/catalog | No requiere sesión. |
| Iniciar sesión | http://localhost/login | Acepta email, usuario o ID institucional. |
| Panel interno | http://localhost/app/dashboard | Requiere sesión y rol activo. |
| Django Admin | http://localhost/admin/ | Requiere superusuario. |
| API REST | http://localhost/api/ | Base de la API. |
| Salud del backend | http://localhost/api/health/ | Debe responder `200` con `{"status":"ok"}`. |

Solo se publica el puerto `80` (Nginx). El backend (`backend:8000`) y PostgreSQL (`db:5432`) no tienen puerto publicado al host: se accede a ellos a través de Nginx o con `docker compose exec`.

**Frontend en modo desarrollo (opcional):**

```bash
cd frontend
npm install
npm start
```

Disponible en http://localhost:4200. El proxy de Angular envía `/api` a `http://localhost`, por lo que el stack de Docker debe estar levantado.

Si accedes desde otro equipo o servidor, reemplaza `localhost` por la IP o el dominio del host, por ejemplo `http://192.168.1.50/`. En producción usa HTTPS y agrega el dominio a `ALLOWED_HOSTS` y `CSRF_TRUSTED_ORIGINS`.

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
   docker compose exec backend find /app/staticfiles -maxdepth 3 -type f | head
   ```

El flujo de autor admite un PDF de prueba de máximo **50 MB**. Nginx admite cuerpos de hasta **60 MB**, pero Django rechaza archivos que superen 50 MB.

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
docker compose exec backend python manage.py migrate --noinput
```

### 5.5 Archivos estáticos

```bash
docker compose exec backend python manage.py collectstatic --noinput
```

### 5.6 Django Admin

Django Admin queda disponible para soporte operativo en:

```text
http://<host>/admin/
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

La topología objetivo de producción publica los puertos `80` y `443`. Actualmente el servicio `web` publica únicamente `:80`; la habilitación de `:443` se realiza junto con la instalación del certificado institucional y el ajuste final de Nginx.

Para producción, coloca el certificado institucional en:

```text
nginx/certs/fullchain.pem
nginx/certs/privkey.pem
```

Requisitos:

- TLS 1.2 y TLS 1.3.
- Redirección de HTTP a HTTPS.
- `server_tokens off`.
- Cabeceras de seguridad:
  - `X-Content-Type-Options`
  - `X-Frame-Options`
  - `Referrer-Policy`
  - `Permissions-Policy`
  - `Content-Security-Policy`

Para un piloto local sin certificado institucional, se puede usar un certificado autofirmado, pero el navegador mostrará una advertencia y no debe habilitarse HSTS hasta contar con un certificado válido.

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

En desarrollo local, `/backups` suele requerir permisos de superusuario. Crea la ruta y asígnala a tu usuario antes de ejecutar el respaldo:

```bash
sudo mkdir -p /backups
sudo chown "$USER":"$(id -gn)" /backups
chmod 700 /backups
```

`BACKUP_ROOT` debe ser una ruta absoluta fuera del repositorio y de `/data/media`.

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

### 8.3 Restauración

> **Pendiente (TSK-76):** `restore.sh` invoca el comando de gestión `verify_integrity`, que aún no existe. Por eso la restauración completa falla actualmente en el paso de verificación de integridad; no la uses como restauración de producción hasta que ese comando esté implementado.

```bash
./scripts/restore.sh /backups/<timestamp>
```

Para pruebas automatizadas:

```bash
./scripts/restore.sh --yes /backups/<timestamp>
```

La restauración, cuando `verify_integrity` esté disponible:

1. Verifica los checksums.
2. Detiene `web` y `backend`.
3. Restaura PostgreSQL.
4. Restaura el volumen `media_data`.
5. Normaliza permisos.
6. Ejecuta la verificación de integridad.
7. Levanta los servicios.
8. Ejecuta `manage.py check`.

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
- Backend tests sobre PostgreSQL 16.
- Angular production build.
- Docker Compose validation.
- Aislamiento del volumen de archivos (`scripts/smoke_media_isolation.sh`).

El pipeline usa PostgreSQL, nunca SQLite, y no consume secretos de producción.

El job de Angular compila la SPA en modo producción e impide publicar un frontend que no compila.

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

### 10.2 Frontend

Desde el directorio `frontend/`:

```bash
cd frontend
npm ci
npx ng test --watch=false
```

Para desarrollo con recarga en caliente, con el stack de Docker Compose levantado:

```bash
cd frontend
npm start
```

La SPA de desarrollo usa `frontend/proxy.conf.json` para enviar `/api/` al backend.

### 10.3 Compose

```bash
docker compose config --quiet
```

### 10.4 Nginx

Verifica que las rutas internas no sean accesibles directamente:

```bash
curl -I http://127.0.0.1/media/
curl -I http://127.0.0.1/_protected/
curl -I http://127.0.0.1/_catalog/
```

Las respuestas esperadas son de denegación o recurso no disponible, no la entrega de archivos.

La **prueba de humo completa** del aislamiento del volumen es un script que no necesita la base de datos ni el stack en ejecución:

```bash
./scripts/smoke_media_isolation.sh
```

Levanta, de forma efímera, Nginx con la configuración real (`nginx/conf.d/default.conf`), el volumen en solo lectura y un backend de prueba que responde con `X-Accel-Redirect`, y comprueba que:

- desde fuera, `/_protected/`, `/_catalog/` y `/media/` no entregan archivos (tampoco con rutas codificadas, dobles barras o `..`) ni listan directorios;
- cuando el backend autoriza, Nginx sí entrega el PDF con `Cache-Control` y `nosniff` (control positivo);
- una redirección interna a `/media/` también se deniega;
- Nginx no puede escribir en el volumen y, en `docker-compose.yml`, solo `backend` lo monta con escritura.

Requiere Docker, `curl` y `python3`; termina con código distinto de cero si algo falla y limpia sus contenedores y su volumen.

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

Las fases 0, 1 y 2 están implementadas:

- Infraestructura: Docker Compose, PostgreSQL 16, Nginx, backend con Gunicorn y volumen `media_data`.
- Identidad: autenticación JWT con refresh en cookie `HttpOnly`, bloqueo de intentos, roles y panel multirrol.
- Autor: manuscritos, autores, carga y sanitización de PDF, envío formal, versiones, historial, descargas y baja lógica.
- Calidad: CI, respaldo, pruebas backend y frontend.

Las fases siguientes agregan:

- Revisión por pares y asignaciones.
- Veredictos editoriales y catálogo público.
- Notificaciones y auditoría administrativa.
- Endurecimiento y prueba de carga.

---

## 13. Metodología y ramas

El proyecto usa Specification-Driven Development con los artefactos en `.spec-kit/`.

Estrategia de ramas:

- `main`: producción.
- `develop`: integración principal.
- `dev/<integrante>-setup`: ramas de trabajo por integrante.

Los commits y la documentación operativa están en español. El código fuente y los nombres técnicos están en inglés.
