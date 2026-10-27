# Matriz de Cumplimiento — TSK-01 a TSK-44 (Fases 0, 1 y 2)

**Archivo:** `compliance.md`
**Fecha de la auditoría:** 26 de octubre de 2026
**Rama / commit auditado:** `dev/jostin-setup` @ `ad22b2c`
**Contrastado contra:** `.spec-kit/specify.md`, `.spec-kit/plan.md`, `.spec-kit/tasks.md`, `.spec-kit/constitution.md`, `.spec-kit/clarify.md`
**Alcance:** solo lectura. No se modificó código, configuración ni contenedores existentes.

---

## 0. Método y evidencia

| Evidencia | Resultado |
|---|---|
| Pruebas backend (pytest, contenedor efímero con dependencias de desarrollo contra el PostgreSQL 16 del proyecto) | **677 pasan, 1 omitida**. La omitida es `test_health_returns_503_when_volume_is_read_only`, que se salta cuando se ejecuta como `root`; no es un fallo del código. |
| Pruebas frontend (`ng test`, Vitest) | **36 archivos, 559 pruebas, todas pasan**. |
| Compilación `ng build --configuration production` | **Correcta** (1 advertencia NG8113, ver D-13). |
| Lectura de código | `docker-compose.yml`, `nginx/`, `backend/Dockerfile`, `frontend/Dockerfile`, `.env.example`, `scripts/`, `.github/workflows/ci.yml`, settings, servicios de `users` y `publications`, migraciones, rutas y servicios Angular. |
| Contenedores en ejecución | `db` y `backend` saludables; el contenedor `backend` contiene `versions.py` y `submission.py`, es decir, **sí está actualizado** con el código de la Fase 2. |

**Cómo leer los porcentajes.** Es la proporción de criterios de aceptación de cada tarea que se verificó como cumplida (por lectura de código y/o pruebas ejecutadas). Es una estimación del auditor, no una métrica automática.

**Estados.** ✅ Cumple · 🟡 Cumple parcialmente · ❌ No cumple · ⏳ Pendiente por diseño (depende de una fase posterior).

**No verificado en esta auditoría** (requiere entorno o acción que no se ejecutó): contraste WCAG AA real, un `413` extremo a extremo a través de Nginx con un PDF de 60 MB, la restauración de humo de `restore.sh`, y el comportamiento TLS (no existe, ver D-02).

---

## 1. Tabla resumen de la Matriz de Cumplimiento

| Módulo / Feature | Tareas | Requisitos cubiertos | Estado | Cumplimiento | Observaciones / Deuda técnica |
|---|---|---|---|---|---|
| Estructura del repositorio y Docker Compose | TSK-01, 02 | Constitución §1; plan §5.1–5.2 | 🟡 | 80 % | `db` publica `5432` y `adminer` publica `8888` (commit `ad22b2c`); `web` solo publica `80`. Contradice el criterio «`db`/`backend` no publican puertos; solo `web` expone 80/443». D-03. |
| Imagen del backend y Gunicorn | TSK-03 | Plan §5; Constitución §2 | ✅ | 95 % | Usuario no root, Gunicorn en `0.0.0.0:8000`, sin MySQL/SQLite. La imagen de producción copia `tests/` pero no instala `pytest`. D-08. |
| Nginx: proxy, estáticos, ubicaciones internas, TLS | TSK-04 | Plan §5.3, §4.6; RNF-06 | 🟡 | 60 % | Cumple `client_max_body_size 60m`, timeouts de 120 s, `/_protected/` y `/_catalog/` internas, `deny all` en `/media/`, PDF sin compresión, CSP. **No cumple TLS**: solo `listen 80`, sin redirección a HTTPS ni TLS 1.2/1.3. D-02. |
| Variables de entorno, secretos y cookies | TSK-05, 16 | Plan §5.4, §6.1, §6.6 | ✅ | 90 % | `.env.example` completo, `check_env.sh` y `production.py` fallan con mensaje claro, `.env` con permisos `0600`. `COOKIE_SECURE=1` sin TLS disponible. D-06. |
| Volumen `media_data` y límites de carga | TSK-06, 29 | Plan §4.1–4.2; clarify Q1, Q2 | ✅ | 95 % | Estructura `private/drafts`, `private/manuscripts`, `public/catalog`, `tmp/uploads`; `0750/0640`; Nginx en solo lectura; limpieza de `tmp/uploads` al iniciar. |
| Respaldo, CI y documentación | TSK-07, 08, 09 | Plan §4.9–4.10, §7.5; clarify Q5 | 🟡 | 80 % | Existen `backup.sh`, `restore.sh`, `verify_integrity.sh`, CI y README de 13 secciones. `verify_integrity.sh` invoca un comando de Django que aún no existe; el cron solo programa el respaldo; CI tolera «sin pruebas» (`exit 5`) y no ejecuta pruebas del frontend. D-07, D-09. |
| Núcleo Django (apps, envelope, paginación, salud) | TSK-10, 11, 12 | Plan §2.1, §2.8, §2.10 | ✅ | 100 % | Cinco apps instaladas, envelope `{error:{code,message,details,request_id}}`, `page_size` ≤ 100, `X-Request-ID`, `/api/health/` con `503` genérico. |
| SPA Angular base, layout e imagen del frontend | TSK-13, 14, 15 | Plan §3.1–3.3, §3.10 | 🟡 | 90 % | Compila en producción; layout y componentes compartidos con pruebas. `environment.production.ts` quedó con `production: false` y claves duplicadas (`apiUrl`/`apiBaseUrl`). D-04. |
| Autenticación JWT, cookie HttpOnly y bloqueo de acceso | TSK-17, 19, 20 | HU-01; RF-01; plan §6.1 | ✅ | 100 % | Refresh en cookie `HttpOnly`, `SameSite=Strict`, path `/api/auth/`; rotación y detección de reutilización; bloqueo a los 5 fallos en 15 min con `429` y `Retry-After`. |
| Auditoría inmutable con cadena de hashes | TSK-18 | RNF-08; plan §1.17, §6.5 | ✅ | 100 % | `AuditService.record()` con `pg_advisory_xact_lock`, JSON canónico, trigger append-only, `AuditUnavailable` → `503`. |
| Permisos por rol y por objeto | TSK-21 | RF-16; HU-03; plan §2.9, §6.2 | ✅ | 100 % | `IsAuthor/Reviewer/Editor/Admin`, `IsManuscriptOwner`, `IsAssignedReviewer`, `IsPublicCatalog`; objeto ajeno → `404`; roles releídos de PostgreSQL en cada solicitud; `IsAdmin` no abre manuscritos. |
| Panel unificado multirrol | TSK-22, 27 | HU-02, HU-03; RF-12; plan §3.4 | 🟡 | 85 % | Una sola llamada, estado `ok`/`error` por sección, sin selector de rol. Las secciones de Revisor, Editor y Administrador devuelven `{}` hasta que lleguen sus modelos. |
| Frontend de sesión (AuthStore, interceptores, guards, login, shell) | TSK-24, 25, 26, 28 | HU-01; RF-01 | ✅ | 100 % | Access token solo en memoria; un refresh por `401`; guards con `returnUrl`; sin selector de rol. La tarea nombra Jasmine/Karma y el proyecto usa Vitest. D-12. |
| Pruebas backend de identidad | TSK-23 | Plan §7.1 | ✅ | 100 % | Cubre cinco intentos, cuenta inactiva, rol retirado, refresh revocado, panel parcial y auditoría fallida. |
| Modelos y migraciones de `publications` | TSK-30, 31 | RF-02, RF-05; RN-11, RN-13; plan §1.8–1.11, §1.20 | ✅ | 100 % | `Manuscript`, `ManuscriptAuthor`, `ManuscriptVersion`, `CorrectionRound`, `StatusEvent`, `IdempotencyKey`; secuencia de código, `CHECK`, índices, `search_vector` generado y triggers `prevent_*`. |
| CRUD de manuscritos y validación de autores | TSK-32 | HU-04, HU-06, HU-07; RF-02 | ✅ | 100 % | `If-Match`/`ETag`, edición solo en `DRAFT`/`REQUIRES_CORRECTIONS`, un responsable exacto, `404` para ajenos, conflicto de interés del Editor excluido en `for_editor()`. |
| Validación, sanitización y carga de PDF | TSK-33, 34 | HU-05; RF-05; Constitución §5 | ✅ | 100 % | `pikepdf`, firma `%PDF-`, rechazo de cifrado y contenido activo, 50 MB exactos aceptados y +1 byte → `413`, `O_CREAT\|O_EXCL`, borrador sin versión. |
| Envío formal (v1/ronda 0) y nueva versión | TSK-35, 36 | HU-04, HU-09; RF-06, RF-10; RN-11 | 🟡 | 95 % | Transacción atómica, hashes y snapshot canónico, `Idempotency-Key`. Los avisos posteriores al commit se emiten como señal sin receptores hasta que exista `notifications`. D-10. |
| Baja lógica | TSK-37 | HU-08; RF-22; RN-13 | 🟡 | 75 % | Marca `is_active=false` sin borrar nada, motivo obligatorio en `UNDER_REVIEW`/`ACCEPTED`, atómica y sin duplicar eventos. **Pendiente**: revocar asignación `ACTIVE`, desactivar `CatalogEntry` y notificar a Revisor/Editor (no existen los modelos). D-10. |
| Historial, versiones y descarga del original | TSK-38 | HU-22, HU-23; RF-14, RF-21 | ✅ | 100 % | `X-Accel-Redirect` a `/_protected/` tras auditar; `503` sin redirección si falla la auditoría; Autor propietario y Editor sin conflicto; rutas solo con UUID/versión. |
| Idempotencia de POST | TSK-39 | Plan §2.11 | ✅ | 95 % | Índice único `(user, endpoint, key)`, 24 h, `409` con payload distinto. La limpieza existe como función (`delete_expired_keys`) pero falta el comando de gestión (TSK-76). |
| Pruebas backend de manuscritos | TSK-40 | Plan §7.1 | ✅ | 100 % | Límites 50 MB / +1 byte, contenido activo, versión anterior intacta, concurrencia y fallos de auditoría/almacenamiento. |
| Frontend del Autor | TSK-41, 42, 43, 44 | HU-04…HU-09, HU-22, HU-23 | ✅ | 100 % | Listado con filtros en la URL, formulario reactivo, cargador de PDF, historial y baja lógica, descarga con `responseType: 'blob'`. TSK-44 añadió interfaz de envío y de nueva versión más allá del texto de la tarea. |

**Resumen numérico** (promedio simple de las 23 filas): **≈ 93 %** global · Fase 0 ≈ 86 % · Fase 1 ≈ 97 % · Fase 2 ≈ 96 %.

---

## 2. Auditoría por módulo implementado

### 2.1 Infraestructura y DevOps (Fase 0 — TSK-01 a TSK-15)

**Docker Compose** (`docker-compose.yml`)

| Elemento | Esperado (plan §5.2) | Encontrado | Veredicto |
|---|---|---|---|
| PostgreSQL | `postgres:16-alpine`, healthcheck, red interna | `postgres:16-alpine`, `pg_isready`, solo en `backend_net` (interna), volumen `postgres_data` | ✅ |
| Puerto de `db` | No se publica | `"5432:5432"` publicado al host (introducido en `ad22b2c`) | ❌ |
| Backend | Sin puertos, healthcheck, espera a `db` sano | Sin puertos; `depends_on: db: service_healthy`; healthcheck contra `/api/health/` | ✅ |
| Arranque | `check_env` → `init_media` → `migrate` → `collectstatic` → Gunicorn | Exactamente esa secuencia, con `umask 0027` | ✅ |
| Web (Nginx + SPA) | Publica 80/443, espera a backend sano | Publica solo `80`; espera a `backend` sano; monta `media_data` y `static_data` en solo lectura | 🟡 |
| `adminer` | No forma parte del plan | Imagen `adminer` sin versión fija, puerto `8888` publicado, conectado a `backend_net` y `frontend_net` | ❌ (herramienta de desarrollo expuesta) |
| Redes | `backend_net` interna, `frontend_net` | Ambas definidas; `backend_net` con `internal: true` | ✅ |

Puntos de atención:

1. **Puerto 5432 expuesto.** Publicado en todas las interfaces del host. Además, el contenedor `db` actualmente en ejecución se creó **antes** del cambio (`docker port` devuelve vacío), de modo que el próximo `docker compose up` lo expondrá sin que nadie lo decida de nuevo.
2. **Adminer.** Da acceso de administración a la base desde el navegador y está en la red del frontend. No debe existir en el compose de producción.
3. **Healthchecks.** Presentes en `db` y `backend`; `web` no tiene (aceptable para el piloto).

**PostgreSQL 16.** Cumple (imagen, driver `psycopg` 3, `ENGINE` PostgreSQL en todos los settings; CI rechaza SQLite con un `git grep`).

**Nginx** (`nginx/conf.d/default.conf`)

- ✅ `client_max_body_size 60m`, `client_body_timeout`/`proxy_*_timeout` de 120 s, `proxy_request_buffering on`, buffer temporal explícito.
- ✅ `/_protected/` y `/_catalog/` son `internal` y sirven desde `/data/media/private/` y `/data/media/public/catalog/`; `/media/` es `deny all`; `gzip_types` no incluye PDF.
- ✅ Cabeceras de seguridad (CSP restrictiva, `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy`, `Permissions-Policy`); `server_tokens off`.
- ✅ Fallback de Angular con `try_files … /index.html`.
- ❌ **TLS.** Solo `listen 80`; no hay bloque `443`, `ssl_protocols`, redirección HTTP→HTTPS ni uso de `nginx/certs/` (existen `fullchain.pem` y `privkey.pem`, ignorados por git). El README §7 declara este aplazamiento («la habilitación de `:443` se realiza junto con la instalación del certificado»), pero TSK-04 lo exige como criterio de aceptación y el plan §5.3 como diseño objetivo.

**Gunicorn / imagen del backend.** 3 workers, timeout 120 s, usuario `app` (UID 1000) sin privilegios, grupo `media` GID 101 coincidente con `nginx`. El `CMD` de la imagen y el `command` del compose definen Gunicorn por duplicado (el compose prevalece).

**Volumen `media_data`.** `init_media.sh` crea la estructura una sola vez, aplica `0750/0640`, grupo `media` y limpia `tmp/uploads` con `-mindepth 1` sin tocar `private/` ni `public/`. Backend con escritura, `web` con `:ro`. No se sirve `/data/media` como estático público.

**Respaldo y CI**

- `backup.sh`, `restore.sh`, `verify_integrity.sh`, `BACKUP.md` y plantilla de cron existen. El cron programa solo el respaldo de las 02:15 con `flock`.
- `verify_integrity.sh` ejecuta `manage.py verify_integrity`, comando que pertenece a TSK-76 y aún no existe: el script falla hoy.
- `ci.yml`: jobs de `check`, pruebas con PostgreSQL, `ng build` de producción y `docker compose config`. El paso de pruebas del backend convierte «ninguna prueba recolectada» (`exit 5`) en éxito, tolerancia que ya no tiene sentido con 677 pruebas. No hay job de pruebas del frontend ni de linter.

**README.** 13 secciones (requisitos, estructura, instalación, carga de prueba, operación, volumen, TLS, respaldo, CI, pruebas, seguridad, estado, metodología). Cubre migraciones, `seed_roles` y restauración.

### 2.2 Identidad y Panel (Fase 1 — TSK-16 a TSK-28)

**Autenticación JWT y cookies**

- `POST /api/auth/login/`, `refresh/`, `logout/` y `GET /api/auth/me/` implementados en `apps/users/services/auth.py` y `views.py`.
- Refresh token en cookie `gpc_refresh`: `HttpOnly=True`, `SameSite=Strict`, `Path=/api/auth/`, `Secure` gobernado por `COOKIE_SECURE`. El access token vive solo en memoria del cliente (verificado en `auth.store.ts`; ningún código fuera de comentarios y pruebas usa `localStorage`).
- Rotación en cada uso con registro propio en `users_refresh_token`; la reutilización de un token consumido revoca los descendientes. Logout revoca el refresh vigente.
- Respuestas genéricas ante credenciales inválidas, cuenta inactiva o inexistente.

**Bloqueo de 5 intentos** (`auth.py`): `LOCKOUT_MAX_FAILURES = 5`, `LOCKOUT_WINDOW = 15 min`; se comprueba **antes** de validar credenciales; el sexto intento devuelve `429` con `Retry-After`; el bloqueo expira por sí solo; los intentos bloqueados no lo extienden; el identificador se compara sin distinguir mayúsculas; se audita éxito, fallo y bloqueo sin guardar la contraseña. Las pruebas `test_rate_limit.py` y `test_session_flow.py` lo cubren.

**Endpoint multirrol `/api/dashboard/`**: una sola respuesta con `user`, `roles` y `sections`; cada sección se construye de forma aislada y devuelve `{"status":"ok"|"error","data","message"}`, de modo que un fallo parcial conserva `200`. Sin roles activos se devuelve `sections` vacío. Limitación: las secciones `reviewer`, `editor` y `admin` devuelven datos vacíos hasta las Fases 3–5.

**Permisos**: el rol y el estado de la cuenta se leen de PostgreSQL en cada solicitud (`InstitutionalJWTAuthentication`, `request_active_roles`); retirar un rol bloquea la siguiente acción aunque el access token siga vigente.

**Frontend**: rutas lazy con `authGuard` y `rolesGuard`, `returnUrl`, `403` y `404`; no existe ruta, guard ni componente de selección de rol; el dashboard renderiza todas las secciones activas a la vez y ofrece «Reintentar» por sección.

### 2.3 Autor y Documentos (Fase 2 — TSK-29 a TSK-44)

| Capacidad | Evidencia | Veredicto |
|---|---|---|
| CRUD de manuscritos | `GET/POST /api/manuscripts/`, `GET/PATCH /{id}/`, `ETag`/`If-Match` con `lock_version`, filtros y paginación; edición solo en `DRAFT`/`REQUIRES_CORRECTIONS` | ✅ |
| Autores | Al menos uno, exactamente un `is_corresponding`, el registrante debe figurar; índices únicos `uq_author_manuscript_order` y de responsable | ✅ |
| Sanitización con `pikepdf` | Elimina `/Info`, `/Metadata`, `/PieceInfo`, anotaciones, `/OpenAction`, `/AA`, `/AcroForm`, árboles `/JavaScript` y `/EmbeddedFiles`; la validación rechaza cifrado, truncado, vacío y sin páginas | ✅ |
| Límite de 50 MB | `MAX_PDF_SIZE_MB=50`; 50 MB exactos se aceptan, +1 byte → `413`; Nginx admite 60 MB como margen de multipart | ✅ |
| Escritura sin sobrescritura | `os.open(..., O_WRONLY \| O_CREAT \| O_EXCL)` en `storage.py`; rutas solo con UUID/versión | ✅ |
| Borrador | `POST /{id}/draft-file/` solo `multipart/form-data`, solo `DRAFT`, reemplaza el borrador, no crea versión ni ronda, elimina el temporal si falla | ✅ |
| v1 y ronda 0 | `POST /{id}/submit/` en `transaction.atomic()` con bloqueo de fila: `original.pdf`, `sanitized.pdf`, `metadata.json`, `ManuscriptVersion`, `CorrectionRound` 0, `StatusEvent`, auditoría; `metadata_sha256` sobre JSON canónico | ✅ |
| Nuevas versiones | `POST /{id}/versions/` solo en `REQUIRES_CORRECTIONS`, versión consecutiva, exige `Idempotency-Key`, rechaza envío sin cambios, anterior intacta | ✅ |
| Baja lógica | `is_active=false` + `withdrawn_*`, sin borrar versiones, eventos ni auditoría; motivo obligatorio en `UNDER_REVIEW`/`ACCEPTED`; segunda baja responde `409` | 🟡 (efectos sobre asignación, catálogo y avisos pendientes) |
| Inmutabilidad en base de datos | Triggers `prevent_manuscript_delete`, `prevent_version_mutation`, `prevent_append_only_mutation` y `prevent_audit_mutation` | ✅ |
| Descarga | `X-Accel-Redirect` a `/_protected/` con `Cache-Control: private, no-store` y `Content-Disposition: attachment`; auditoría previa, `503` si falla | ✅ |
| Doble ciego (lado Autor) | `AuthorEvaluationFeedbackSerializer` con lista blanca de tres campos: sin identidad del Revisor ni comentarios confidenciales | ✅ |
| Frontend del Autor | Listado con filtros y página en la URL, formulario con `FormArray`, cargador de PDF con progreso y reemplazo, historial con hash, diálogo de baja, descarga `blob`; 36 archivos de prueba | ✅ |

Observación de alcance: `ManuscriptService.listVersions` (plan §3.6) existe con pruebas pero ninguna pantalla lo usa todavía; el historial consume `history/`.

---

## 3. Lista de deuda técnica y ajustes pendientes

Prioridad: **Crítica** (resolver antes de cualquier `push` o despliegue) · **Alta** · **Media** · **Baja**.

| ID | Prioridad | Hallazgo | Ubicación | Ajuste recomendado |
|---|---|---|---|---|
| D-01 | **Crítica** | `credentials.txt` está **versionado** desde el commit `ad22b2c` (agregado junto con `project_status.md`). Contiene credenciales de una cuenta administradora y nombres de variables de base de datos. El archivo no está en `.gitignore`. Ninguna rama remota conocida localmente contiene el commit (no se verificó contra `origin`, cuyas referencias pueden estar desactualizadas). Durante esta auditoría el contenido se mostró parcialmente en el terminal de la sesión por un comando de inspección; el valor no se reproduce aquí. | `credentials.txt`, `.gitignore` | Tratar la credencial como expuesta: rotarla. Sacar el archivo del índice (`git rm --cached`), añadirlo al `.gitignore` y, **antes del primer `push` de ese commit**, reescribir el commit para que no lo contenga (acción que requiere aprobación explícita). Mover los datos de acceso a un gestor de secretos o a `.env`. |
| D-02 | **Alta** | Nginx no sirve HTTPS: sin `443`, sin `ssl_protocols`, sin redirección. Incumple el criterio de TSK-04 y RNF-06. | `nginx/conf.d/default.conf`, `docker-compose.yml` | Añadir el bloque `listen 443 ssl` con TLS 1.2/1.3 y la redirección `80 → 443`; publicar `443`; montar `nginx/certs/`. |
| D-03 | **Alta** | `db` publica `5432` y `adminer` publica `8888` en todas las interfaces; el contenedor `db` en ejecución aún no los tiene (se crearon antes del cambio). Contradice TSK-02. | `docker-compose.yml` (líneas de `ports` de `db` y `adminer`) | Mover ambos a un archivo `docker-compose.override.yml` solo de desarrollo o ligarlos a `127.0.0.1`; fijar la versión de `adminer`; no incluirlos en producción. |
| D-04 | **Media** | `environment.production.ts` tiene `production: false` (cambio de `ad22b2c`; antes era `true`) y las claves duplicadas `apiUrl`/`apiBaseUrl`; solo `apiBaseUrl` se usa (`app.config.ts:40`). | `frontend/src/environments/environment.production.ts`, `environment.ts` | Restaurar `production: true`; eliminar `apiUrl` o unificar el nombre. |
| D-05 | **Media** | `.gitignore` incompleto: no cubre `credentials*.txt` ni `graphify-out/` (aparece como no rastreado). | `.gitignore` | Añadir ambas rutas (o versionar deliberadamente solo los artefactos del grafo que el equipo quiera compartir). |
| D-06 | **Media** | Con `COOKIE_SECURE=1`, `SESSION_COOKIE_SECURE`/`CSRF_COOKIE_SECURE` y `SECURE_HSTS_SECONDS` de un año con `preload`, pero sin TLS en Nginx, la cookie `Secure` del refresh no viaja por HTTP en un host real (solo `localhost` está exento en los navegadores) y HSTS con preload es arriesgado antes de tener certificado válido. | `backend/config/settings/production.py`, `.env.example` | Resolver D-02; mientras tanto, desarrollo local con `COOKIE_SECURE=0` (ya documentado) y activar HSTS preload solo con el certificado institucional. |
| D-07 | **Media** | CI: el paso de pruebas convierte `exit 5` («nada recolectado») en éxito; no existe job de pruebas del frontend (`ng test`) ni de linter. | `.github/workflows/ci.yml` | Eliminar la tolerancia a `exit 5`; añadir `ng test --watch=false`. |
| D-08 | **Baja** | La imagen de producción copia `tests/` y `pytest.ini` pero `requirements/production.txt` no instala `pytest`; las pruebas no se pueden ejecutar dentro del contenedor desplegado. | `backend/Dockerfile`, `requirements/production.txt` | No copiar `tests/` a la imagen de producción o crear una etapa de pruebas con dependencias de desarrollo. |
| D-09 | **Media** | `verify_integrity.sh` depende del comando `verify_integrity` (TSK-76), inexistente; el cron solo programa el respaldo; la restauración de humo no se ejercitó en esta auditoría. | `scripts/verify_integrity.sh`, `scripts/cron/gpc.cron` | Aceptar como dependencia conocida hasta TSK-76; ejecutar una restauración de humo antes del piloto. |
| D-10 | **Media** | Integraciones de la baja lógica y del envío pendientes por diseño: revocar asignación activa, desactivar catálogo, notificar. Hoy existen solo como señales (`manuscript_withdrawing`, `manuscript_withdrawn`, `manuscript_submitted`) sin receptores. | `apps/publications/signals.py`, `services/withdraw.py`, `services/submission.py` | Conectar los receptores al crear `Assignment` (TSK-46/48), `CatalogEntry` (TSK-50) y `notifications` (Fase 5). |
| D-11 | **Baja** | Las secciones `reviewer`, `editor` y `admin` del dashboard devuelven `{}`. | `apps/users/services/dashboard.py` | Completar con las Fases 3–5. |
| D-12 | **Baja** | TSK-28 nombra Jasmine/Karma; el proyecto usa Vitest (`@angular/build:unit-test`). | `.spec-kit/tasks.md`, `frontend/package.json` | Actualizar el texto de la tarea para que refleje la herramienta real. |
| D-13 | **Baja** | Advertencia NG8113: `LoadingSpinnerComponent` importado y sin uso en `UnifiedDashboardComponent`. | `frontend/.../unified-dashboard.component.ts:38` | Quitar el import. |
| D-14 | **Baja** | Gunicorn definido dos veces (`CMD` de la imagen y `command` del compose). | `backend/Dockerfile`, `docker-compose.yml` | Dejar una sola definición. |
| D-15 | **Baja** | `project_status.md` (versionado) afirma que no se ejecutaron pruebas; esta auditoría sí las ejecutó (677 backend, 559 frontend). | `project_status.md` | Actualizar la nota o fechar el documento como instantánea. |

**Archivos y configuraciones de entorno — resumen**

- **No versionado y correcto:** `.env` (permisos `0600`), `nginx/certs/*.pem`, respaldos y volcados.
- **Versionado y no debería estarlo:** `credentials.txt` (D-01).
- **Sin versionar y sin ignorar:** `graphify-out/` (D-05).
- **Versionado con cambio indeseado:** `environment.production.ts` (D-04) y `docker-compose.yml` (D-03).

---

## 4. Siguiente paso

**Veredicto: el proyecto está funcionalmente listo para iniciar la Fase 3 desde la TSK-45.** El dominio del Autor (Fase 2) y la identidad (Fase 1) cumplen sus criterios, con 677 pruebas de backend y 559 de frontend en verde y compilación de producción correcta. La deuda abierta se concentra en infraestructura y no bloquea el desarrollo de la Fase 3, con una excepción previa a cualquier publicación del repositorio:

1. **Antes de cualquier `push`:** resolver D-01 (credencial versionada).
2. **Antes de un despliegue o piloto:** D-02 (TLS), D-03 (puertos de `db` y `adminer`) y D-06.
3. **Puede proceder en paralelo con la Fase 3:** D-04, D-05, D-07, D-12, D-13.

**Estado de partida de la TSK-45 (verificado):**

- `scripts/cron/gpc.cron` contiene solo el respaldo diario; la línea de `mark_expired_assignments` se añade siguiendo el mismo patrón (`flock -n`, `docker compose exec -T backend`, log redirigido).
- `apps/reviews/` existe pero `models.py`, `views.py`, `urls.py` y `serializers.py` están vacíos; solo hay `permissions.py`. El comando `mark_expired_assignments` y el modelo `Assignment` llegan con TSK-49 y TSK-46, por lo que la línea de cron fallará cada minuto hasta TSK-49.
- TSK-49 exige «notificar al Editor una sola vez», pero `apps/notifications/models.py` está vacío y su implementación está planificada en la Fase 5. Conviene decidir antes de TSK-49 si se adelanta un mínimo de notificaciones o se deja el gancho para después.

**Pendiente de tu orden:** revisar este informe y confirmar el inicio de la TSK-45, decidiendo además si D-01 se atiende antes.
