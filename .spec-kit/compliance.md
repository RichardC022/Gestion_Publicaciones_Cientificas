# Matriz de Cumplimiento — TSK-01 a TSK-70 (Fases 0, 1, 2, 3 y 4)

**Archivo:** `compliance.md`
**Fecha de la auditoría:** 26 de octubre de 2026 (TSK-01 a TSK-44) · actualizada el 27 de octubre de 2026 con la Fase 3 (TSK-45 a TSK-57) · **actualizada de nuevo el 27 de octubre de 2026** (añade la Fase 4 completa, TSK-58 a TSK-70: Revisor, incidentes confidenciales y doble ciego; revisa cada deuda contra el estado actual y registra tres nuevas, D-20 a D-22)
**Rama / commit auditado:** `dev/jostin-setup` @ `5a27a9b` (TSK-70); los únicos cambios sin commit son `.spec-kit/HANDOFF.md` y este documento
**Contrastado contra:** `.spec-kit/specify.md`, `.spec-kit/plan.md`, `.spec-kit/tasks.md`, `.spec-kit/constitution.md`, `.spec-kit/clarify.md`
**Alcance:** lectura y ejecución de pruebas. Esta actualización solo modifica este documento; el código de la Fase 4 se auditó tal como quedó en los commits `9a96a14` a `5a27a9b`. La configuración de Nginx, el `docker-compose.yml`, el CI y los scripts **no cambiaron** desde la TSK-58.

---

## 0. Método y evidencia

| Evidencia | Resultado |
|---|---|
| Pruebas backend (pytest, contenedor efímero con dependencias de desarrollo contra el PostgreSQL 16 del proyecto) | **1312 pasan, 8 omitidas, 1 `xfail`** (antes: 975 y 8 omitidas; la Fase 4 añade 337, casi todas en `tests/reviews/`). Las 8 omitidas son comprobaciones que necesitan archivos del repositorio que la imagen del backend no trae: la plantilla de cron y la configuración de Nginx (7 casos); con esos archivos montados pasan (las de Nginx: 10 de 10) y con una configuración rota fallan. El `xfail(strict=True)` documenta una deuda real (D-10). |
| Pruebas frontend (`ng test`, Vitest) | **57 archivos, 1045 pruebas, todas pasan** (antes: 45 archivos, 775). La Fase 4 añade 270 pruebas: servicio y modelo del Revisor, contador, bandeja, detalle, formulario, diálogos, historial, bandeja de incidentes del Editor, integración con las rutas reales y una prueba que lee el código fuente del Revisor. |
| Compilación `ng build --configuration production` | **Correcta** (1 advertencia NG8113, ver D-13). Los componentes del Revisor y la bandeja de incidentes salen como bloques de carga diferida propios. |
| Migraciones | `makemigrations --check`: **sin cambios pendientes**. `reviews` llega a `0003_incident_report` (nueva en la Fase 4); `publications` sin cambios. |
| Aislamiento del volumen (TSK-58) | `scripts/smoke_media_isolation.sh`: todas las comprobaciones pasaron en la TSK-58 (3 ejecuciones; las tres mutaciones probadas la hacen fallar). **No se repitió en esta actualización**: Nginx, el compose y los scripts no cambiaron desde entonces (`git diff ed3b109 HEAD` vacío). La guarda de `tests/test_media_isolation.py` que prohíbe a `apps/reviews` nombrar el PDF original **sí se ejecutó** y pasa contra el código real del Revisor. |
| Concurrencia | Las pruebas con hilos reales (`transaction=True`) se repitieron 6 veces seguidas sin fallos en la Fase 3; las de la Fase 4 (`test_review_concurrency.py`: guardados, doble envío, envío contra revocación o conflicto, doble reporte, doble resolución) se repitieron 5 veces seguidas, 20 pasadas cada una, sin intermitencias. |
| Lectura de código | `docker-compose.yml`, `nginx/`, `.github/workflows/ci.yml`, `scripts/cron/gpc.cron`, settings, servicios de `users`, `publications` y `reviews` (incluidos `evaluations.py`, `incidents.py`, `inbox.py`), vistas y serializadores del Revisor, rutas, modelos y servicios Angular de los módulos Editor y Revisor. |
| Contenedores en ejecución | `backend`, `db` y `web` arriba. **No se comprobó** si la imagen en ejecución incluye el código de la Fase 4 (la imagen no se reconstruyó; las pruebas montan `backend/` sobre ella): hace falta `docker compose up -d --build backend web` antes de recorrer las pantallas. |

**Cómo leer los porcentajes.** Es la proporción de criterios de aceptación de cada tarea que se verificó como cumplida (por lectura de código y/o pruebas ejecutadas). Es una estimación del auditor, no una métrica automática.

**Estados.** ✅ Cumple · 🟡 Cumple parcialmente · ❌ No cumple · ⏳ Pendiente por diseño (depende de una fase posterior).

**No verificado en esta auditoría** (requiere entorno o acción que no se ejecutó): contraste WCAG AA real, un `413` extremo a extremo a través de Nginx con un PDF de 60 MB, la restauración de humo de `restore.sh`, el comportamiento TLS (no existe, ver D-02), la instalación de `scripts/cron/gpc.cron` en `/etc/cron.d/gpc` del servidor, y cualquier recorrido manual en navegador de las pantallas del Editor y del Revisor (se probaron con Vitest contra las rutas reales y una API simulada), la descarga del PDF sanitizado del Revisor **a través de Nginx** (las pruebas verifican la cabecera `X-Accel-Redirect`, que Nginx consume, pero no la entrega real del archivo) y la lectura de los PDF servidos con un visor externo.

---

## 1. Tabla resumen de la Matriz de Cumplimiento

| Módulo / Feature | Tareas | Requisitos cubiertos | Estado | Cumplimiento | Observaciones / Deuda técnica |
|---|---|---|---|---|---|
| Estructura del repositorio y Docker Compose | TSK-01, 02 | Constitución §1; plan §5.1–5.2 | 🟡 | 80 % | `db` publica `5432` y `adminer` publica `8888` (commit `ad22b2c`); `web` solo publica `80`. Contradice el criterio «`db`/`backend` no publican puertos; solo `web` expone 80/443». **`adminer` está ahora en ejecución publicado en `0.0.0.0:8888`.** D-03. |
| Imagen del backend y Gunicorn | TSK-03 | Plan §5; Constitución §2 | ✅ | 95 % | Usuario no root, Gunicorn en `0.0.0.0:8000`, sin MySQL/SQLite. La imagen de producción copia `tests/` pero no instala `pytest`. D-08. |
| Nginx: proxy, estáticos, ubicaciones internas, TLS | TSK-04 | Plan §5.3, §4.6; RNF-06 | 🟡 | 60 % | Cumple `client_max_body_size 60m`, timeouts de 120 s, `/_protected/` y `/_catalog/` internas, `deny all` en `/media/`, PDF sin compresión, CSP. **No cumple TLS**: solo `listen 80`, sin redirección a HTTPS ni TLS 1.2/1.3. D-02. |
| Variables de entorno, secretos y cookies | TSK-05, 16 | Plan §5.4, §6.1, §6.6 | ✅ | 90 % | `.env.example` completo, `check_env.sh` y `production.py` fallan con mensaje claro, `.env` con permisos `0600`. `COOKIE_SECURE=1` sin TLS disponible. D-06. |
| Volumen `media_data` y límites de carga | TSK-06, 29 | Plan §4.1–4.2; clarify Q1, Q2 | ✅ | 95 % | Estructura `private/drafts`, `private/manuscripts`, `public/catalog`, `tmp/uploads`; `0750/0640`; Nginx en solo lectura; limpieza de `tmp/uploads` al iniciar. |
| Respaldo, CI y documentación | TSK-07, 08, 09 | Plan §4.9–4.10, §7.5; clarify Q5 | 🟡 | 80 % | Existen `backup.sh`, `restore.sh`, `verify_integrity.sh`, CI y README de 13 secciones. `verify_integrity.sh` invoca un comando de Django que aún no existe; el cron programa el respaldo y, desde la TSK-49, la expiración de asignaciones; CI sigue tolerando «sin pruebas» (`exit 5`) y no ejecuta pruebas del frontend. D-07, D-09. |
| Núcleo Django (apps, envelope, paginación, salud) | TSK-10, 11, 12 | Plan §2.1, §2.8, §2.10 | ✅ | 100 % | Cinco apps instaladas, envelope `{error:{code,message,details,request_id}}`, `page_size` ≤ 100, `X-Request-ID`, `/api/health/` con `503` genérico. |
| SPA Angular base, layout e imagen del frontend | TSK-13, 14, 15 | Plan §3.1–3.3, §3.10 | 🟡 | 90 % | Compila en producción; layout y componentes compartidos con pruebas. `environment.production.ts` quedó con `production: false` y claves duplicadas (`apiUrl`/`apiBaseUrl`). D-04. |
| Autenticación JWT, cookie HttpOnly y bloqueo de acceso | TSK-17, 19, 20 | HU-01; RF-01; plan §6.1 | ✅ | 100 % | Refresh en cookie `HttpOnly`, `SameSite=Strict`, path `/api/auth/`; rotación y detección de reutilización; bloqueo a los 5 fallos en 15 min con `429` y `Retry-After`. |
| Auditoría inmutable con cadena de hashes | TSK-18 | RNF-08; plan §1.17, §6.5 | ✅ | 100 % | `AuditService.record()` con `pg_advisory_xact_lock`, JSON canónico, trigger append-only, `AuditUnavailable` → `503`. |
| Permisos por rol y por objeto | TSK-21 | RF-16; HU-03; plan §2.9, §6.2 | ✅ | 100 % | `IsAuthor/Reviewer/Editor/Admin`, `IsManuscriptOwner`, `IsAssignedReviewer`, `IsPublicCatalog`; objeto ajeno → `404`; roles releídos de PostgreSQL en cada solicitud; `IsAdmin` no abre manuscritos. |
| Panel unificado multirrol | TSK-22, 27 | HU-02, HU-03; RF-12; plan §3.4 | 🟡 | 70 % | Una sola llamada, estado `ok`/`error` por sección, sin selector de rol. **Corrección del informe anterior:** las cuatro secciones del backend (Autor, Revisor, Editor y Administrador) devuelven `{}`, no solo tres; el panel muestra «Sin datos por ahora» a todos los roles. **La sección del Revisor sigue vacía aunque ya existen asignaciones y plazos reales (Fase 4).** El nombre del rol aparecía duplicado en cada tarjeta; corregido (ver 2.2). D-11. |
| Frontend de sesión (AuthStore, interceptores, guards, login, shell) | TSK-24, 25, 26, 28 | HU-01; RF-01 | ✅ | 100 % | Access token solo en memoria; un refresh por `401`; guards con `returnUrl`; sin selector de rol. La tarea nombra Jasmine/Karma y el proyecto usa Vitest. D-12. |
| Pruebas backend de identidad | TSK-23 | Plan §7.1 | ✅ | 100 % | Cubre cinco intentos, cuenta inactiva, rol retirado, refresh revocado, panel parcial y auditoría fallida. |
| Modelos y migraciones de `publications` | TSK-30, 31 | RF-02, RF-05; RN-11, RN-13; plan §1.8–1.11, §1.20 | ✅ | 100 % | `Manuscript`, `ManuscriptAuthor`, `ManuscriptVersion`, `CorrectionRound`, `StatusEvent`, `IdempotencyKey`; secuencia de código, `CHECK`, índices, `search_vector` generado y triggers `prevent_*`. |
| CRUD de manuscritos y validación de autores | TSK-32 | HU-04, HU-06, HU-07; RF-02 | ✅ | 100 % | `If-Match`/`ETag`, edición solo en `DRAFT`/`REQUIRES_CORRECTIONS`, un responsable exacto, `404` para ajenos, conflicto de interés del Editor excluido en `for_editor()`. |
| Validación, sanitización y carga de PDF | TSK-33, 34 | HU-05; RF-05; Constitución §5 | ✅ | 100 % | `pikepdf`, firma `%PDF-`, rechazo de cifrado y contenido activo, 50 MB exactos aceptados y +1 byte → `413`, `O_CREAT\|O_EXCL`, borrador sin versión. |
| Envío formal (v1/ronda 0) y nueva versión | TSK-35, 36 | HU-04, HU-09; RF-06, RF-10; RN-11 | 🟡 | 95 % | Transacción atómica, hashes y snapshot canónico, `Idempotency-Key`. Los avisos posteriores al commit se emiten como señal sin receptores hasta que exista `notifications`. D-10. |
| Baja lógica | TSK-37 | HU-08; RF-22; RN-13 | 🟡 | 85 % | Marca `is_active=false` sin borrar nada, motivo obligatorio en `UNDER_REVIEW`/`ACCEPTED`, atómica y sin duplicar eventos. Desde la TSK-48 **revoca la asignación `ACTIVE`** dentro de la misma transacción. **Pendiente**: desactivar la `CatalogEntry`, retirar la copia pública y notificar a Revisor/Editor. D-10. |
| Historial, versiones y descarga del original | TSK-38 | HU-22, HU-23; RF-14, RF-21 | ✅ | 100 % | `X-Accel-Redirect` a `/_protected/` tras auditar; `503` sin redirección si falla la auditoría; Autor propietario y Editor sin conflicto; rutas solo con UUID/versión. |
| Idempotencia de POST | TSK-39 | Plan §2.11 | ✅ | 95 % | Índice único `(user, endpoint, key)`, 24 h, `409` con payload distinto. La limpieza existe como función (`delete_expired_keys`) pero falta el comando de gestión (TSK-76). |
| Pruebas backend de manuscritos | TSK-40 | Plan §7.1 | ✅ | 100 % | Límites 50 MB / +1 byte, contenido activo, versión anterior intacta, concurrencia y fallos de auditoría/almacenamiento. |
| Frontend del Autor | TSK-41, 42, 43, 44 | HU-04…HU-09, HU-22, HU-23 | ✅ | 100 % | Listado con filtros en la URL, formulario reactivo, cargador de PDF, historial y baja lógica, descarga con `responseType: 'blob'`. TSK-44 añadió interfaz de envío y de nueva versión más allá del texto de la tarea. |
| Expiración programada de asignaciones | TSK-45, 49 | HU-12; RF-03; RN-05 | 🟡 | 90 % | `mark_expired_assignments` cada minuto con `flock -n`: pasa `ACTIVE` con `due_at <= now()` (reloj de PostgreSQL) a `EXPIRED`, idempotente, un evento de auditoría de sistema por asignación, no revoca ni reasigna. El «aviso al Editor» es la señal `assignment_expired`, **sin receptores** hasta `notifications` (Fase 5); la instalación del cron en el servidor no se verificó. D-10, D-18. |
| Esquema de asignaciones y evaluaciones | TSK-46 | RF-03, RF-07; RN-04, RN-05; plan §1.13–1.14, §1.20 | ✅ | 100 % | `Assignment` y `Evaluation`; `CHECK due_at = assigned_at + 20 días`, único parcial de asignación `ACTIVE`, único `(versión, revisor)`, scores 1–5 y trigger de evaluación `FINAL` inmutable. Dos ajustes al plan (ver 2.4). |
| APIs del Editor: bandeja, asignación y revocación | TSK-47 | HU-10, HU-11; RF-03; plan §2.4 | ✅ | 100 % | Siete endpoints bajo `/api/editor/`; ámbito `for_editor()` (conflicto de interés → `404`); segunda asignación `ACTIVE` → `409`; una vencida debe revocarse antes de reasignar. |
| Servicio de asignación y reasignación | TSK-48 | HU-11; RF-03 | 🟡 | 90 % | `due_at` fijado por PostgreSQL; elegibilidad por cuenta, disponibilidad, área y conflicto; capacidad con bloqueo del perfil; la baja lógica revoca la asignación. Pendiente: los avisos no tienen receptor y el plan §2.4 pide repetir la exclusión de autores «en la base de datos», que hoy solo vive en el servicio. D-10. |
| Modelos de veredicto y catálogo | TSK-50 | RF-07, RF-19; RN-12; plan §1.11–1.12, §1.15 | ✅ | 100 % | `Verdict` append-only (trigger), `CatalogEntry` con único activo por manuscrito, `CorrectionRound.opened_by_verdict` con FK `DEFERRABLE INITIALLY DEFERRED`, `CHECK` de justificación y observaciones. Ajustes al plan en 2.4. |
| Veredicto normal y publicación | TSK-51, 52 | HU-13; RF-07, RF-15, RF-19; RN-12 | 🟡 | 95 % | Servicio y `POST/GET .../verdicts/`, `GET .../evaluations/`: una transacción con veredicto, estado, ronda, catálogo y copia pública sanitizada; `If-Match` + `Idempotency-Key`; falla de auditoría o de copia → `503`/rollback. Desde D-19 el Autor lee las observaciones (`feedback`, lista blanca de tres campos). Pendiente: no existe aún el catálogo público que muestre el artículo (D-17). |
| Pruebas backend de la Fase 3 | TSK-53 | Plan §7.1 | ✅ | 100 % | Factorías de `reviews`, concurrencia real (asignación, capacidad, vencimiento vs revocación, baja vs asignación, veredicto doble, misma clave) y cuatro ciclos completos por la API; cadena de auditoría íntegra tras cada uno. |
| Frontend del Editor: bandeja, detalle y vencidas | TSK-54, 57 | HU-10, HU-12 | ✅ | 95 % | Bandeja con filtros y orden en la URL, detalle con PDF por `Blob` y sellos, vista de vencidas sin acciones automáticas, rutas con `rolesGuard` y acceso por URL a un envío ajeno → error sin datos. El orden usa `updated_at` (la API no ordena por fecha de envío). La bandeja de incidentes, andamio hasta la Fase 3, se implementó en la TSK-70 (ver 2.5). |
| Frontend del Editor: selector y diálogos | TSK-55 | HU-11 | ✅ | 100 % | Selector con búsqueda, carga y **causa cuando no hay elegibles** (`diagnosis` del backend); diálogo de asignación que muestra la fecha límite devuelta por el servidor y advierte del `409`; diálogo de revocación con causa y motivo obligatorios. |
| Frontend del Editor: formulario de veredicto | TSK-56 | HU-13 | 🟡 | 90 % | Recomendación del Revisor en solo lectura, validación espejo del servidor, advertencia al apartarse, confirmación, reintento con la misma `Idempotency-Key`, veredictos anteriores solo en lectura. No muestra la autorización administrativa de corrección (CA-HU-13-12, Fase 5). |
| Aislamiento del volumen y acceso al PDF sanitizado | TSK-58 | Plan §4.6; RNF de privacidad; Constitución §5 | ✅ | 100 % | Prueba de humo ejecutable (`scripts/smoke_media_isolation.sh`) y job de CI: `/_protected/`, `/_catalog/` y `/media/` no entregan archivos (tampoco con rutas codificadas, `//` o `..`), no hay listados, el control positivo entrega con `Cache-Control` y `nosniff`, una redirección interna a `/media/` se deniega, y solo `backend` escribe en el volumen. **Cerrado en la Fase 4:** el endpoint del Revisor (TSK-61) existe y la guarda que prohíbe al módulo `reviews` nombrar el PDF original lo vigila y pasa. |
| Modelo de incidentes confidenciales | TSK-59 | HU-16; RN-06; plan §1.14.1 | ✅ | 100 % | `IncidentReport` (migración `0003`): `CHECK` de resuelto completo (`resolution` y `resolved_at`), único parcial `uq_incident_open` (un reporte abierto por asignación), índice `idx_incident_status_date`, FK `PROTECT`. Crear un reporte no toca PDF, evaluación ni estado del manuscrito. |
| Ámbito, serializadores, bandeja, detalle y descarga del Revisor | TSK-60, 61 | HU-14, HU-16; RF-03; RN-06; plan §2.5, §2.9 | ✅ | 100 % | `Assignment.objects.for_reviewer` (propias, manuscrito activo, sin autor ni coautor por cuenta o correo), serializadores de lista blanca sin autoría, contacto, nombre original, rutas ni hashes; `404` uniforme para lo ajeno. La descarga solo resuelve `sanitized.pdf` con nombre genérico, con la asignación `ACTIVE` (si no, `410`), auditada antes (`503` sin redirección si falla). |
| Borrador y envío final de la evaluación | TSK-62 | HU-15, HU-16; RF-07; plan §2.5, §2.11 | 🟡 | 95 % | `PUT` del borrador con `If-Match` (nace en `lock_version` 1; el borrador vacío es `"0"`), huecos permitidos; envío exige 5 puntajes, recomendación y comentarios al Autor; corte por `due_at` con el reloj de PostgreSQL (`410`, el borrador se conserva); asignación → `COMPLETED`, auditoría y señal en la misma transacción. La señal `evaluation_submitted` no tiene receptor hasta `notifications` (D-10). |
| Conflicto de interés e historial anónimo | TSK-63 | HU-16, HU-17; RN-17 | 🟡 | 95 % | `POST .../conflict/` bloquea guardado y envío sin revocar nada; historial propio solo con evaluaciones `FINAL`, sin comentarios confidenciales y con la decisión editorial y su fecha, nunca el texto del Editor. El aviso al Editor es una señal sin receptor (D-10). |
| Reporte de fuga e incidentes del Editor | TSK-64 | HU-16; RN-06; plan §2.4–2.5 | 🟡 | 95 % | Reporte confidencial (un abierto por asignación → `409`; el Revisor solo recibe el acuse). El Editor lista (`?status=`) y resuelve **una sola vez**: `REQUEST_ANONYMIZED_VERSION` abre una ronda sin veredicto y revoca; `REASSIGN` revoca; `DISMISS` solo cierra. El Autor no llega a saber que existe el reporte (evento de historial con texto fijo). Avisos sin receptor (D-10). |
| Pruebas backend de la Fase 4 | TSK-65 | Plan §2.9, §7.1 | 🟡 | 95 % | Ciclo completo por la API con PDFs reales: recorrido recursivo del grafo del PDF servido (sin `/Info`, XMP, `/EmbeddedFiles`, JS, `/OpenAction`, `/AA`, `/Launch`; el comprobador se valida contra archivos sucios), 404 indistinguible en 8 endpoints, Autor sin identidad del Revisor, concurrencia con dos conexiones e inmutabilidad de la `FINAL` por API, trigger y SQL crudo. **Limitación:** el punto «notificación sin datos personales» del plan §2.9 se probó sobre el payload de las señales, porque `notifications` no existe (TSK-75). |
| Frontend del Revisor: bandeja, detalle, descarga y plazo | TSK-66 | HU-14 | ✅ | 95 % | Bandeja con página en la URL, detalle anonimizado, descarga **bajo demanda** (cada lectura queda auditada) con nombre `manuscript-<código>-v<n>.pdf` que ignora el `Content-Disposition` del servidor, contador contra `due_at` corregido con la cabecera `Date`. El desfase tiene precisión de segundos (D-22). |
| Frontend del Revisor: formulario de evaluación | TSK-67 | HU-15, HU-16 | ✅ | 100 % | 5 puntajes, recomendación y comentarios; el envío exige todo y la declaración de no tener conflicto (solo en pantalla); guarda primero lo pendiente; confirmación; `If-Match`; `409` de versión ofrece conservar el texto o usar lo guardado; `410` y `409` de estado bloquean **dejando el texto a la vista**; aviso de cambios sin guardar. |
| Frontend del Revisor: diálogos, historial e integración | TSK-68, 69 | HU-16, HU-17 | ✅ | 100 % | Diálogos de conflicto y de fuga que no dan nada por enviado hasta el `2xx`; historial de solo lectura sin comentarios confidenciales; pruebas contra las rutas reales (roles, `404` ajeno, vencimiento, `409`/`410`) y una prueba que lee el código fuente del Revisor y falla si algún archivo referencia campos de autoría o del Editor. |
| Frontend del Editor: incidentes confidenciales | TSK-70 | HU-16 | ✅ | 100 % | Filtro Abiertos/Resueltos/Todos y página en la URL; las tres resoluciones explican sus efectos y piden confirmación; un segundo intento muestra el `409` y relee la lista; un error de red no marca nada como resuelto. |

**Resumen numérico** (promedio simple de las 44 filas): **≈ 94,8 %** global · Fase 0 ≈ 86 % · Fase 1 ≈ 95 % · Fase 2 ≈ 97 % · Fase 3 ≈ 96 % · Fase 4 (TSK-58 a TSK-70, completa) ≈ 98 % (las filas que bajan de 100 % lo hacen por avisos sin receptor hasta la Fase 5 y por la precisión del reloj del contador).

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

**Endpoint multirrol `/api/dashboard/`**: una sola respuesta con `user`, `roles` y `sections`; cada sección se construye de forma aislada y devuelve `{"status":"ok"|"error","data","message"}`, de modo que un fallo parcial conserva `200`. Sin roles activos se devuelve `sections` vacío. Limitación: **las cuatro secciones** (`author`, `reviewer`, `editor` y `admin`) devuelven datos vacíos; los contadores nunca se implementaron (ver D-11).

**Permisos**: el rol y el estado de la cuenta se leen de PostgreSQL en cada solicitud (`InstitutionalJWTAuthentication`, `request_active_roles`); retirar un rol bloquea la siguiente acción aunque el access token siga vigente.

**Frontend**: rutas lazy con `authGuard` y `rolesGuard`, `returnUrl`, `403` y `404`; no existe ruta, guard ni componente de selección de rol; el dashboard renderiza todas las secciones activas a la vez y ofrece «Reintentar» por sección. **Corrección del 27/oct:** cada tarjeta mostraba el nombre del rol dos veces (el `<h2>` del contenedor y el `<h3>` de la tarjeta resumen). Ahora la tarjeta cargada lo muestra una sola vez; la sección fallida conserva el título del contenedor, porque ahí no hay tarjeta resumen. Dos pruebas nuevas lo fijan.

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

### 2.4 Editor y veredictos (Fase 3 — TSK-45 a TSK-57)

| Capacidad | Evidencia | Veredicto |
|---|---|---|
| Expiración de asignaciones | `mark_expired_assignments`: `ACTIVE` con `due_at <= now()` por el reloj de PostgreSQL, una transacción y un evento de auditoría de sistema por asignación, `skip_locked`, idempotente; si la auditoría falla la asignación sigue `ACTIVE` y se reintenta. Cron `* * * * *` con `flock -n` y lock propio | ✅ |
| Plazo de 20 días | `CHECK due_at = assigned_at + interval '20 days'`; el servicio usa `now()` de la transacción en ambos campos; el reloj o los campos que envíe el cliente no lo mueven | ✅ |
| Revisor único | Índice único parcial `uq_assignment_active`, bloqueo de la fila del manuscrito y bloqueo del perfil del Revisor al contar su carga | ✅ |
| Elegibilidad | Cuenta y rol activos, perfil disponible, área declarada (coincidencia exacta) y sin conflicto por cuenta o por correo; con lista vacía, `GET /reviewers/` añade `diagnosis` con la causa | ✅ |
| Revocación | Antes del plazo solo `CONFLICT_OF_INTEREST`, `ASSIGNMENT_ERROR` y `ACCOUNT_DISABLED`; `OVERDUE` solo si venció; motivo obligatorio; el manuscrito sigue `UNDER_REVIEW` y las evaluaciones se conservan | ✅ |
| Conflicto de interés del Editor | `for_editor()` → `404` en las lecturas y en la asignación; en `POST .../verdicts/` el servicio responde `403` y audita `DENIED` (CA-HU-13-08) | ✅ |
| Veredicto normal | Una transacción: bloqueo de manuscrito y evaluación, `Verdict` append-only, estado, ronda nueva con su veredicto, `CatalogEntry` y copia pública generada con `PdfService.sanitize` desde el original (inodo propio, `O_EXCL`), auditoría. Si falla algo, rollback y el archivo escrito se retira; un archivo previo nunca se pisa | ✅ |
| Reglas del veredicto | Justificación al rechazar o apartarse de la recomendación; observaciones al pedir correcciones; `If-Match` + `Idempotency-Key`; segundo veredicto → `409 VERDICT_CONFLICT`; baja lógica → `409` auditado; sin evaluación `FINAL` → `409` | ✅ |
| Doble ciego (lado Editor) | La identidad del Revisor y los comentarios confidenciales solo salen por `/api/editor/**`; los borradores no se listan; Autor y Revisor reciben `403`; las pruebas confirman que no aparecen en sus respuestas | ✅ |
| Concurrencia | Hilos con conexión propia: dos Editores asignando, capacidad entre manuscritos, doble `start-review`, revocar vs vencer, baja vs asignación, veredicto doble, misma clave a la vez, baja vs veredicto. Seis ejecuciones seguidas estables | ✅ |
| Frontend del Editor | Bandeja, detalle, selector, diálogos, formulario de veredicto y vencidas, probados contra las rutas reales con `rolesGuard` | ✅ |
| Baja lógica ↔ catálogo | La `CatalogEntry` no se desactiva ni se elimina la copia pública al dar de baja un manuscrito aceptado (plan §4.8, pasos 5 y 7). Lo documenta un `xfail(strict=True)` | ❌ D-10 |
| Veredicto → Autor | `feedback` en la respuesta del Autor: `comments_for_author`, decisión y observaciones del último veredicto, y solo cuando existe un veredicto (una evaluación final por sí sola no se muestra). Nunca incluye la identidad del Revisor, los comentarios confidenciales, las puntuaciones ni la justificación interna del Editor; 12 pruebas, incluida una de consultas para evitar N+1 en el listado | ✅ |
| Avisos | Siete señales emitidas tras el commit (`manuscript_submitted`, `new_version_submitted`, `manuscript_withdrawn`, `assignment_created`, `assignment_revoked`, `assignment_expired`, `verdict_registered`), sin receptores. La Fase 4 añade cuatro más (ver 2.5) | ⏳ Fase 5 |

**Ajustes al plan** (cada uno decidido y probado):

1. **Trigger de evaluación final:** la función del plan devuelve siempre `NEW`; en un `DELETE` eso cancelaría el borrado de un borrador en silencio. La implementación devuelve `OLD` en los borrados.
2. **Nombre de índice:** `idx_assignment_ms_status` en lugar de `idx_assignment_manuscript_status`, por el límite de 30 caracteres de Django.
3. **`lock_version` en `Assignment`:** lo pide `tasks.md` (TSK-46) aunque la tabla del plan no lo lista.
4. **Catálogo:** solo el índice único parcial `uq_catalog_active`; el `UNIQUE` completo que también muestra el plan lo volvería redundante e impediría conservar entradas retiradas junto a una nueva. Se añadieron `ck_catalog_unpublish` y `ck_catalog_public_path` (la copia nunca apunta al árbol privado).
5. **Un veredicto normal por versión en la base de datos:** `uq_verdict_normal_per_version` (no estaba en TSK-50); la corrección administrativa lo sortea con `previous_verdict`.
6. **Justificación al apartarse de la recomendación:** lo dice el plan §1.15, no `tasks.md`.
7. **Copia pública:** se genera desde el original con la misma sanitización, no copiando `sanitized.pdf` (plan §4.7).
8. **Fecha límite en la interfaz:** el diálogo anuncia «20 días calendario» y muestra la fecha exacta solo cuando el servidor responde; el navegador no calcula fechas.
9. **Orden de la bandeja:** por `updated_at`, porque la API no admite ordenar por fecha de envío.

### 2.5 Revisor, incidentes y doble ciego (Fase 4 — TSK-58 a TSK-70)

| Capacidad | Evidencia | Veredicto |
|---|---|---|
| Ámbito del Revisor | `Assignment.objects.for_reviewer`: solo asignaciones propias de manuscritos activos, excluye los que el Revisor registró o co-escribió (por cuenta o por correo). Todo endpoint del Revisor parte de ahí; lo ajeno responde `404` con el mismo sobre que un id inexistente (8 endpoints probados) | ✅ |
| Doble ciego, capa de serializadores | `ReviewerManuscriptSerializer`/`ReviewerVersionSerializer` son listas blancas: sin autores, filiaciones, contacto, `created_by`, `metadata_snapshot`, nombre original, rutas ni hashes. Las pruebas buscan los valores sensibles en el texto serializado, no solo las claves | ✅ |
| Doble ciego, capa de artefactos | El Revisor solo recibe `sanitized.pdf`; la prueba abre el archivo que Nginx serviría y recorre todo su grafo de objetos desde el *trailer* (diccionarios directos incluidos). El comprobador se valida contra PDFs con cada tipo de contenido sucio | ✅ |
| Doble ciego, lado Autor | El Autor no ve la identidad del Revisor, los comentarios confidenciales, los puntajes ni la existencia de un reporte de fuga | ✅ |
| Descarga del PDF | `GET .../document/` solo con la asignación `ACTIVE` (si no, `410`); auditoría previa y `503` sin redirección si falla; `X-Accel-Redirect` a `/_protected/` (interno de Nginx, no llega al cliente); nombre genérico | ✅ |
| Evaluación | Borrador con huecos y bloqueo optimista (`If-Match`/`ETag` = `lock_version`); envío con 5 puntajes, recomendación y comentarios al Autor; corte por `due_at` con el reloj de PostgreSQL (`now() == due_at` ya es tarde); `FINAL` inmutable por trigger (`UPDATE` y `DELETE` fallan), por el servicio y por la API (409) | ✅ |
| Orden de bloqueos | Manuscrito → asignación → incidente/evaluación en todas las rutas. Probado con dos conexiones reales: dos guardados, doble envío (una finalización, una auditoría), envío contra revocación, contra conflicto y contra resolución, doble reporte, doble resolución | ✅ |
| Conflicto de interés | Bloquea guardado y envío; no revoca ni cambia el manuscrito; el aviso al Editor es una señal | 🟡 (aviso sin receptor) |
| Reporte de fuga | Confidencial: el Revisor recibe el acuse, el Editor lee la descripción y la identidad del Revisor, el Autor nada. Un abierto por asignación; el servicio y la BD lo garantizan | 🟡 (aviso sin receptor) |
| Resolución editorial | Una sola vez (`409` el segundo intento); las dos primeras resoluciones exigen el manuscrito `UNDER_REVIEW` y activo y revocan la asignación; `REQUEST_ANONYMIZED_VERSION` abre la siguiente ronda **sin veredicto** (excepción auditada y única a la transición ordinaria) con un evento de historial de texto fijo | ✅ |
| Historial del Revisor | Solo evaluaciones `FINAL` propias, sin `confidential_comments`, con decisión editorial y fecha; el detalle sin el texto del Editor | ✅ |
| Frontend del Revisor | Bandeja, detalle, formulario, diálogos e historial con `rolesGuard`; Editor, Autor y Administrador reciben `403` en las cuatro pantallas y no se pide nada; acceso por URL a una asignación ajena → error sin datos y sin pedir el documento | ✅ |
| Doble ciego en el código | `no-authorship.spec.ts` lee los archivos fuente del Revisor (sin comentarios) y falla si alguno referencia campos de autoría, archivo original, rutas, hashes o campos del Editor; se comprobó que detecta una referencia introducida a propósito | ✅ |
| Cambios sin perder texto | `409` de versión, `410`, `409` de estado y errores de red conservan lo escrito; salir con cambios sin guardar advierte (`unsavedChangesGuard`) | ✅ |
| Frontend del Editor: incidentes | Ver TSK-70 en la matriz | ✅ |
| Avisos | Cuatro señales nuevas tras el commit (`evaluation_submitted`, `reviewer_conflict_declared`, `incident_reported`, `incident_resolved`), con solo identificadores y códigos, sin receptores (11 en total) | ⏳ Fase 5 |

**Decisiones y ajustes al plan** (cada uno decidido y probado):

1. **`lock_version` de la evaluación nace en 1:** el borrador vacío que muestra el `GET` es el `"0"`; si naciera en 0, dos pestañas que parten del borrador vacío se pisarían en silencio.
2. **El conflicto de interés se guarda en la evaluación** (`conflict_declared`) y no en una tabla propia; el texto libre del motivo solo va a la auditoría. Un Revisor que nunca guardó un borrador recibe uno vacío que lleva la marca.
3. **Código de error del `410`:** el catálogo no tiene un código para `410`; se usa `STATE_CONFLICT` con `status_code=410`.
4. **La descarga del PDF es bajo demanda** en la interfaz: abrir el detalle no la pide, porque cada lectura queda auditada. El PDF descargado se conserva en memoria mientras la vista siga abierta.
5. **Nombre del archivo:** la interfaz construye `manuscript-<código>-v<n>.pdf` y descarta el `Content-Disposition` del servidor, de modo que ningún nombre original puede llegar al disco del Revisor aunque el backend lo enviara.
6. **La declaración «no tengo conflicto de interés» del formulario no se persiste:** es una exigencia de pantalla para el envío (CA de la TSK-67); el servidor no la recibe.
7. **Detalle del historial en la misma fila** de la lista, sin ruta nueva (el plan solo lista `evaluation-history/`).
8. **Bandeja de incidentes:** por defecto muestra los abiertos; `Resueltos` y `Todos` van en `?status=` y un valor desconocido vuelve al predeterminado.
9. **Reloj del contador:** cuenta contra el `due_at` del backend y corrige el desfase con la cabecera `Date` de la respuesta; el vencimiento real lo decide siempre el servidor (D-22).
10. **Refactores compartidos:** `core/http/blob-download.ts` (lectura del nombre y del error en un `Blob`) y `toPage` en `core/http/query-params.ts`; los módulos que los tenían los reexportan.

---

## 3. Lista de deuda técnica y ajustes pendientes

Prioridad: **Crítica** (resolver antes de cualquier `push` o despliegue) · **Alta** · **Media** · **Baja**.

| ID | Prioridad | Hallazgo | Ubicación | Ajuste recomendado |
|---|---|---|---|---|
| D-01 | **Crítica** | **Atendido solo en parte.** `credentials.txt` ya no está en el índice (commit `51cfcd7`) y figura en `.gitignore`, pero **sigue en el historial**: el commit `ad22b2c`, que lo añadió, está contenido en `origin/dev/jostin-setup`, `origin/develop`, `personal/develop` y `personal/main` según las referencias locales (el archivo contiene credenciales de una cuenta administradora; su valor no se reproduce aquí ni se leyó en esta auditoría). Retirarlo del índice no lo borra de los commits anteriores. | historial de git; `credentials.txt` | Tratar la credencial como expuesta: **rotarla ya**. Si se quiere eliminarla también del historial, hay que reescribirlo y hacer `push --force` en esas ramas, con aprobación explícita y avisando al equipo. Mover los datos de acceso a un gestor de secretos o a `.env`. |
| D-02 | **Alta** | Nginx no sirve HTTPS: sin `443`, sin `ssl_protocols`, sin redirección. Incumple el criterio de TSK-04 y RNF-06. Sin cambios. | `nginx/conf.d/default.conf`, `docker-compose.yml` | Añadir el bloque `listen 443 ssl` con TLS 1.2/1.3 y la redirección `80 → 443`; publicar `443`; montar `nginx/certs/`. |
| D-03 | **Alta** | `db` publica `5432` y `adminer` publica `8888` en todas las interfaces según el compose. En el entorno en ejecución **`adminer` ya está publicado en `0.0.0.0:8888`**; `db` todavía no (su contenedor se creó antes del cambio), de modo que el próximo `docker compose up` que lo recree lo expondrá. Contradice TSK-02. | `docker-compose.yml` (líneas de `ports` de `db` y `adminer`) | Mover ambos a un `docker-compose.override.yml` solo de desarrollo o ligarlos a `127.0.0.1`; fijar la versión de `adminer`; no incluirlos en producción. |
| D-04 | **Media** | `environment.production.ts` sigue con `production: false` y las claves duplicadas `apiUrl`/`apiBaseUrl`; solo `apiBaseUrl` se usa. | `frontend/src/environments/environment.production.ts`, `environment.ts` | Restaurar `production: true`; eliminar `apiUrl` o unificar el nombre. |
| D-05 | ~~Media~~ **Resuelta** | `.gitignore` ya cubre `credentials.txt` y `/graphify-out/`. | `.gitignore` | Ninguno. (Un patrón `credentials*.txt` cubriría variantes; opcional.) |
| D-06 | **Media** | Con `COOKIE_SECURE=1`, `SECURE_HSTS_SECONDS` de un año con `preload` y sin TLS en Nginx, la cookie `Secure` del refresh no viaja por HTTP en un host real y HSTS con preload es arriesgado antes de tener certificado válido. Sin cambios. | `backend/config/settings/production.py`, `.env.example` | Resolver D-02; mientras tanto, desarrollo local con `COOKIE_SECURE=0` y activar HSTS preload solo con el certificado institucional. |
| D-07 | **Media** | CI: el paso de pruebas del backend convierte «ninguna prueba recolectada» (`exit 5`) en éxito, tolerancia que ya no tiene sentido con 1312 pruebas; no existe job de pruebas del frontend (`ng test`, 1045 pruebas) ni de linter. Desde la TSK-58 el CI sí ejecuta la prueba de humo del volumen (`media-isolation`). | `.github/workflows/ci.yml` | Eliminar la tolerancia a `exit 5`; añadir `ng test --watch=false`. |
| D-08 | **Baja** | La imagen de producción copia `tests/` y `pytest.ini`, pero `requirements/production.txt` no instala `pytest`. Sin cambios. | `backend/Dockerfile`, `requirements/production.txt` | No copiar `tests/` a la imagen de producción o crear una etapa de pruebas. |
| D-09 | **Media** | `verify_integrity.sh` depende del comando `verify_integrity` (TSK-76), inexistente (solo hay `seed_roles` y `mark_expired_assignments`); la restauración de humo no se ejercitó. El cron ya programa también la expiración. | `scripts/verify_integrity.sh`, `scripts/cron/gpc.cron` | Aceptar como dependencia conocida hasta TSK-76; ejecutar una restauración de humo antes del piloto. |
| D-10 | **Media** | **Atendido solo en parte.** Hecho: la baja lógica revoca la asignación `ACTIVE` (TSK-48). Pendiente: (a) desactivar la `CatalogEntry` y retirar la copia pública al dar de baja un manuscrito aceptado (plan §4.8, pasos 5 y 7), que documenta el `xfail` de `test_verdict_concurrency.py`; (b) los receptores de las **once** señales de dominio (siete de la Fase 3 y cuatro de la Fase 4), que esperan a `notifications` (Fase 5). Hasta entonces el Editor **no se entera** de que un Revisor envió su evaluación, declaró un conflicto o reportó una fuga, y el Autor no recibe aviso de las rondas abiertas por un incidente: hay que mirar la bandeja. | `apps/publications/services/withdraw.py`, `apps/*/signals.py` | Implementar (a) con un receptor de `manuscript_withdrawing`/`manuscript_withdrawn` en `publications`; al hacerlo, quitar el `xfail`. (b) con TSK-75. |
| D-11 | **Media** (antes Baja) | Las **cuatro** secciones del dashboard del backend devuelven `{}`, incluida la del Autor (el informe anterior decía tres). El panel muestra «Sin datos por ahora» a todos los roles y HU-02/HU-03 no se cumplen del todo. **La Fase 4 lo agrava para el Revisor:** ya existen asignaciones, plazos y evaluaciones reales y `build_reviewer_section` sigue devolviendo `{}` (su docstring remite a la TSK-60 en adelante, que no lo llenó). | `apps/users/services/dashboard.py` | Implementar los contadores de cada sección (Autor: manuscritos por estado; Editor: nuevos envíos y vencidas; Revisor: asignaciones y plazos; Administrador: Fase 5). |
| D-12 | **Baja** | TSK-28 y TSK-84 nombran Jasmine/Karma; el proyecto usa Vitest (`@angular/build:unit-test`). Sin cambios. | `.spec-kit/tasks.md` (líneas 321 y 969) | Actualizar el texto de las tareas. |
| D-13 | **Baja** | Advertencia NG8113: `LoadingSpinnerComponent` importado y sin uso en `UnifiedDashboardComponent`. Sigue abierta (la corrección del 27/oct no la tocó). | `frontend/.../unified-dashboard.component.ts` | Quitar el import. |
| D-14 | **Baja** | Gunicorn definido dos veces (`CMD` de la imagen y `command` del compose). Sin cambios. | `backend/Dockerfile`, `docker-compose.yml` | Dejar una sola definición. |
| D-15 | **Baja** | `project_status.md` (versionado) afirma que no se ejecutaron pruebas; hay 1312 de backend y 1045 de frontend. | `project_status.md` | Actualizar la nota o fechar el documento como instantánea. |
| D-16 | **Baja** | `ruff` no está disponible en el contenedor de desarrollo (`No module named ruff`) ni se ejecuta en CI: el código de las TSK-46 a TSK-70 se escribió siguiendo el estilo vecino, sin linter. En el frontend, Prettier sí se aplicó a los archivos de la Fase 4, pero `editor.model.ts` y `expired-assignments.component.ts` ya lo incumplían antes (un `import` largo) y no se reformatearon. | `backend/requirements/development.txt`, `.github/workflows/ci.yml` | Añadir `ruff` a las dependencias de desarrollo y un paso de CI. |
| D-17 | **Media** | No existe ningún endpoint público del catálogo: un manuscrito aceptado queda en `CatalogEntry` con su copia pública, pero ningún visitante puede consultarlo (CA-HU-13-02, «disponible en el catálogo público en cinco minutos»). Las pantallas `features/catalog/**` son andamios. | `apps/publications/` (sin vistas de catálogo) | TSK-74 (backend) y TSK-80 (frontend). |
| D-18 | **Baja** | No hay rotación de logs para `/var/log/gpc-expire.log` (el cron corre cada minuto) ni para `gpc-backup.log`; la instalación de la plantilla de cron en el servidor no está verificada. | `scripts/cron/gpc.cron`, documentación | Añadir una regla de `logrotate` y una verificación de instalación en el runbook (TSK-88). |
| D-19 | ~~Alta~~ **Resuelta** | El Autor no podía leer las observaciones del veredicto: `AuthorEvaluationFeedbackSerializer` no estaba conectado. Ahora `AuthorManuscriptSerializer` expone `feedback` con la lista blanca de tres campos y solo tras un veredicto, con `prefetch` de veredictos y evaluaciones. Se actualizó una prueba existente que fijaba el conjunto exacto de campos de la respuesta del Autor, porque el contrato cambió a propósito. | `apps/publications/serializers.py`, `views.py` | Ninguno. |
| D-20 | **Baja** | `resolve_assignment` (`reviews/permissions.py`) trata como asignación cualquier objeto con `reviewer_id`; una `Evaluation` también lo tiene. Hoy nadie usa `IsAssignedReviewer` sobre evaluaciones (el historial usa `IsReviewer` y el ámbito `for_reviewer`), por lo que es una falla latente, no un defecto activo. | `apps/reviews/permissions.py` | Resolver por tipo (`isinstance(obj, Assignment)`) o documentar que la permission solo vale para asignaciones; añadir una prueba. |
| D-21 | **Baja** | El PDF sanitizado del Revisor se verifica por la cabecera `X-Accel-Redirect` y la sanitización por `pikepdf`, pero no se ha ejecutado una descarga real del Revisor a través de Nginx ni abierto el archivo servido en un visor. La prueba de humo del volumen (TSK-58) no incluye el endpoint del Revisor. | `scripts/smoke_media_isolation.sh`, runbook (TSK-88) | Añadir al humo una descarga autenticada del Revisor y comprobar que el cuerpo es el PDF sanitizado; incluirla en el runbook del piloto. |
| D-22 | **Baja** | El contador del Revisor corrige el desfase del reloj con la cabecera `Date` (precisión de segundos, más el retraso de la respuesta); es una ayuda de interfaz, no un cronómetro. El corte real lo aplica el servidor (`410`). | `frontend/.../reviewer.service.ts` (`serverOffset`), `deadline-countdown` | Si se quiere exactitud absoluta, añadir `server_now` al detalle del Revisor y usarlo en lugar de `Date`. |

**Archivos y configuraciones de entorno — resumen**

- **No versionado y correcto:** `.env` (permisos `0600`), `nginx/certs/*.pem`, respaldos y volcados.
- **Ya no versionado, pero presente en el historial publicado:** `credentials.txt` (D-01).
- **Sin versionar e ignorado:** `credentials.txt` y `graphify-out/` (D-05, resuelta).
- **Versionado con cambio indeseado:** `environment.production.ts` (D-04) y `docker-compose.yml` (D-03).

---

## 4. Siguiente paso

**Veredicto: la Fase 4 (TSK-58 a TSK-70) está completa y verificada.** El Revisor puede, de extremo a extremo, ver sus asignaciones y plazos, leer el manuscrito anonimizado y su PDF sanitizado, guardar un borrador privado, enviar una evaluación inmutable, declarar un conflicto de interés y reportar en confidencial una posible fuga de identidad; el Editor resuelve esos reportes una sola vez, con confirmación y sin que el Autor llegue a saberlo. El doble ciego se prueba en cuatro capas (ámbito, serializadores, permisos por objeto y artefactos) y también sobre el código fuente. Hay 1312 pruebas de backend y 1045 de frontend en verde y la compilación de producción es correcta. Lo que queda abierto es deuda de integración y de infraestructura, no defectos del flujo; la excepción sigue siendo la credencial publicada.

1. **Ya (no depende de código):** rotar la credencial de `credentials.txt` (D-01). El commit que la contiene está en cuatro ramas remotas.
2. **Antes de un despliegue o piloto:** D-02 (TLS), D-03 (puertos de `db` y `adminer`, este último ya publicado), D-06 y D-10 (retirada del catálogo al dar de baja y avisos sin receptor).
3. **Puede proceder en paralelo con la Fase 5:** D-04, D-07, D-11 (en especial la sección del Revisor), D-12, D-13, D-16, D-18 y D-20 a D-22.

**Qué sigue — Fase 5 (catálogo, auditoría y avisos), por el orden de `tasks.md`:**

- DevOps: TSK-71 (cron de avisos, limpieza e integridad) y TSK-72 (privilegios de BD sobre auditoría). **Ojo:** el cron de la TSK-71 invoca comandos que crea la TSK-76 (`send_pending_notifications`, `cleanup_idempotency_keys`, `verify_integrity`; D-09); conviene hacer la TSK-76 antes o programarlos sin habilitar.
- Backend: TSK-73 (consulta de auditoría), TSK-74 (catálogo público, cierra D-17), **TSK-75 (notificaciones, que da receptor a las once señales y cierra D-10b)**, TSK-76, TSK-77 a 79 (corrección de veredicto y pruebas).
- Al llegar la TSK-75 hay que **añadir la comprobación de no fuga sobre la notificación ya construida** (plan §2.9, punto 3): hoy solo se prueba el payload de las señales.
- Frontend: TSK-80 a 84; DevOps: TSK-85 y 86.

**Qué no se ha verificado todavía** (ver §0): el recorrido manual en navegador de las pantallas del Revisor y del Editor, la descarga del PDF sanitizado a través de Nginx (D-21) y que la imagen en ejecución incluya el código de la Fase 4 (requiere `docker compose up -d --build backend web`).

**Pendiente de tu orden:** confirmar el inicio de la TSK-71 (o la TSK-76 antes, ver arriba) y decidir qué hacer con D-01 (rotación de la credencial), que sigue siendo lo único crítico.
