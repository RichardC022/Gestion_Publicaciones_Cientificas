# Guía rápida: levantar el sistema en menos de 5 minutos

Copia y pega los bloques **en orden**, dentro de la ruta de tu entorno. No hace falta leer nada más.
La referencia técnica completa está en [`README.md`](README.md) y la operación del servidor en [`docs/RUNBOOK.md`](docs/RUNBOOK.md).

**Requisitos:** Linux o macOS con `git`, `openssl`, `curl` y Docker con Compose v2 (`docker compose version`). Los puertos 80 y 443 deben estar libres.

- [A. Despliegue en producción / servidor piloto](#a-despliegue-en-producción--servidor-piloto)
- [B. Despliegue local / desarrollo](#b-despliegue-local--desarrollo)
- [Detener, reiniciar y empezar de cero](#detener-reiniciar-y-empezar-de-cero)
- [Si algo falla](#si-algo-falla)

---

## A. Despliegue en producción / servidor piloto

### A1. Clonar

```bash
git clone https://github.com/RichardC022/Gestion_Publicaciones_Cientificas.git
cd Gestion_Publicaciones_Cientificas
```

### A2. Tus datos (**edita estos valores** y pega el bloque)

```bash
export DOMINIO=gpc.unl.edu.ec
export SMTP_HOST=smtp.institucional.edu.ec
export SMTP_USER=notificaciones@unl.edu.ec
export SMTP_PASSWORD='clave-del-correo'

export ADMIN_ID=admin
export ADMIN_NOMBRE=Nombre
export ADMIN_APELLIDO=Apellido
export ADMIN_CORREO=admin@unl.edu.ec
```

### A3. Configuración (`.env` con secretos únicos generados y permisos 600)

```bash
cp .env.example .env
SMTP_PASSWORD_ESC=$(printf '%s' "$SMTP_PASSWORD" | sed 's/[&|\\]/\\&/g')
sed -i.bak \
  -e "s|^DJANGO_SECRET_KEY=.*|DJANGO_SECRET_KEY=$(openssl rand -hex 32)|" \
  -e "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$(openssl rand -hex 24)|" \
  -e "s|^APP_DB_PASSWORD=.*|APP_DB_PASSWORD=$(openssl rand -hex 24)|" \
  -e "s|^ALLOWED_HOSTS=.*|ALLOWED_HOSTS=${DOMINIO},localhost|" \
  -e "s|^CSRF_TRUSTED_ORIGINS=.*|CSRF_TRUSTED_ORIGINS=https://${DOMINIO}|" \
  -e "s|^EMAIL_HOST=.*|EMAIL_HOST=${SMTP_HOST}|" \
  -e "s|^EMAIL_HOST_USER=.*|EMAIL_HOST_USER=${SMTP_USER}|" \
  -e "s|^EMAIL_HOST_PASSWORD=.*|EMAIL_HOST_PASSWORD=${SMTP_PASSWORD_ESC}|" \
  -e "s|^DEFAULT_FROM_EMAIL=.*|DEFAULT_FROM_EMAIL=${SMTP_USER}|" \
  .env
rm -f .env.bak
chmod 600 .env
```

### A4. Certificado TLS (autofirmado, para arrancar de inmediato)

```bash
./scripts/make_dev_cert.sh
```

Para usar el certificado institucional, copia `fullchain.pem` y `privkey.pem` en `nginx/certs/` (sustituye a los autofirmados) y ejecuta `docker compose restart web`.

### A5. Construir y levantar (**solo** `docker-compose.yml`)

```bash
docker compose up -d --build --wait
```

### A6. Roles y primera cuenta (administrador)

```bash
docker compose exec backend python manage.py seed_roles
docker compose exec backend python manage.py create_user "$ADMIN_ID" \
  --first-name "$ADMIN_NOMBRE" --last-name "$ADMIN_APELLIDO" \
  --email "$ADMIN_CORREO" --role ADMIN
```

La contraseña inicial se muestra **una sola vez**: anótala. En producción las cuentas se crean **siempre** con `create_user` (el Django Admin no existe):

```bash
# Otra cuenta (Editor, o Revisor con áreas de especialidad):
docker compose exec backend python manage.py create_user <identificador> \
  --first-name <Nombre> --last-name <Apellidos> --email <correo> --role EDITOR
docker compose exec backend python manage.py create_user <identificador> \
  --first-name <Nombre> --last-name <Apellidos> --email <correo> --role REVIEWER --areas "Agronomía,Medicina"
```

**No ejecutes `seed_dev_users` en producción** (se niega a correr sin una variable explícita).

### A7. Comprobar

```bash
docker compose ps
curl -ks https://localhost/api/health/; echo
curl -ks -o /dev/null -w "admin: %{http_code}\n" https://localhost/admin/
```

Debes ver los servicios en `healthy`/`running`, `{"status":"ok"}` y `admin: 404`. Abre `https://<tu-dominio>` e inicia sesión con `$ADMIN_ID`.

---

## B. Despliegue local / desarrollo

### B1. Clonar

```bash
git clone https://github.com/RichardC022/Gestion_Publicaciones_Cientificas.git
cd Gestion_Publicaciones_Cientificas
```

### B2. Configuración (`.env` para `localhost` con secretos generados)

```bash
cp .env.example .env
sed -i.bak \
  -e "s|^DJANGO_SECRET_KEY=.*|DJANGO_SECRET_KEY=$(openssl rand -hex 32)|" \
  -e "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$(openssl rand -hex 24)|" \
  -e "s|^APP_DB_PASSWORD=.*|APP_DB_PASSWORD=$(openssl rand -hex 24)|" \
  -e "s|^EMAIL_HOST_PASSWORD=.*|EMAIL_HOST_PASSWORD=$(openssl rand -hex 12)|" \
  -e "s|^ALLOWED_HOSTS=.*|ALLOWED_HOSTS=localhost,127.0.0.1|" \
  -e "s|^CSRF_TRUSTED_ORIGINS=.*|CSRF_TRUSTED_ORIGINS=https://localhost|" \
  .env
rm -f .env.bak
chmod 600 .env
```

### B3. Certificado TLS (autofirmado)

```bash
./scripts/make_dev_cert.sh
```

### B4. Construir y levantar (**combinando** `docker-compose.dev.yml`)

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build --wait
```

Además del sistema, abre PostgreSQL en `127.0.0.1:5432` y Adminer (cliente web de la base) en `http://127.0.0.1:8888` (sistema PostgreSQL, servidor `db`).

### B5. Roles y cuentas de prueba (una por rol)

```bash
docker compose exec -e ALLOW_DEV_USERS=1 backend python manage.py seed_dev_users
```

Contraseña de todas: `Gpc-dev-2026`.

| Identificador | Rol |
|---|---|
| `autor`, `autor2` | Autor |
| `editor` | Editor |
| `revisor`, `revisor2` | Revisor |
| `admin` | Administrador |
| `autor.revisor` | Autor y Revisor a la vez |

Repetir el comando restablece las contraseñas sin duplicar cuentas. Para una cuenta propia en desarrollo también sirve `create_user` (`docker compose exec backend python manage.py create_user <identificador> --first-name <N> --last-name <A> --email <correo> --role AUTHOR`).

### B6. Comprobar

```bash
docker compose ps
curl -ks https://localhost/api/health/; echo
```

Abre `https://localhost` (el navegador avisará del certificado autofirmado: acepta la excepción) e inicia sesión con `editor` / `Gpc-dev-2026`.

---

## Detener, reiniciar y empezar de cero

Producción (solo `docker-compose.yml`):

```bash
docker compose stop                 # detener (conserva los datos)
docker compose up -d --wait         # volver a levantar
docker compose down -v              # BORRA contenedores y TODOS los datos (base y PDF)
```

Desarrollo (con `docker-compose.dev.yml`):

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml stop
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --wait
docker compose -f docker-compose.yml -f docker-compose.dev.yml down -v   # empezar de cero (borra los datos)
```

Tras un `down -v` repite desde el paso de «Construir y levantar» de tu ruta.

## Si algo falla

| Síntoma | Solución |
|---|---|
| `port is already allocated` (80 o 443) | Otro servicio usa ese puerto: detenlo (`sudo ss -ltnp 'sport = :443'` indica cuál) y repite el paso de levantar. |
| El backend no arranca y dice `contiene un valor de ejemplo` o `faltan variables` | El `.env` conserva `change-me` o quedó vacío (¿faltó pegar el bloque de tus datos?): `rm .env` y repite el paso de configuración. |
| `web` no arranca y menciona `fullchain.pem` | Falta el certificado: `./scripts/make_dev_cert.sh` y `docker compose up -d --wait`. |
| `seed_dev_users` dice que se niega a correr | Falta `-e ALLOW_DEV_USERS=1` (copia el comando tal cual, con `exec -e`). |
| `create_user` dice `Faltan los roles en la base` | Ejecuta antes `docker compose exec backend python manage.py seed_roles`. |
| `/admin/` responde 404 | Es lo esperado: el Django Admin está deshabilitado a propósito. |
| Los logs del backend | `docker compose logs backend` |
