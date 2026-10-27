# Tareas de Implementación — Sistema de Gestión de Publicaciones Científicas

## Fase 0 — Fundación (soporte de todas las HU/RF)

### DevOps

### TSK-01 — Reestructurar el repositorio a `/backend` y `/frontend`

- **ID:** TSK-01
- **Título:** Reestructurar el repositorio a `/backend` y `/frontend`
- **Capa:** [DevOps]
- **Descripción técnica:** Mover `manage.py`, `config/`, `apps/` y `tests/` a `backend/`; crear `frontend/`; retirar `templates/` y `static/` de la ruta de ejecución; actualizar imports, rutas de settings y referencias del repositorio. Conservar Django Admin solo como herramienta operativa.
- **Criterios de aceptación:**
  - `python backend/manage.py check` funciona y no quedan imports que apunten a la estructura raíz anterior.
  - La raíz queda organizada en `backend/`, `frontend/`, `nginx/`, `scripts/`, `docker-compose.yml`, `.env.example` y `README.md`.
  - No queda ninguna dependencia de ejecución con MySQL ni con las plantillas server-side anteriores.

### TSK-02 — Definir Docker Compose con PostgreSQL 16, backend y web

- **ID:** TSK-02
- **Título:** Definir Docker Compose con PostgreSQL 16, backend y web
- **Capa:** [DevOps]
- **Descripción técnica:** Crear `docker-compose.yml` con servicios `db` (`postgres:16-alpine`), `backend` (Gunicorn/Django) y `web` (Nginx + Angular); volúmenes `postgres_data`, `media_data` y `static_data`; redes `backend_net` interna y `frontend_net`; healthchecks y dependencias.
- **Criterios de aceptación:**
  - `docker compose config` valida sin errores y `db`/`backend` no publican puertos al host; solo `web` expone 80/443.
  - `backend` espera a `db` saludable y `web` espera a `backend` saludable.
  - `media_data` se monta con escritura en backend y solo lectura en web.

### TSK-03 — Crear imagen de backend y fijar dependencias

- **ID:** TSK-03
- **Título:** Crear imagen de backend y fijar dependencias
- **Capa:** [DevOps]
- **Descripción técnica:** Crear `backend/Dockerfile` y `backend/requirements/base.txt`, `development.txt` y `production.txt`; incluir Django, DRF, `psycopg[binary]`, `pikepdf`, `gunicorn` y JWT; retirar `mysqlclient`; definir usuario de ejecución, `WORKDIR` y comando Gunicorn.
- **Criterios de aceptación:**
  - La imagen construye y `python manage.py check` pasa dentro del contenedor.
  - No se instala MySQL ni SQLite como motor de ejecución.
  - Gunicorn escucha en `0.0.0.0:8000` y el contenedor no requiere privilegios de root para servir la aplicación.

### TSK-04 — Configurar Nginx con TLS, proxy, estáticos y ubicaciones internas

- **ID:** TSK-04
- **Título:** Configurar Nginx con TLS, proxy, estáticos y ubicaciones internas
- **Capa:** [DevOps]
- **Descripción técnica:** Crear `nginx/nginx.conf`, `nginx/conf.d/default.conf` y `nginx/certs/`; configurar `client_max_body_size 60m`, timeouts de 120 s, proxy a `backend:8000`, fallback de Angular, `/static/`, `/_protected/`, `/_catalog/`, `deny all` para `/media/` y cabeceras de seguridad.
- **Criterios de aceptación:**
  - HTTP redirige a HTTPS y solo se aceptan TLS 1.2/1.3.
  - `/_protected/` y `/_catalog/` son `internal`; una petición externa directa no obtiene el archivo.
  - `/api/` llega al backend, las rutas Angular resuelven a `index.html` y los PDF no se comprimen.

### TSK-05 — Centralizar variables de entorno y secretos

- **ID:** TSK-05
- **Título:** Centralizar variables de entorno y secretos
- **Capa:** [DevOps]
- **Descripción técnica:** Crear `.env.example` con `DJANGO_SETTINGS_MODULE`, `DJANGO_SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, PostgreSQL, JWT, sesión, PDF, `MEDIA_ROOT`, `TZ` y SMTP; documentar permisos `0600` para `.env`.
- **Criterios de aceptación:**
  - `.env.example` no contiene secretos reales y cubre todas las variables requeridas por Compose y Django.
  - `TZ=America/Guayaquil`, `MEDIA_ROOT=/data/media` y los límites de PDF están explícitos.
  - El arranque falla de forma clara si faltan variables obligatorias en producción.

### TSK-06 — Preparar el volumen `media_data` y sus permisos

- **ID:** TSK-06
- **Título:** Preparar el volumen `media_data` y sus permisos
- **Capa:** [DevOps]
- **Descripción técnica:** Crear `scripts/init_media.sh` y la estructura `private/drafts`, `private/manuscripts`, `public/catalog` y `tmp/uploads`; aplicar directorios `0750`, archivos `0640`, grupo `media`, `umask 0027` y montaje `:ro` en Nginx.
- **Criterios de aceptación:**
  - La estructura se crea una sola vez y el backend puede escribir; Nginx solo puede leer.
  - Las rutas usan UUID y versión, nunca título, correo o nombre del autor.
  - `/data/media` no se sirve como directorio estático público.

### TSK-07 — Implementar respaldo, restauración y verificación de integridad

- **ID:** TSK-07
- **Título:** Implementar respaldo, restauración y verificación de integridad
- **Capa:** [DevOps]
- **Descripción técnica:** Crear `scripts/backup.sh`, `scripts/restore.sh`, `scripts/verify_integrity.sh` y una plantilla de cron; usar `pg_dump --format=custom`, `tar` del volumen, `SHA256SUMS`, retención de 30 días y permisos `0700`; el script de integridad envuelve `python manage.py verify_integrity` y documenta la restauración de humo.
- **Criterios de aceptación:**
  - El respaldo produce `database.dump`, `media.tar.gz` y checksums verificables.
  - La retención no elimina el respaldo más reciente y la restauración de humo reconstruye la base y el volumen.
  - Los respaldos no se versionan ni se sirven por Nginx; la verificación reporta discrepancias sin modificar archivos.

### TSK-08 — Crear la base del pipeline de integración continua

- **ID:** TSK-08
- **Título:** Crear la base del pipeline de integración continua
- **Capa:** [DevOps]
- **Descripción técnica:** Crear `.github/workflows/ci.yml` con jobs de `manage.py check`, pruebas backend con PostgreSQL, `ng build --configuration production` y `docker compose config`; cachear dependencias y no usar secretos de producción.
- **Criterios de aceptación:**
  - El pipeline falla si Django no pasa `check`, si Angular no compila o si Compose es inválido.
  - Las pruebas usan PostgreSQL, nunca SQLite.
  - No se imprimen secretos ni archivos `.env` reales.

### TSK-09 — Documentar instalación, despliegue y operación inicial

- **ID:** TSK-09
- **Título:** Documentar instalación, despliegue y operación inicial
- **Capa:** [DevOps]
- **Descripción técnica:** Actualizar `README.md` con estructura `/backend` y `/frontend`, PostgreSQL, Docker Compose, migraciones, `seed_roles`, superusuario, carga de prueba, respaldo y restauración; actualizar `.env.example` y comandos de instalación.
- **Criterios de aceptación:**
  - Un entorno limpio puede levantarse siguiendo el README sin pasos de MySQL.
  - Se documentan migraciones, roles, TLS, volumen y restauración.
  - No se publican credenciales reales ni rutas absolutas dependientes del desarrollador.

### Backend

### TSK-10 — Crear el proyecto Django y las apps de dominio

- **ID:** TSK-10
- **Título:** Crear el proyecto Django y las apps de dominio
- **Capa:** [Backend]
- **Descripción técnica:** Crear `backend/manage.py`, `config/settings/base.py`, `development.py`, `production.py`, `config/urls.py`, `asgi.py`, `wsgi.py` y las apps `users`, `publications`, `reviews`, `audit` y `notifications` con `apps.py`, migraciones y tests.
- **Criterios de aceptación:**
  - `python manage.py check` pasa y las cinco apps están en `INSTALLED_APPS`.
  - `config/settings/production.py` exige `DEBUG=0`, `ALLOWED_HOSTS` y secretos por entorno.
  - Las rutas se montan bajo `/api/` y Django Admin queda separado como herramienta operativa.

### TSK-11 — Establecer envelope de errores, paginación y request ID

- **ID:** TSK-11
- **Título:** Establecer envelope de errores, paginación y request ID
- **Capa:** [Backend]
- **Descripción técnica:** Crear `config/exceptions.py`, `config/pagination.py` y `config/middleware.py`; registrar el manejador DRF y el middleware en settings; estandarizar `{error: {code, message, details, request_id}}`, `page`/`page_size` con máximo 100 y `X-Request-ID`.
- **Criterios de aceptación:**
  - Todos los errores de dominio usan el envelope y conservan el `request_id`.
  - `page_size` nunca supera 100 y los filtros inválidos devuelven `400`.
  - El `request_id` se propaga a logs y auditoría sin datos personales.

### TSK-12 — Implementar el endpoint de salud

- **ID:** TSK-12
- **Título:** Implementar el endpoint de salud
- **Capa:** [Backend]
- **Descripción técnica:** Crear `backend/config/health.py` y registrar `GET /api/health/`; verificar `SELECT 1` en PostgreSQL, escritura/lectura temporal en `MEDIA_ROOT` y disponibilidad básica de la aplicación; devolver `200` o `503`.
- **Criterios de aceptación:**
  - Un fallo de base o volumen devuelve `503` con un mensaje genérico y sin detalles sensibles.
  - El endpoint es público, no devuelve datos de usuarios ni contenido de manuscritos.
  - Compose lo usa como healthcheck del backend.

### Frontend

### TSK-13 — Crear la SPA Angular y su configuración base

- **ID:** TSK-13
- **Título:** Crear la SPA Angular y su configuración base
- **Capa:** [Frontend]
- **Descripción técnica:** Crear `frontend/package.json`, `angular.json`, `tsconfig.json`, `src/main.ts`, `src/app/app.component.ts`, `src/app/app.config.ts`, `src/app/app.routes.ts`, `core/http/api-base-url.token.ts` y entornos; configurar standalone components, lazy loading, `HttpClient` y las rutas públicas `/catalog` y `/login`.
- **Criterios de aceptación:**
  - `ng build --configuration production` termina sin errores de tipo.
  - La URL de API se inyecta por entorno y no se codifica en los componentes.
  - No se incorpora NgRx ni una pantalla de selección de rol.

### TSK-14 — Crear layout, tema y componentes compartidos

- **ID:** TSK-14
- **Título:** Crear layout, tema y componentes compartidos
- **Capa:** [Frontend]
- **Descripción técnica:** Crear `core/layout/shell.component.ts`, `header`, `side-nav`, `notification-bell`, `shared/components/status-badge`, `round-counter`, `empty-state`, `error-state`, `confirm-dialog`, `pagination`, `loading-spinner`, `pdf-viewer`, `shared/directives/has-role.directive.ts` y `shared/pipes/file-size.pipe.ts`/`safe-url.pipe.ts`; definir `styles.scss` con la paleta institucional.
- **Criterios de aceptación:**
  - Verde para éxito, amarillo para advertencia, rojo para acciones destructivas y azul/gris para navegación.
  - El layout es responsive, navegable por teclado y con contraste WCAG AA.
  - No existe selector ni conmutador de rol.

### TSK-15 — Crear la imagen Docker del frontend

- **ID:** TSK-15
- **Título:** Crear la imagen Docker del frontend
- **Capa:** [Frontend]
- **Descripción técnica:** Crear `frontend/Dockerfile` multi-stage (Node para build y Nginx para servir), `frontend/.dockerignore` y la copia de `nginx/` requerida por el contexto raíz; publicar el `dist` en la ruta que sirve `web`.
- **Criterios de aceptación:**
  - La imagen construye desde la raíz y sirve la SPA compilada, no el servidor de desarrollo.
  - Las rutas profundas de Angular resuelven mediante `try_files`.
  - La imagen no incluye `node_modules`, secretos ni archivos `.env`.

## Fase 1 — Identidad y panel (HU-01, HU-02, HU-03; RF-01, RF-12, RF-16)

### DevOps

### TSK-16 — Configurar secretos JWT, cookies y SMTP

- **ID:** TSK-16
- **Título:** Configurar secretos JWT, cookies y SMTP
- **Capa:** [DevOps]
- **Descripción técnica:** Completar `.env.example` y `docker-compose.yml` con `JWT_ACCESS_MINUTES=15`, `JWT_REFRESH_DAYS=7`, `SESSION_IDLE_MINUTES=30`, `EMAIL_*`, `DEFAULT_FROM_EMAIL`, `CSRF_TRUSTED_ORIGINS` y flags de cookie; documentar que `.env` se crea con permisos `0600`.
- **Criterios de aceptación:**
  - El refresh token se configura como `HttpOnly`, `Secure` y `SameSite=Strict`; el access token no se persiste.
  - SMTP y JWT no se versionan con valores reales.
  - Los valores de producción son distintos de los de desarrollo.

### Backend

### TSK-17 — Implementar usuarios, roles, perfiles e intentos de acceso

- **ID:** TSK-17
- **Título:** Implementar usuarios, roles, perfiles e intentos de acceso
- **Capa:** [Backend]
- **Descripción técnica:** Crear `apps/users/models.py` con `User`, `Role`, `UserRole`, `ReviewerProfile` y `LoginAttempt`; configurar `AUTH_USER_MODEL="users.User"`; agregar índice único parcial de rol activo, GIN de `expertise_areas` y comando `apps/users/management/commands/seed_roles.py`.
- **Criterios de aceptación:**
  - Los roles sembrados son exactamente `AUTHOR`, `REVIEWER`, `EDITOR` y `ADMIN`, y el comando es idempotente.
  - Un usuario conserva historial de roles retirados y no puede tener dos filas activas del mismo rol.
  - `is_active=false` impide autenticarse y nunca se borra físicamente una cuenta con historial.

### TSK-18 — Crear auditoría inmutable y cadena de hashes

- **ID:** TSK-18
- **Título:** Crear auditoría inmutable y cadena de hashes
- **Capa:** [Backend]
- **Descripción técnica:** Crear `apps/audit/models.py` con `AuditLog` (`event_id`, `occurred_at`, `actor_id`, `actor_role`, `action`, `entity_type`, `entity_id`, `result`, `reason`, `request_id`, `ip_address`, `user_agent`, `details`, `previous_hash`, `entry_hash`) y `apps/audit/services.py` con `AuditService.record()`; usar `pg_advisory_xact_lock(hashtext('audit_audit_log'))`, JSON canónico y migración con trigger append-only.
- **Criterios de aceptación:**
  - Cada evento encadena `previous_hash` y `entry_hash`; el primero tiene `previous_hash=NULL`.
  - `UPDATE` y `DELETE` sobre `audit_audit_log` fallan por trigger.
  - Si la auditoría no puede escribirse, el servicio lanza `AuditUnavailable` y la acción crítica se revierte con `503`.

### TSK-19 — Implementar autenticación JWT institucional

- **ID:** TSK-19
- **Título:** Implementar autenticación JWT institucional
- **Capa:** [Backend]
- **Descripción técnica:** Crear `apps/users/serializers.py`, `apps/users/services/auth.py`, `apps/users/views.py` y `apps/users/urls.py` para `POST /api/auth/login/`, `POST /api/auth/refresh/`, `POST /api/auth/logout/` y `GET /api/auth/me/`; implementar rotación y revocación de refresh tokens y revalidación de roles activos.
- **Criterios de aceptación:**
  - Credenciales inválidas, cuenta inactiva o inexistente devuelven el mismo mensaje genérico.
  - El refresh rota en cada uso y el logout revoca el refresh vigente.
  - Los roles y el estado de la cuenta se leen de PostgreSQL en cada solicitud; el claim del JWT no autoriza por sí solo.

### TSK-20 — Aplicar límite de intentos y auditoría de login

- **ID:** TSK-20
- **Título:** Aplicar límite de intentos y auditoría de login
- **Capa:** [Backend]
- **Descripción técnica:** Implementar el conteo de fallos en `apps/users/services/auth.py` usando `users_login_attempt`; bloquear tras cinco fallos por identificador en quince minutos; devolver `429` con `Retry-After`; auditar éxito, fallo y bloqueo sin almacenar contraseñas.
- **Criterios de aceptación:**
  - El sexto intento dentro de la ventana se rechaza con `429` y no revela si la cuenta existe.
  - El bloqueo expira automáticamente al cumplirse la ventana.
  - La auditoría registra identificador intentado, IP y resultado, nunca la contraseña.

### TSK-21 — Implementar permisos por rol y por objeto

- **ID:** TSK-21
- **Título:** Implementar permisos por rol y por objeto
- **Capa:** [Backend]
- **Descripción técnica:** Crear `apps/users/permissions.py` y permisos de objeto en cada app: `IsAuthor`, `IsReviewer`, `IsEditor`, `IsAdmin`, `IsManuscriptOwner`, `IsAssignedReviewer` e `IsPublicCatalog`; centralizar la lectura de roles activos y el retorno `404` para objetos ajenos.
- **Criterios de aceptación:**
  - `403` se usa solo para rol sin permiso de módulo; un objeto ajeno devuelve `404`.
  - `IsAdmin` no concede acceso a manuscritos, evaluaciones ni PDF.
  - Un rol retirado durante la sesión bloquea la siguiente acción aunque el access token siga vigente.

### TSK-22 — Implementar el panel unificado en una sola respuesta

- **ID:** TSK-22
- **Título:** Implementar el panel unificado en una sola respuesta
- **Capa:** [Backend]
- **Descripción técnica:** Crear `DashboardView` y serializadores en `apps/users/views.py`/`serializers.py` para `GET /api/dashboard/`; devolver `user`, `roles` y `sections` (`author`, `reviewer`, `editor`, `admin`) con estado `ok` o `error` independiente por sección.
- **Criterios de aceptación:**
  - Una sola llamada devuelve todas las secciones de los roles activos, sin exigir elegir rol.
  - El fallo de una sección no cancela las demás y conserva `200` con un mensaje reintentable.
  - Un usuario sin roles activos recibe una sección vacía explícita y no puede acceder a rutas internas.

### TSK-23 — Probar autenticación, permisos y panel

- **ID:** TSK-23
- **Título:** Probar autenticación, permisos y panel
- **Capa:** [Backend]
- **Descripción técnica:** Crear pruebas en `backend/tests/users/` y `backend/tests/audit/` para login, refresh, logout, bloqueo, revalidación de roles, dashboard parcial y cadena de auditoría; usar `APIClient`, `factory_boy` y PostgreSQL de prueba.
- **Criterios de aceptación:**
  - Se cubren cinco intentos, cuenta inactiva, rol retirado y refresh revocado.
  - El panel multirrol devuelve secciones simultáneas y tolera un fallo parcial.
  - La auditoría fallida revierte la operación crítica y devuelve `503`.

### Frontend

### TSK-24 — Implementar AuthService, AuthStore e interceptores

- **ID:** TSK-24
- **Título:** Implementar AuthService, AuthStore e interceptores
- **Capa:** [Frontend]
- **Descripción técnica:** Crear `core/auth/auth.service.ts`, `auth.store.ts`, `auth.interceptor.ts`, `core/http/error.interceptor.ts`, `request-id.interceptor.ts` y modelos de sesión/error; mantener el access token en memoria, usar `withCredentials` para refresh y normalizar `ApiError`.
- **Criterios de aceptación:**
  - El access token y los PDFs nunca se guardan en `localStorage`.
  - Un `401` intenta refrescar una sola vez; si falla, limpia la sesión y redirige a login.
  - `409`, `413`, `429` y `503` muestran mensajes accionables y respetan `Retry-After`.

### TSK-25 — Configurar guards y rutas lazy

- **ID:** TSK-25
- **Título:** Configurar guards y rutas lazy
- **Capa:** [Frontend]
- **Descripción técnica:** Crear `auth.guard.ts`, `roles.guard.ts`, `public-only.guard.ts`, `unsaved-changes.guard.ts` y `app.routes.ts`; proteger `/app/**` y las rutas por rol, con redirección a `/login?returnUrl=...`, `403` y `404`.
- **Criterios de aceptación:**
  - Las rutas internas exigen sesión y al menos un rol activo; no existe ruta de selección de rol.
  - Un formulario sucio advierte antes de abandonar la ruta.
  - Un usuario con roles simultáneos accede a todas sus secciones sin conmutar.

### TSK-26 — Crear login, shell y navegación por roles

- **ID:** TSK-26
- **Título:** Crear login, shell y navegación por roles
- **Capa:** [Frontend]
- **Descripción técnica:** Crear `features/auth/login/login.component.ts`, `core/layout/shell.component.ts`, `header.component.ts`, `side-nav.component.ts` y `notification-bell.component.ts`; mostrar nombre, roles activos, navegación de todos los roles y cierre de sesión.
- **Criterios de aceptación:**
  - El login usa credenciales institucionales y muestra un error genérico.
  - La navegación muestra los módulos de todos los roles activos, sin apartados de roles inexistentes.
  - La campana y el menú son accesibles por teclado y no exponen datos de otros usuarios.

### TSK-27 — Implementar el dashboard unificado y sus secciones

- **ID:** TSK-27
- **Título:** Implementar el dashboard unificado y sus secciones
- **Capa:** [Frontend]
- **Descripción técnica:** Crear `features/dashboard/unified-dashboard/` y los componentes `author-summary`, `reviewer-summary`, `editor-summary` y `admin-summary`; consumir una sola vez `DashboardService.getDashboard()` y manejar señales por sección y `sectionErrors`.
- **Criterios de aceptación:**
  - Las secciones de todos los roles activos se renderizan simultáneamente.
  - Si una sección falla, las demás permanecen visibles y la fallida ofrece “Reintentar”.
  - No se muestra un paso “Seleccione rol” ni un selector en el encabezado.

### TSK-28 — Probar autenticación, guards y dashboard

- **ID:** TSK-28
- **Título:** Probar autenticación, guards y dashboard
- **Capa:** [Frontend]
- **Descripción técnica:** Crear pruebas Jasmine/Karma para `AuthStore`, `AuthService`, guards y `UnifiedDashboardComponent`; simular refresh fallido, rol retirado, multirrol y fallo parcial de una sección.
- **Criterios de aceptación:**
  - Las pruebas verifican que no se guardan tokens en `localStorage`.
  - El dashboard muestra secciones simultáneas y no muestra apartados de roles inexistentes.
  - Un fallo de sección no oculta las demás y ofrece reintento.

## Fase 2 — Autor y documentos (HU-04, HU-05, HU-06, HU-07, HU-08, HU-09, HU-22, HU-23; RF-02, RF-05, RF-06, RF-10, RF-14, RF-21, RF-22)

### DevOps

### TSK-29 — Verificar límites de carga y almacenamiento del volumen

- **ID:** TSK-29
- **Título:** Verificar límites de carga y almacenamiento del volumen
- **Capa:** [DevOps]
- **Descripción técnica:** Ajustar `docker-compose.yml`, `nginx/conf.d/default.conf` y `scripts/init_media.sh` para `client_max_body_size 60m`, timeouts de 120 s, buffer temporal y limpieza de `tmp/uploads`; montar `media_data` con escritura en backend y solo lectura en web.
- **Criterios de aceptación:**
  - Nginx acepta hasta 60 MB y Django aplica el límite real de 50 MB por PDF.
  - `tmp/uploads` se limpia al iniciar y al finalizar una carga fallida.
  - `/data/media` no es accesible por una URL estática pública.

### Backend

### TSK-30 — Crear modelos de manuscritos, autores, versiones, rondas y eventos

- **ID:** TSK-30
- **Título:** Crear modelos de manuscritos, autores, versiones, rondas y eventos
- **Capa:** [Backend]
- **Descripción técnica:** Crear `apps/publications/models.py` con `Manuscript`, `ManuscriptAuthor`, `ManuscriptVersion`, `CorrectionRound` y `StatusEvent`; incluir `code`, `status`, `current_round`, `current_version`, `lock_version`, `is_active`, `withdrawn_*`, `metadata_snapshot`, hashes y `search_vector`; crear la secuencia `publications_manuscript_code_seq`.
- **Criterios de aceptación:**
  - `code` es único con formato `GPC-AAAA-######`; `(manuscript_id, version_number)` y `(manuscript_id, round_number)` son únicos.
  - La baja lógica mantiene `status` y exige `is_active=false` junto con `withdrawn_at`.
  - `metadata_snapshot` y los hashes son obligatorios en cada versión formal y nunca se sobrescriben.

### TSK-31 — Crear migraciones, índices y triggers de integridad

- **ID:** TSK-31
- **Título:** Crear migraciones, índices y triggers de integridad
- **Capa:** [Backend]
- **Descripción técnica:** Escribir migraciones para la secuencia, índices GIN/B-tree, restricciones `CHECK`, columna generada `search_vector` y triggers `prevent_manuscript_delete`, `prevent_version_mutation` y `prevent_append_only_mutation`; agregar el índice único de autor responsable.
- **Criterios de aceptación:**
  - Las migraciones aplican sobre una base PostgreSQL vacía y son reversibles en desarrollo.
  - `DELETE` sobre manuscritos y `UPDATE`/`DELETE` sobre versiones o eventos falla en base de datos.
  - Solo puede existir un autor responsable por manuscrito y un `author_order` único.

### TSK-32 — Implementar CRUD de manuscritos y validación de autores

- **ID:** TSK-32
- **Título:** Implementar CRUD de manuscritos y validación de autores
- **Capa:** [Backend]
- **Descripción técnica:** Crear `apps/publications/serializers.py`, `views.py`, `urls.py` y `permissions.py` para `GET/POST /api/manuscripts/` y `GET/PATCH /api/manuscripts/{id}/`; implementar `AuthorManuscriptSerializer`, `AuthorEvaluationFeedbackSerializer`, `EditorManuscriptSerializer`, filtros, paginación y `If-Match`/`ETag` con `lock_version`.
- **Criterios de aceptación:**
  - Solo se edita en `DRAFT` o `REQUIRES_CORRECTIONS`; otro estado devuelve `409`; el `PATCH` no crea versión ni ronda y audita los campos modificados.
  - Se exige al menos un autor y exactamente un `is_corresponding=true`; el autor registrante debe figurar en la lista.
  - Un manuscrito ajeno devuelve `404`, el Editor no puede omitir su conflicto de interés y el serializador del Autor no expone identidad del Revisor ni comentarios confidenciales.

### TSK-33 — Implementar validación, sanitización y hashes de PDF

- **ID:** TSK-33
- **Título:** Implementar validación, sanitización y hashes de PDF
- **Capa:** [Backend]
- **Descripción técnica:** Crear `apps/publications/services/pdf.py` y `storage.py`; implementar `PdfService.validate()` y `sanitize()` con `pikepdf`, firma `%PDF-`, una página mínima, rechazo de cifrado y contenido activo, SHA-256 en streaming y rutas exclusivas con `O_CREAT` y `O_EXCL`.
- **Criterios de aceptación:**
  - Un PDF de 50 MB exactos se acepta; 50 MB + 1 byte devuelve `413`.
  - PDF truncado, vacío, cifrado o con `/JavaScript`, `/OpenAction`, `/AA`, `/Launch` o `/EmbeddedFiles` se rechaza con `400`.
  - El sanitizado elimina `/Info`, XMP, `/Metadata`, `/PieceInfo`, anotaciones y contenido activo; nunca sobrescribe un archivo existente.

### TSK-34 — Implementar carga y reemplazo de PDF de borrador

- **ID:** TSK-34
- **Título:** Implementar carga y reemplazo de PDF de borrador
- **Capa:** [Backend]
- **Descripción técnica:** Crear el endpoint `POST /api/manuscripts/{id}/draft-file/` en `apps/publications/views.py` y el servicio de borradores; aceptar solo `multipart/form-data`, guardar en `private/drafts/<user_uuid>/<draft_uuid>.pdf`, reemplazar el borrador anterior y auditar la operación.
- **Criterios de aceptación:**
  - Solo el Autor propietario y un manuscrito `DRAFT` pueden cargar; otro estado devuelve `409`.
  - La carga no crea versión, ronda ni snapshot.
  - Un archivo inválido, mayor a 50 MB o con `Content-Type` incorrecto devuelve `400`/`413`/`415` y elimina el temporal.

### TSK-35 — Implementar el envío formal y la creación de v1/ronda 0

- **ID:** TSK-35
- **Título:** Implementar el envío formal y la creación de v1/ronda 0
- **Capa:** [Backend]
- **Descripción técnica:** Crear `apps/publications/services/submission.py` y el endpoint `POST /api/manuscripts/{id}/submit/`; dentro de `transaction.atomic()` bloquear el manuscrito, validar borrador y metadatos, crear `original.pdf`, `sanitized.pdf`, `metadata.json`, `ManuscriptVersion`, `CorrectionRound` 0, `StatusEvent` y auditoría; encolar avisos después del commit.
- **Criterios de aceptación:**
  - El envío crea exactamente v1 y ronda 0, actualiza `current_version` y `status=SUBMITTED`, y devuelve `201`.
  - Si falla la escritura, la sanitización o la auditoría, se revierte la transacción y se eliminan los archivos recién movidos.
  - `metadata_sha256` se calcula sobre JSON canónico con claves ordenadas y autores completos.

### TSK-36 — Implementar nueva versión en `REQUIRES_CORRECTIONS`

- **ID:** TSK-36
- **Título:** Implementar nueva versión en `REQUIRES_CORRECTIONS`
- **Capa:** [Backend]
- **Descripción técnica:** Crear `apps/publications/services/versions.py` y `POST /api/manuscripts/{id}/versions/`; bloquear el manuscrito, calcular la versión consecutiva, asociarla a la ronda vigente, generar snapshot y hashes, actualizar `status=SUBMITTED`, registrar el evento y auditar.
- **Criterios de aceptación:**
  - Solo se permite en `REQUIRES_CORRECTIONS`; otro estado devuelve `409`.
  - La versión anterior permanece intacta y no se renombra ni se reutiliza.
  - La operación exige `Idempotency-Key`, no duplica la versión si se repite la misma clave y rechaza un envío sin cambios de PDF ni metadatos.

### TSK-37 — Implementar baja lógica y retiro del catálogo

- **ID:** TSK-37
- **Título:** Implementar baja lógica y retiro del catálogo
- **Capa:** [Backend]
- **Descripción técnica:** Crear `apps/publications/services/withdraw.py` y `POST /api/manuscripts/{id}/withdraw/`; marcar `is_active=false`, `withdrawn_at`, `withdrawn_by_id` y `withdrawal_reason`; revocar asignación `ACTIVE`, desactivar `CatalogEntry`, notificar a Revisor y Editor, registrar evento y auditoría, y eliminar la copia pública después del commit.
- **Criterios de aceptación:**
  - En `UNDER_REVIEW` o `ACCEPTED` el motivo es obligatorio; en otros estados es opcional.
  - Nunca se borra el manuscrito, versión, evaluación, veredicto, historial ni auditoría.
  - El catálogo deja de mostrar el artículo de inmediato, el Revisor pierde el acceso y una segunda baja no duplica eventos ni avisos.

### TSK-38 — Implementar historial, versiones y descarga del original

- **ID:** TSK-38
- **Título:** Implementar historial, versiones y descarga del original
- **Capa:** [Backend]
- **Descripción técnica:** Crear `GET /api/manuscripts/{id}/versions/`, `GET /api/manuscripts/{id}/versions/{version_id}/file/` y `GET /api/manuscripts/{id}/history/`; construir rutas solo con UUID/versión y responder con `X-Accel-Redirect` a `/_protected/`, previa auditoría.
- **Criterios de aceptación:**
  - Autor propietario y Editor reciben `original.pdf`; el Revisor usa exclusivamente su endpoint sanitizado.
  - Un manuscrito ajeno o no asignado devuelve `404`, no `403`.
  - Si la auditoría de descarga falla, se devuelve `503` y no se emite `X-Accel-Redirect`.

### TSK-39 — Implementar idempotencia de operaciones POST

- **ID:** TSK-39
- **Título:** Implementar idempotencia de operaciones POST
- **Capa:** [Backend]
- **Descripción técnica:** Crear `IdempotencyKey` en `apps/publications/models.py` y `apps/publications/services/idempotency.py`; almacenar hash de solicitud, estado y cuerpo de respuesta, índice único `(user_id, endpoint, key)` y expiración de 24 horas; la limpieza se conecta con el comando de TSK-76.
- **Criterios de aceptación:**
  - Repetir la misma clave con el mismo payload devuelve la misma respuesta sin duplicar efectos.
  - La misma clave con payload distinto devuelve `409`.
  - Las claves vencidas se eliminan sin afectar operaciones vigentes.

### TSK-40 — Probar manuscritos, PDF, versiones y baja lógica

- **ID:** TSK-40
- **Título:** Probar manuscritos, PDF, versiones y baja lógica
- **Capa:** [Backend]
- **Descripción técnica:** Crear pruebas en `backend/tests/publications/` para CRUD, autores, PDF, sanitización, v1/ronda 0, nuevas versiones, hashes, baja lógica, descarga y permisos; incluir límites de 50 MB y concurrencia de versión.
- **Criterios de aceptación:**
  - Se verifican los límites 50 MB/50 MB + 1 byte y el rechazo de contenido activo.
  - Se comprueba que una versión anterior no se sobrescribe y que la baja no elimina registros.
  - Un fallo de auditoría o almacenamiento no deja una versión parcial.

### Frontend

### TSK-41 — Crear listado, formulario y detalle de manuscritos

- **ID:** TSK-41
- **Título:** Crear listado, formulario y detalle de manuscritos
- **Capa:** [Frontend]
- **Descripción técnica:** Crear `features/author/manuscript-list/`, `manuscript-form/` y `manuscript-detail/`; usar formularios reactivos con `FormArray` de autores, validación de exactamente un responsable, filtros por estado/fecha y vista de archivados; el detalle consume `AuthorEvaluationFeedbackSerializer` para mostrar veredicto, observaciones y siguiente acción.
- **Criterios de aceptación:**
  - El formulario bloquea el guardado si no hay autores o si hay más de un responsable.
  - Las acciones de edición solo aparecen en `DRAFT` o `REQUIRES_CORRECTIONS`.
  - El detalle muestra estado, versión, ronda, observaciones y veredicto cuando existan, pero nunca identidad del Revisor ni comentarios confidenciales.

### TSK-42 — Implementar el cargador de PDF

- **ID:** TSK-42
- **Título:** Implementar el cargador de PDF
- **Capa:** [Frontend]
- **Descripción técnica:** Crear `features/author/pdf-uploader/pdf-uploader.component.ts`; validar extensión `.pdf`, MIME y 50 MB antes de enviar; mostrar progreso, permitir reemplazar el borrador y manejar `413`/`415` del backend.
- **Criterios de aceptación:**
  - La validación del cliente es solo UX y el backend sigue siendo la barrera de seguridad.
  - Reemplazar el borrador no crea una versión formal.
  - Un archivo inválido muestra un error claro y no deja el formulario bloqueado.

### TSK-43 — Crear historial de versiones y diálogo de baja lógica

- **ID:** TSK-43
- **Título:** Crear historial de versiones y diálogo de baja lógica
- **Capa:** [Frontend]
- **Descripción técnica:** Crear `version-history/` y `withdraw-dialog/`; mostrar línea de tiempo con versión, ronda, fecha, hash y descarga; pedir motivo cuando el estado sea `UNDER_REVIEW` o `ACCEPTED`; confirmar la baja lógica.
- **Criterios de aceptación:**
  - Las versiones anteriores se muestran en solo lectura y con su hash.
  - El motivo es obligatorio en los estados que lo exigen.
  - La confirmación aclara que no se borra el historial.

### TSK-44 — Integrar servicios, rutas y pruebas del módulo Autor

- **ID:** TSK-44
- **Título:** Integrar servicios, rutas y pruebas del módulo Autor
- **Capa:** [Frontend]
- **Descripción técnica:** Crear `core/services/manuscript.service.ts`, modelos TypeScript y las rutas de `features/author`; implementar descarga `Blob`, query params persistentes y pruebas de listado, formulario, uploader e historial.
- **Criterios de aceptación:**
  - Las descargas usan `responseType: 'blob'` y no exponen rutas internas del volumen.
  - Los filtros y la paginación viven en la URL.
  - Las pruebas cubren validación de autores, reemplazo de borrador y baja lógica.

## Fase 3 — Editor y veredictos (HU-10, HU-11, HU-12, HU-13; RF-03, RF-07, RF-15, RF-17, RF-19)

### DevOps

### TSK-45 — Programar la expiración de asignaciones

- **ID:** TSK-45
- **Título:** Programar la expiración de asignaciones
- **Capa:** [DevOps]
- **Descripción técnica:** Agregar a `scripts/cron/gpc.cron` (o al cron documentado) la ejecución cada minuto de `docker compose exec -T backend python manage.py mark_expired_assignments`; redirigir logs y evitar ejecuciones solapadas.
- **Criterios de aceptación:**
  - La tarea no reasigna ni revoca automáticamente; solo marca `EXPIRED`.
  - Es idempotente y no genera avisos duplicados al Editor.
  - El corte exacto sigue calculándose con `due_at <= now()` en cada consulta.

### Backend

### TSK-46 — Crear el esquema de asignaciones y evaluaciones

- **ID:** TSK-46
- **Título:** Crear el esquema de asignaciones y evaluaciones
- **Capa:** [Backend]
- **Descripción técnica:** Crear `apps/reviews/models.py` con `Assignment` y `Evaluation`; incluir `due_at`, `status`, `revocation_reason`, `lock_version`, scores 1–5, recomendación, comentarios y `submitted_at`; agregar `CHECK (due_at = assigned_at + interval '20 days')`, unique de asignación activa, unique de evaluación por versión/revisor y trigger `prevent_final_evaluation_mutation`.
- **Criterios de aceptación:**
  - Solo puede existir una asignación `ACTIVE` por manuscrito.
  - `due_at` es exactamente 20 días después de `assigned_at`, validado en base de datos.
  - Una evaluación `FINAL` exige todos los scores, recomendación, comentarios y `submitted_at`; un trigger impide modificarla o eliminarla y la lógica de envío se completa en Fase 4.

### TSK-47 — Implementar APIs de bandeja, asignación y revocación del Editor

- **ID:** TSK-47
- **Título:** Implementar APIs de bandeja, asignación y revocación del Editor
- **Capa:** [Backend]
- **Descripción técnica:** Crear `apps/reviews/serializers.py`, `views.py`, `urls.py` y los endpoints `GET /api/editor/submissions/`, `GET /api/editor/submissions/{id}/`, `POST /api/editor/submissions/{id}/start-review/`, `GET /api/editor/reviewers/`, `GET/POST /api/editor/manuscripts/{id}/assignments/`, `POST /api/editor/assignments/{id}/revoke/` y `GET /api/editor/assignments/expired/`; integrar permisos de Editor y validación de conflicto de interés.
- **Criterios de aceptación:**
  - La bandeja solo muestra `SUBMITTED` y el detalle devuelve metadatos, autores, PDF e historial.
  - Crear una segunda asignación `ACTIVE` devuelve `409`; una asignación `EXPIRED` debe revocarse antes de reasignar.
  - El Editor que es autor o coautor no puede asignar ni registrar veredicto sobre ese manuscrito.

### TSK-48 — Implementar el servicio de asignación y reasignación

- **ID:** TSK-48
- **Título:** Implementar el servicio de asignación y reasignación
- **Capa:** [Backend]
- **Descripción técnica:** Crear `apps/reviews/services/assignments.py`; calcular `due_at` en PostgreSQL, validar área/disponibilidad/máximo de asignaciones, excluir autores y coautores, hacer atómica la transición a `UNDER_REVIEW`, revocar con motivo y auditar/notificar cada cambio.
- **Criterios de aceptación:**
  - La fecha límite se fija con `assigned_at + interval '20 days'` y no con el reloj del navegador.
  - La revocación anticipada exige conflicto, error de asignación o cuenta inhabilitada.
  - La reasignación no altera `current_round` ni `current_version`.

### TSK-49 — Implementar el comando de asignaciones vencidas

- **ID:** TSK-49
- **Título:** Implementar el comando de asignaciones vencidas
- **Capa:** [Backend]
- **Descripción técnica:** Crear `apps/reviews/management/commands/mark_expired_assignments.py`; seleccionar `ACTIVE` con `due_at <= now()`, cambiar a `EXPIRED`, registrar evento/auditoría y notificar al Editor una sola vez.
- **Criterios de aceptación:**
  - No cambia automáticamente a `REVOKED` ni crea una nueva asignación.
  - Ejecutarlo dos veces no duplica notificaciones ni eventos.
  - El comando deja intactos evaluaciones y borradores existentes.

### TSK-50 — Crear modelos de veredicto y entrada de catálogo

- **ID:** TSK-50
- **Título:** Crear modelos de veredicto y entrada de catálogo
- **Capa:** [Backend]
- **Descripción técnica:** Crear `Verdict` y `CatalogEntry` en `apps/publications/models.py`; agregar `decision`, `justification`, `observations`, `previous_verdict_id`, `public_file_path`, `published_at`, `unpublished_at`; crear la FK diferible `CorrectionRound.opened_by_verdict_id`, los triggers append-only del veredicto y el índice único de catálogo activo.
- **Criterios de aceptación:**
  - `REJECTED` exige justificación y `REQUIRES_CORRECTIONS` exige observaciones; la ronda abierta conserva la referencia al veredicto que la originó.
  - El veredicto es append-only y no admite `UPDATE` ni `DELETE`.
  - Solo puede existir una entrada de catálogo activa por manuscrito y la copia pública no es un enlace duro al original.

### TSK-51 — Implementar el flujo normal de veredicto y publicación

- **ID:** TSK-51
- **Título:** Implementar el flujo normal de veredicto y publicación
- **Capa:** [Backend]
- **Descripción técnica:** Crear `apps/publications/services/verdicts.py` y `catalog.py`; validar evaluación final, registrar veredicto, actualizar estado, abrir ronda o crear/activar catálogo, generar copia pública sanitizada y auditar en una sola transacción.
- **Criterios de aceptación:**
  - `ACCEPTED` publica en catálogo de forma síncrona; `REJECTED` no publica; `REQUIRES_CORRECTIONS` abre la siguiente ronda.
  - Un segundo veredicto normal para la misma versión devuelve `409`.
  - Si falla la copia pública o la auditoría, el veredicto no se confirma.

### TSK-52 — Implementar endpoints de veredicto y evaluaciones del Editor

- **ID:** TSK-52
- **Título:** Implementar endpoints de veredicto y evaluaciones del Editor
- **Capa:** [Backend]
- **Descripción técnica:** Crear `POST/GET /api/editor/manuscripts/{id}/verdicts/` y `GET /api/editor/manuscripts/{id}/evaluations/`; aplicar `If-Match`, `Idempotency-Key`, permiso de Editor sin conflicto y serializador con identidad del Revisor solo para el Editor.
- **Criterios de aceptación:**
  - No se registra veredicto sin evaluación `FINAL` o con manuscrito dado de baja.
  - La respuesta incluye historial de veredictos, pero nunca permite editarlos.
  - Si la auditoría falla, se devuelve `503` y no se publica el catálogo.

### TSK-53 — Probar asignaciones, veredictos y publicación

- **ID:** TSK-53
- **Título:** Probar asignaciones, veredictos y publicación
- **Capa:** [Backend]
- **Descripción técnica:** Crear pruebas en `backend/tests/reviews/` y `backend/tests/publications/` para asignación única, plazo exacto, revocación, reasignación, veredicto, ronda, catálogo y concurrencia.
- **Criterios de aceptación:**
  - Se cubre el límite exacto de 20 días y el `409` por segunda asignación/veredicto.
  - `ACCEPTED` aparece en catálogo, `REJECTED` no y `REQUIRES_CORRECTIONS` incrementa la ronda.
  - Un fallo de auditoría revierte la publicación y devuelve `503`.

### Frontend

### TSK-54 — Crear bandeja y detalle de envíos del Editor

- **ID:** TSK-54
- **Título:** Crear bandeja y detalle de envíos del Editor
- **Capa:** [Frontend]
- **Descripción técnica:** Crear `features/editor/submission-inbox/` y `submission-detail/`; mostrar código, título, autor, área, fecha, versión y ronda; permitir filtros, orden, paso a revisión y consulta de PDF/historial.
- **Criterios de aceptación:**
  - La bandeja solo muestra `SUBMITTED` y el detalle completo solo está disponible para Editor.
  - El paso a revisión se confirma y refleja el estado actualizado.
  - No se muestran datos de auditoría global ni acciones de Administrador.

### TSK-55 — Crear selector de revisores y diálogos de asignación/revocación

- **ID:** TSK-55
- **Título:** Crear selector de revisores y diálogos de asignación/revocación
- **Capa:** [Frontend]
- **Descripción técnica:** Crear `reviewer-picker/`, `assign-reviewer-dialog/` y `revoke-assignment-dialog/`; mostrar elegibilidad por área, disponibilidad y conflicto, fecha límite calculada y motivo obligatorio de revocación.
- **Criterios de aceptación:**
  - Cuando no hay revisores elegibles se muestra la causa, no una lista vacía sin explicación.
  - El diálogo advierte si ya existe una asignación activa y muestra el `409`.
  - La fecha límite mostrada coincide con la calculada por el backend.

### TSK-56 — Crear el formulario de veredicto normal

- **ID:** TSK-56
- **Título:** Crear el formulario de veredicto normal
- **Capa:** [Frontend]
- **Descripción técnica:** Crear `features/editor/verdict-form/`; permitir Aceptado, Rechazado o Requiere Correcciones; exigir justificación para rechazo o separación de la recomendación y observaciones para correcciones; mostrar la recomendación del Revisor sin permitir editarla.
- **Criterios de aceptación:**
  - El formulario no envía si faltan los campos obligatorios según la decisión.
  - Se advierte cuando el Editor se aparta de la recomendación del Revisor.
  - El veredicto anterior nunca se edita ni se sobrescribe.

### TSK-57 — Integrar rutas, servicios y pruebas del módulo Editor

- **ID:** TSK-57
- **Título:** Integrar rutas, servicios y pruebas del módulo Editor
- **Capa:** [Frontend]
- **Descripción técnica:** Crear `EditorService`, modelos de asignación/veredicto, `ExpiredAssignmentsComponent` y las rutas `/app/editor/**`; agregar pruebas de bandeja, selector, asignación, revocación y veredicto.
- **Criterios de aceptación:**
  - Las rutas exigen rol Editor y no permiten acceso por URL a manuscritos ajenos.
  - La vista de vencidos muestra `due_at <= now()` y no reasigna automáticamente.
  - Las pruebas cubren `409` de asignación duplicada y validaciones de veredicto.

## Fase 4 — Revisor y doble ciego (HU-14, HU-15, HU-16, HU-17; RF-04, RF-09, RF-18; CA-HU-16-06)

### DevOps

### TSK-58 — Verificar aislamiento del volumen y acceso al PDF sanitizado

- **ID:** TSK-58
- **Título:** Verificar aislamiento del volumen y acceso al PDF sanitizado
- **Capa:** [DevOps]
- **Descripción técnica:** Revisar `docker-compose.yml` y `nginx/conf.d/default.conf` para confirmar `media_data:ro` en `web`, `/_protected/` y `/_catalog/` internos, `deny all` en `/media/` y ausencia de listados de directorio; agregar una prueba de humo de acceso directo.
- **Criterios de aceptación:**
  - Una petición externa a `/_protected/...`, `/_catalog/...` o `/media/...` no entrega archivos.
  - El backend sigue siendo el único que escribe en el volumen.
  - El endpoint del Revisor solo puede resolver `sanitized.pdf`, nunca `original.pdf`.

### Backend

### TSK-59 — Crear el modelo de incidentes confidenciales

- **ID:** TSK-59
- **Título:** Crear el modelo de incidentes confidenciales
- **Capa:** [Backend]
- **Descripción técnica:** Crear `IncidentReport` en `apps/reviews/models.py` con assignment, manuscript, reporter, tipo, descripción, estado, resolución, ronda y auditoría; agregar `CHECK` de resolución, índice único parcial de incidente abierto e índice por estado/fecha.
- **Criterios de aceptación:**
  - Solo puede existir un incidente `OPEN` por asignación; un segundo devuelve `409`.
  - Un incidente `RESOLVED` exige `resolution` y `resolved_at`.
  - El reporte no modifica el PDF, la evaluación ni el estado del manuscrito por sí solo.

### TSK-60 — Implementar QuerySet, serializadores y permisos del Revisor

- **ID:** TSK-60
- **Título:** Implementar QuerySet, serializadores y permisos del Revisor
- **Capa:** [Backend]
- **Descripción técnica:** Implementar `ReviewerAssignmentQuerySet.for_reviewer()` en `apps/reviews/querysets.py` o manager; crear `ReviewerManuscriptSerializer` y `ReviewerVersionSerializer`; aplicar `IsAssignedReviewer` y `404` uniforme; excluir autores, coautores y `created_by`.
- **Criterios de aceptación:**
  - La respuesta no contiene `authors`, `email`, `affiliation`, `created_by`, `metadata_snapshot`, `original_filename`, rutas ni hashes internos.
  - Una asignación ajena o un manuscrito dado de baja devuelve `404`.
  - Un Revisor que es autor o coautor no ve el manuscrito ni puede evaluarlo.

### TSK-61 — Implementar asignaciones, detalle y descarga del Revisor

- **ID:** TSK-61
- **Título:** Implementar asignaciones, detalle y descarga del Revisor
- **Capa:** [Backend]
- **Descripción técnica:** Crear `apps/reviews/views.py` y `urls.py` para `GET /api/reviewer/assignments/`, `GET /api/reviewer/assignments/{id}/` y `GET /api/reviewer/assignments/{id}/document/`; usar el QuerySet por revisor, validar `ACTIVE` para descarga y responder con `X-Accel-Redirect` a `sanitized.pdf`.
- **Criterios de aceptación:**
  - La bandeja solo muestra asignaciones propias y distingue pendiente, en plazo, vencida, evaluada y revocada.
  - La descarga usa un nombre genérico y nunca resuelve `original.pdf`; una asignación no activa devuelve `410`.
  - La descarga se audita y falla con `503` si la auditoría no está disponible.

### TSK-62 — Implementar borrador y envío final de evaluación

- **ID:** TSK-62
- **Título:** Implementar borrador y envío final de evaluación
- **Capa:** [Backend]
- **Descripción técnica:** Crear `GET/PUT /api/reviewer/assignments/{id}/evaluation/` y `POST .../evaluation/submit/`; implementar `apps/reviews/services/evaluations.py`, `lock_version`, validación de scores 1–5, recomendación, comentarios y corte `now() < due_at`; completar la asignación y notificar al Editor.
- **Criterios de aceptación:**
  - El borrador es privado y solo editable por el Revisor dueño de una asignación `ACTIVE`.
  - En `now() == due_at` o después, el envío devuelve `410` y conserva el borrador sin convertirlo en final.
  - Una evaluación `FINAL` no admite `PUT` posterior y no puede borrarse.

### TSK-63 — Implementar conflicto de interés e historial del Revisor

- **ID:** TSK-63
- **Título:** Implementar conflicto de interés e historial del Revisor
- **Capa:** [Backend]
- **Descripción técnica:** Crear `POST /api/reviewer/assignments/{id}/conflict/`, `GET /api/reviewer/evaluations/` y `GET /api/reviewer/evaluations/{id}/`; bloquear la evaluación al declarar conflicto, notificar al Editor y devolver solo datos anonimizados, incluido el resultado editorial cuando exista.
- **Criterios de aceptación:**
  - Declarar conflicto impide guardar o enviar la evaluación y no revela el autor.
  - El historial solo incluye evaluaciones propias, en modo lectura y con el resultado del manuscrito cuando el Editor ya lo registró.
  - Ni el historial ni las notificaciones incluyen identidad de Autores o comentarios confidenciales.

### TSK-64 — Implementar reporte de fuga y resolución editorial

- **ID:** TSK-64
- **Título:** Implementar reporte de fuga y resolución editorial
- **Capa:** [Backend]
- **Descripción técnica:** Crear `POST /api/reviewer/assignments/{id}/identity-leak/`, `GET /api/editor/incidents/` y `POST /api/editor/incidents/{id}/resolve/`; implementar `apps/reviews/services/incidents.py` con `REQUEST_ANONYMIZED_VERSION`, `REASSIGN` y `DISMISS`, apertura de ronda, revocación y auditoría.
- **Criterios de aceptación:**
  - Solo el Revisor dueño de una asignación `ACTIVE` puede reportar; el reporte es privado y no cambia la evaluación.
  - `REQUEST_ANONYMIZED_VERSION` deja el manuscrito en `REQUIRES_CORRECTIONS`, abre ronda y guarda `correction_round_id`; `REASSIGN` revoca y mantiene `UNDER_REVIEW`; `DISMISS` no cambia estado.
  - La resolución se registra una sola vez, devuelve `409` al repetir y nunca expone al Revisor ante el Autor.

### TSK-65 — Probar doble ciego, evaluación e incidentes

- **ID:** TSK-65
- **Título:** Probar doble ciego, evaluación e incidentes
- **Capa:** [Backend]
- **Descripción técnica:** Crear pruebas en `backend/tests/reviews/` para serializadores, PDF sanitizado, notificaciones, evaluación, conflicto, plazo, incidentes y resolución; usar `pikepdf` y dos conexiones para concurrencia.
- **Criterios de aceptación:**
  - La respuesta del Revisor no contiene autores, correos, filiaciones, `created_by`, `metadata_snapshot` ni nombre original.
  - El PDF sanitizado no contiene `/Info`, XMP, `/EmbeddedFiles`, `/JavaScript`, `/OpenAction`, `/AA` ni `/Launch`.
  - El envío en `due_at` devuelve `410` y la evaluación final no puede modificarse.

### Frontend

### TSK-66 — Crear asignaciones, detalle anonimizado y descarga del Revisor

- **ID:** TSK-66
- **Título:** Crear asignaciones, detalle anonimizado y descarga del Revisor
- **Capa:** [Frontend]
- **Descripción técnica:** Crear `features/reviewer/assignment-list/`, `assignment-detail/` y `deadline-countdown/`; mostrar código, título, resumen, área, ronda, versión, plazo y PDF sanitizado; no renderizar autores, filiaciones ni nombre original.
- **Criterios de aceptación:**
  - El detalle no contiene campos de autoría ni enlaces al PDF original.
  - El contador usa la fecha/hora exacta del backend y deshabilita el envío al vencer.
  - La descarga usa el endpoint sanitizado y un nombre genérico.

### TSK-67 — Crear el formulario de evaluación estructurado

- **ID:** TSK-67
- **Título:** Crear el formulario de evaluación estructurado
- **Capa:** [Frontend]
- **Descripción técnica:** Crear `features/reviewer/evaluation-form/`; implementar scores de originalidad, metodología, claridad, relevancia y ética (1–5), recomendación, comentarios para el Autor, comentarios confidenciales, conflicto, guardado de borrador y envío final.
- **Criterios de aceptación:**
  - El envío final exige todos los scores, recomendación, comentarios para el Autor y la declaración de conflicto.
  - El borrador se puede guardar sin completar todos los campos y no se comparte con el Autor.
  - El formulario maneja `If-Match` y muestra `409`/`410` sin perder el texto.

### TSK-68 — Crear diálogos de conflicto y fuga de identidad

- **ID:** TSK-68
- **Título:** Crear diálogos de conflicto y fuga de identidad
- **Capa:** [Frontend]
- **Descripción técnica:** Crear `features/reviewer/conflict-dialog/` e `identity-leak-dialog/`; pedir confirmación/motivo, enviar el reporte y actualizar el estado local sin revelar el reporte al Autor.
- **Criterios de aceptación:**
  - Declarar conflicto bloquea el formulario de evaluación.
  - El reporte de fuga se presenta como confidencial y no incluye datos del Revisor en la notificación al Autor.
  - Un error de red no muestra el reporte como enviado.

### TSK-69 — Integrar historial, servicios, rutas y pruebas del Revisor

- **ID:** TSK-69
- **Título:** Integrar historial, servicios, rutas y pruebas del Revisor
- **Capa:** [Frontend]
- **Descripción técnica:** Crear `evaluation-history/`, `ReviewerService`, modelos TypeScript y rutas `/app/reviewer/**`; agregar pruebas de no visualización de autoría, descarga sanitizada, plazo y envío final.
- **Criterios de aceptación:**
  - Ningún componente del Revisor referencia campos de autor.
  - El historial es solo lectura y no muestra comentarios confidenciales.
  - Las pruebas cubren el bloqueo por vencimiento y el manejo de `409`/`410`.

### TSK-70 — Crear la bandeja de incidentes del Editor

- **ID:** TSK-70
- **Título:** Crear la bandeja de incidentes del Editor
- **Capa:** [Frontend]
- **Descripción técnica:** Crear `features/editor/incident-list/`; listar reportes abiertos/resueltos y permitir `REQUEST_ANONYMIZED_VERSION`, `REASSIGN` o `DISMISS` con confirmación; integrar en `EditorService` y la ruta `/app/editor/incidents`.
- **Criterios de aceptación:**
  - El Editor ve el reporte confidencial, pero no se expone al Autor.
  - Cada resolución pide confirmación y refleja el estado actualizado.
  - Un segundo intento de resolución muestra `409`.

## Fase 5 — Catálogo, auditoría y avisos (HU-18, HU-19, HU-20, HU-21, HU-24; RF-08, RF-11, RF-13, RF-20; CA-HU-13-12)

### DevOps

### TSK-71 — Programar avisos, limpieza e integridad

- **ID:** TSK-71
- **Título:** Programar avisos, limpieza e integridad
- **Capa:** [DevOps]
- **Descripción técnica:** Agregar a `scripts/cron/gpc.cron` la ejecución cada minuto de `send_pending_notifications`, diaria de `cleanup_idempotency_keys` y mensual de `verify_integrity`; completar SMTP en `.env.example` y documentar reintentos.
- **Criterios de aceptación:**
  - Los comandos se ejecutan dentro de `backend` y no exponen secretos en logs.
  - La limpieza solo elimina claves vencidas.
  - La verificación mensual reporta discrepancias sin modificar archivos ni auditoría.

### TSK-72 — Restringir privilegios de base de datos sobre auditoría

- **ID:** TSK-72
- **Título:** Restringir privilegios de base de datos sobre auditoría
- **Capa:** [DevOps]
- **Descripción técnica:** Crear el script de inicialización de PostgreSQL (`docker-entrypoint-initdb.d/01_privileges.sql` o migración equivalente) para que el usuario de aplicación tenga `INSERT`/`SELECT` sobre `audit_audit_log`, pero no `UPDATE` ni `DELETE`; verificar el respaldo diario a las 02:15.
- **Criterios de aceptación:**
  - El usuario de aplicación no puede alterar ni borrar auditoría, además del trigger.
  - El backend conserva permisos de escritura en las tablas operativas.
  - La configuración se aplica en una base nueva y queda documentada para producción.

### Backend

### TSK-73 — Implementar la consulta administrativa de auditoría

- **ID:** TSK-73
- **Título:** Implementar la consulta administrativa de auditoría
- **Capa:** [Backend]
- **Descripción técnica:** Crear `apps/audit/serializers.py`, `views.py` y `urls.py` para `GET /api/admin/audit/` y `GET /api/admin/audit/{id}/`; filtros por fecha, actor, acción, manuscrito y resultado; `AdminAuditSerializer` sin PII ni contenido; dejar el detalle preparado para la elegibilidad de corrección que integra TSK-77.
- **Criterios de aceptación:**
  - Solo `ADMIN` accede y cada consulta de auditoría se audita.
  - La respuesta no incluye contenido del manuscrito, comentarios confidenciales ni datos personales innecesarios.
  - El detalle no infiere permisos de escritura; la habilitación de corrección se calcula y expone en TSK-77.

### TSK-74 — Implementar catálogo público y descarga pública

- **ID:** TSK-74
- **Título:** Implementar catálogo público y descarga pública
- **Capa:** [Backend]
- **Descripción técnica:** Crear `GET /api/catalog/`, `GET /api/catalog/{code}/` y `GET /api/catalog/{code}/document/`; usar `PublicCatalogSerializer` y `CatalogService`; filtrar `status=ACCEPTED`, `is_active=true` y entrada de catálogo activa; entregar `/_catalog/...` con `X-Accel-Redirect`.
- **Criterios de aceptación:**
  - Sin autenticación, el catálogo no muestra manuscritos en revisión, rechazados, dados de baja, evaluaciones, revisores, historial ni auditoría.
  - La búsqueda cubre título, autores, palabras clave, área y resumen, con paginación y filtros.
  - Un artículo no aceptado devuelve `404`; un PDF retirado devuelve `410`; toda descarga se audita.

### TSK-75 — Implementar notificaciones de panel y correo

- **ID:** TSK-75
- **Título:** Implementar notificaciones de panel y correo
- **Capa:** [Backend]
- **Descripción técnica:** Crear `apps/notifications/models.py`, `services.py`, `serializers.py`, `views.py` y `urls.py`; implementar `GET /api/notifications/`, `PATCH /api/notifications/{id}/read/` y `POST /api/notifications/read-all/`; usar `event_key` único, canales `PANEL`/`EMAIL` y payload sanitizado.
- **Criterios de aceptación:**
  - Cada destinatario recibe una sola notificación por evento.
  - Las notificaciones al Revisor no contienen datos de Autores y las del Autor no contienen datos del Revisor.
  - El panel funciona aunque el correo falle; el estado queda `PENDING` o `FAILED` con reintento.

### TSK-76 — Implementar comandos de avisos, limpieza e integridad

- **ID:** TSK-76
- **Título:** Implementar comandos de avisos, limpieza e integridad
- **Capa:** [Backend]
- **Descripción técnica:** Crear `apps/notifications/management/commands/send_pending_notifications.py`, `apps/publications/management/commands/cleanup_idempotency_keys.py` y `apps/audit/management/commands/verify_integrity.py`; procesar `PENDING`/`FAILED`, aplicar backoff, actualizar intentos/errores y recalcular hashes de PDFs y de la cadena de auditoría.
- **Criterios de aceptación:**
  - Un aviso enviado no se reenvía en la siguiente ejecución y un fallo SMTP se registra como `FAILED` con backoff.
  - La limpieza de idempotencia no toca claves vigentes.
  - `verify_integrity` reporta discrepancias sin modificar archivos ni auditoría y devuelve un código de salida distinto de cero cuando las encuentra.

### TSK-77 — Implementar autorización administrativa de corrección de veredicto

- **ID:** TSK-77
- **Título:** Implementar autorización administrativa de corrección de veredicto
- **Capa:** [Backend]
- **Descripción técnica:** Crear `VerdictCorrection` en `apps/publications/models.py`, `POST /api/admin/verdicts/{id}/authorize-correction/` y extender `AdminAuditSerializer`/detalle con `can_authorize_correction`; exigir `Idempotency-Key` y validar rol `ADMIN`, `reason` de 10–1000 caracteres, veredicto más reciente, ausencia de versión posterior y una sola autorización activa; auditar `VERDICT_CORRECTION_AUTHORIZED`.
- **Criterios de aceptación:**
  - El Administrador no modifica el veredicto original ni accede a manuscritos, evaluaciones o PDF.
  - Un veredicto desactualizado, con versión posterior o con autorización activa devuelve `409`.
  - `can_authorize_correction` solo es `true` para el veredicto más reciente sin versión posterior; la vista administrativa no expone autores ni comentarios.

### TSK-78 — Integrar la corrección en el veredicto del Editor

- **ID:** TSK-78
- **Título:** Integrar la corrección en el veredicto del Editor
- **Capa:** [Backend]
- **Descripción técnica:** Extender `apps/publications/services/verdicts.py` y el endpoint de veredictos para consumir `VerdictCorrection` con `select_for_update()`; derivar `previous_verdict_id`, crear la nueva decisión, marcar la autorización consumida y actualizar estado, catálogo y ronda en una transacción.
- **Criterios de aceptación:**
  - Sin autorización activa, un segundo veredicto devuelve `409` aunque el cliente envíe `previous_verdict_id`.
  - La corrección conserva el original, no cambia `current_version` y registra `VERDICT_CORRECTED` con ambos identificadores.
  - Si falla cualquier paso, la autorización no se consume y el veredicto no se crea.

### TSK-79 — Probar catálogo, auditoría, avisos y corrección

- **ID:** TSK-79
- **Título:** Probar catálogo, auditoría, avisos y corrección
- **Capa:** [Backend]
- **Descripción técnica:** Crear pruebas en `backend/tests/publications/`, `backend/tests/audit/` y `backend/tests/notifications/` para catálogo, descarga, auditoría global, idempotencia de avisos y flujo de corrección.
- **Criterios de aceptación:**
  - El catálogo solo devuelve aceptados activos y retira el artículo de inmediato tras la baja.
  - La autorización de corrección se consume una sola vez y ambas decisiones quedan en historial/auditoría.
  - La cadena de auditoría verifica y las notificaciones no duplican eventos.

### Frontend

### TSK-80 — Crear búsqueda, listado y ficha del catálogo público

- **ID:** TSK-80
- **Título:** Crear búsqueda, listado y ficha del catálogo público
- **Capa:** [Frontend]
- **Descripción técnica:** Crear `features/catalog/catalog-search/`, `catalog-list/` y `catalog-detail/`; implementar filtros combinados, paginación, autores, filiaciones, resumen y descarga pública; registrar `/catalog` y `/catalog/:code` sin guard.
- **Criterios de aceptación:**
  - El catálogo es público y no envía JWT.
  - Solo muestra artículos aceptados y activos; un artículo no disponible devuelve `404`/`410` visual controlado.
  - La ficha no incluye evaluaciones, revisores, historial ni auditoría.

### TSK-81 — Crear auditoría global y filtros del Administrador

- **ID:** TSK-81
- **Título:** Crear auditoría global y filtros del Administrador
- **Capa:** [Frontend]
- **Descripción técnica:** Crear `features/admin/audit-log-list/`, `audit-log-detail/` y `audit-filters/`; mostrar actor, rol, acción, entidad, resultado, fecha, hash y `can_authorize_correction`; registrar `/app/admin/audit` y `/app/admin/audit/:id`.
- **Criterios de aceptación:**
  - La tabla es paginada y filtrable por fecha, actor, acción, manuscrito y resultado.
  - El detalle no muestra contenido del manuscrito ni datos personales innecesarios.
  - La acción “Habilitar corrección” solo aparece si el backend la autoriza.

### TSK-82 — Crear diálogo de corrección y estado de veredicto corregido

- **ID:** TSK-82
- **Título:** Crear diálogo de corrección y estado de veredicto corregido
- **Capa:** [Frontend]
- **Descripción técnica:** Crear `features/admin/verdict-correction-dialog/` y extender `VerdictFormComponent`; el Administrador introduce un motivo de 10–1000 caracteres; el Editor ve la autorización activa, la decisión/fecha original y confirma una nueva decisión sin editar la anterior.
- **Criterios de aceptación:**
  - El motivo es obligatorio y el diálogo muestra que la decisión anterior se conserva.
  - El formulario del Editor no precarga ni permite modificar el veredicto original.
  - Tras consumir la autorización, la acción desaparece y el historial muestra ambas decisiones.

### TSK-83 — Crear panel y lista de notificaciones

- **ID:** TSK-83
- **Título:** Crear panel y lista de notificaciones
- **Capa:** [Frontend]
- **Descripción técnica:** Crear `features/notifications/notification-list/`, `notification-item/`, conectar `NotificationBellComponent` y registrar `/app/notifications`; listar avisos propios, marcar uno/todos como leídos y actualizar el contador sin recargar la página.
- **Criterios de aceptación:**
  - Solo se muestran avisos del usuario autenticado.
  - El contador de no leídos se actualiza tras marcar como leído.
  - Los avisos no exponen identidades cruzadas ni contenido confidencial.

### TSK-84 — Probar catálogo, auditoría, corrección y avisos en frontend

- **ID:** TSK-84
- **Título:** Probar catálogo, auditoría, corrección y avisos en frontend
- **Capa:** [Frontend]
- **Descripción técnica:** Crear pruebas Jasmine/Karma para catálogo público, filtros de auditoría, diálogo de corrección, formulario de veredicto con autorización y notificaciones; simular `403`, `404`, `409` y `410`.
- **Criterios de aceptación:**
  - El catálogo no muestra acciones internas ni datos de revisión.
  - La corrección no se puede enviar sin motivo y no edita el veredicto original.
  - El contador de avisos y el estado leído se actualizan correctamente.

## Fase 6 — Endurecimiento (todas las HU/RF)

### DevOps

### TSK-85 — Completar el pipeline de calidad

- **ID:** TSK-85
- **Título:** Completar el pipeline de calidad
- **Capa:** [DevOps]
- **Descripción técnica:** Extender `.github/workflows/ci.yml` con `pytest` y cobertura mínima, `ng test`, `ng build --configuration production`, `pip-audit`, `npm audit`, `docker compose config`, migraciones y verificación de que no se usa SQLite.
- **Criterios de aceptación:**
  - El pipeline falla con cobertura menor al 80% en dominio/permisos, errores de tipos, migraciones pendientes o vulnerabilidades críticas/altas sin mitigar.
  - No se ejecutan pruebas contra SQLite ni se usan secretos de producción.
  - Los artefactos de cobertura y build quedan disponibles para revisión.

### TSK-86 — Ejecutar prueba de carga de 50 MB y concurrencia

- **ID:** TSK-86
- **Título:** Ejecutar prueba de carga de 50 MB y concurrencia
- **Capa:** [DevOps]
- **Descripción técnica:** Crear un script de carga (por ejemplo `scripts/load_test.sh` o `tests/load/`) que suba PDFs de 50 MB a través de Nginx y simule 50 usuarios concurrentes en login, catálogo y descargas.
- **Criterios de aceptación:**
  - Nginx acepta 50 MB y rechaza cuerpos mayores a 60 MB sin bloquear el backend.
  - Los timeouts de 120 s y el buffer en disco funcionan bajo carga.
  - No se superan los límites de memoria definidos para Gunicorn/PostgreSQL.

### TSK-87 — Verificar restauración, integridad y superficie expuesta

- **ID:** TSK-87
- **Título:** Verificar restauración, integridad y superficie expuesta
- **Capa:** [DevOps]
- **Descripción técnica:** Ejecutar `scripts/restore.sh` en un entorno aislado, `python manage.py verify_integrity`, y pruebas de red para `/_protected/`, `/_catalog/`, `/media/`, puertos de `db`/`backend` y cabeceras TLS.
- **Criterios de aceptación:**
  - La restauración reconstruye base, PDFs y auditoría con checksums válidos.
  - Las ubicaciones internas y `/media/` no responden desde el exterior.
  - Solo `web` expone 80/443 y las cabeceras de seguridad están presentes.

### TSK-88 — Documentar runbook de piloto y aceptación operativa

- **ID:** TSK-88
- **Título:** Documentar runbook de piloto y aceptación operativa
- **Capa:** [DevOps]
- **Descripción técnica:** Actualizar `README.md` y crear el runbook de despliegue, TLS, backups, restauración, cron, incidentes, credenciales institucionales y criterios de aceptación del piloto; incluir la verificación de las cinco decisiones Q1–Q5.
- **Criterios de aceptación:**
  - Un operador puede desplegar, respaldar y restaurar sin conocimiento previo del código.
  - El runbook documenta límites 50/60 MB, volumen, PostgreSQL y `X-Accel-Redirect`.
  - No contiene secretos reales ni instrucciones de MySQL.

### Backend

### TSK-89 — Auditar seguridad, IDOR y no fuga de identidad

- **ID:** TSK-89
- **Título:** Auditar seguridad, IDOR y no fuga de identidad
- **Capa:** [Backend]
- **Descripción técnica:** Revisar y corregir permisos por objeto, serializadores, QuerySets, descargas, notificaciones, auditoría y endpoints administrativos; ejecutar pruebas de acceso ajeno, rol retirado, doble ciego y fuga por PDF.
- **Criterios de aceptación:**
  - Todo acceso a manuscrito, evaluación o PDF ajeno devuelve `404`, salvo rol sin módulo que devuelve `403`.
  - El Revisor no recibe autores, filiaciones, correos, `metadata_snapshot` ni nombre original.
  - El Administrador no obtiene acceso a manuscritos, evaluaciones o PDF por la API.

### TSK-90 — Optimizar consultas y consolidar cobertura backend

- **ID:** TSK-90
- **Título:** Optimizar consultas y consolidar cobertura backend
- **Capa:** [Backend]
- **Descripción técnica:** Revisar `select_related`/`prefetch_related`, índices de búsqueda, paginación, cadena de auditoría y bloqueos de asignación/veredicto; ejecutar `pytest --cov` y corregir consultas N+1.
- **Criterios de aceptación:**
  - Las consultas de bandeja, catálogo, historial y auditoría no generan N+1 evidente.
  - La cobertura de dominio y permisos alcanza al menos 80%.
  - Los bloqueos de concurrencia no permiten dos asignaciones activas ni dos veredictos normales.

### Frontend

### TSK-91 — Ejecutar E2E Playwright de los flujos críticos

- **ID:** TSK-91
- **Título:** Ejecutar E2E Playwright de los flujos críticos
- **Capa:** [Frontend]
- **Descripción técnica:** Crear pruebas Playwright en `frontend/e2e/` contra Docker Compose para los diez flujos del plan: login multirrol, autor, editor, revisor, catálogo, baja, auditoría, corrección administrativa, fuga de identidad y notificaciones.
- **Criterios de aceptación:**
  - El flujo completo publica un artículo, lo retira y conserva historial/auditoría.
  - La corrección administrativa conserva el veredicto original y la fuga de identidad no revela al Revisor.
  - Las pruebas no dependen de datos residuales y limpian su estado.

### TSK-92 — Validar accesibilidad, responsive y build de producción

- **ID:** TSK-92
- **Título:** Validar accesibilidad, responsive y build de producción
- **Capa:** [Frontend]
- **Descripción técnica:** Revisar foco, teclado, etiquetas `aria-*`, contraste, diálogos, tablas y formularios largos; ejecutar `ng build --configuration production` y pruebas en resoluciones de escritorio/tablet.
- **Criterios de aceptación:**
  - Contraste WCAG AA, foco visible y navegación completa por teclado en login, panel, formularios y catálogo.
  - No hay desbordes ni acciones inaccesibles en las resoluciones objetivo.
  - El build de producción no incluye `sourceMap` ni dependencias de desarrollo.
