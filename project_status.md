# Estado técnico del proyecto — Gestión de Publicaciones Científicas

> Auditoría de estructura realizada el 2026-10-25 sobre la rama `dev/jostin-setup`.
> Fuentes: `docker-compose.yml`, `backend/`, `frontend/`, `nginx/`, `scripts/` y `.spec-kit/plan.md`.
> No se ejecutaron pruebas ni contenedores: todo lo descrito sale de leer el código.
> El grafo `graphify-out/graph.json` no existe, por lo que no se usó.

---

## 1. Tecnologías

| Capa | Tecnología | Versión |
|---|---|---|
| Lenguaje backend | Python | 3.12 (`python:3.12-slim-bookworm`) |
| Framework web | Django | 5.2.18 |
| API REST | Django REST Framework | 3.15.2 |
| JWT | `djangorestframework-simplejwt` | 5.5.1 |
| Servidor de aplicación | Gunicorn | 26.2.0 (3 workers, timeout 120 s) |
| Base de datos | PostgreSQL | 16-alpine, driver `psycopg[binary]` 3.3.6 |
| Procesado de PDF | `pikepdf` | 10.17.0 |
| Pruebas backend | pytest, pytest-django, pytest-cov, factory-boy, freezegun | 9.1.1 / 4.14.0 / 7.1.0 / 3.3.3 / 1.5.5 |
| Frontend | Angular (standalone, `app.config.ts`) | ^22.2 |
| Lenguaje frontend | TypeScript / RxJS | ~6.0.2 / ~7.8 |
| Pruebas frontend | Vitest + jsdom | ^5.0 / ^30.0 |
| Borde / estáticos | Nginx | 1.27-alpine |
| Orquestación | Docker Compose | build multietapa (Node 22 → Nginx) |

---

## 2. Arquitectura

Multicontenedor con SPA y backend separados. Nginx es el único punto de entrada.

```
Navegador ──:80──▶ web (Nginx + SPA Angular)
                     │  /api/  ──────────▶ backend (Gunicorn + Django/DRF) ──▶ db (PostgreSQL 16)
                     │  /static/ ◀── static_data (ro)        │ rw
                     │  /_protected/, /_catalog/ (internal) ◀── media_data (ro)
```

### Servicios de `docker-compose.yml`

| Servicio | Imagen / build | Redes | Volúmenes | Notas |
|---|---|---|---|---|
| `db` | `postgres:16-alpine` | `backend_net` | `postgres_data` | Healthcheck `pg_isready`. Publica `5432` al host (cambio local sin commitear). |
| `backend` | `./backend/Dockerfile` | `backend_net`, `frontend_net` | `media_data` (rw), `static_data` (rw), `./scripts` (ro) | `env_file: .env`. Arranca con `check_env.sh` → `init_media.sh` → `migrate` → `collectstatic` → Gunicorn. Healthcheck contra `/api/health/`. |
| `web` | `frontend/Dockerfile` (contexto raíz) | `frontend_net` | `media_data` (ro), `static_data` (ro), `./nginx/certs` (ro) | Publica `80`. Espera a que `backend` esté sano. |
| `adminer` | `adminer` | `backend_net`, `frontend_net` | — | Solo desarrollo. Puerto `8888`. |

- `backend_net` es `internal: true`: ni `db` ni la red del backend tienen salida al exterior.
- Los volúmenes nombrados son `postgres_data`, `media_data` y `static_data`.

### Estructura del backend (`backend/apps/`)

| App | Estado | Contenido |
|---|---|---|
| `users` | Implementada | Usuario propio, `Role`, `UserRole`, `ReviewerProfile`, `LoginAttempt`, `RefreshToken`; autenticación JWT; panel unificado. |
| `publications` | Implementada | `Manuscript`, `ManuscriptAuthor`, `ManuscriptVersion`, `CorrectionRound`, `StatusEvent`, `IdempotencyKey`; capa de servicios (`drafts`, `submission`, `versions`, `withdraw`, `pdf`, `history`, `idempotency`, `storage`…). |
| `audit` | Implementada | `AuditLog` con cadena de hash y trigger append-only; `AuditService`. |
| `core` | Parcial | `health`, datos de demostración. |
| `reviews` | **Vacía** | `models.py`, `views.py`, `serializers.py` y `urls.py` tienen 0 líneas; solo existe `permissions.py`. |
| `notifications` | **Vacía** | `models.py` de 1 línea. |

`backend/config/` contiene `settings/{base,development,production}.py`, `api.py` (enrutador `/api/`), `exceptions.py` (envelope de errores), `middleware.py` (X-Request-ID), `pagination.py` y `health.py`.

### Estructura del frontend (`frontend/src/app/`)

- `core/`: `auth` (store, servicio, interceptor, guards de sesión, rol y cambios sin guardar), `http` (interceptores de error y de `X-Request-ID`, clave de idempotencia), `layout`, `models`, `services`.
- `features/`: `auth`, `dashboard`, `author`, `editor`, `reviewer`, `catalog`, `admin`, `notifications`, `forbidden`, `not-found`.
  - Solo `author` está comprobado como completo (Fase 2, con pruebas de integración). Las carpetas de `editor`, `reviewer`, `catalog`, `admin` y `notifications` existen, pero no se verificó su contenido.
- `shared/`: componentes (visor PDF), directivas, pipes y utilidades.

---

## 3. Patrones de seguridad y diseño aplicados

### Autenticación y sesión (JWT)
- Access token de 15 minutos (`JWT_ACCESS_MINUTES`), enviado como `Authorization: Bearer`, guardado **solo en memoria** en el SPA (nunca en `localStorage`).
- Refresh token de 7 días (`JWT_REFRESH_DAYS`) en cookie `gpc_refresh`: `HttpOnly`, `SameSite=Strict`, `Secure` en producción y `path=/api/auth/`. Se rota en cada refresh y se persiste en la tabla `RefreshToken` con motivo de revocación.
- Inactividad máxima de 30 minutos (`SESSION_IDLE_MINUTES`).
- Límite de 5 fallos por identificador en 15 minutos (`LoginAttempt`), con respuesta genérica.
- `InstitutionalJWTAuthentication` responde siempre `AUTH_INVALID` ante cualquier fallo (token vencido, malformado, usuario inexistente o cuenta deshabilitada), para impedir la enumeración de cuentas.
- El login no usa clases de autenticación, de modo que un `Authorization` viejo no lo bloquea.

### Roles y control de acceso
- Catálogo fijo: `AUTHOR`, `REVIEWER`, `EDITOR`, `ADMIN`. Los permisos son aditivos y cada vista revalida la relación con el objeto (`IsManuscriptOwner`).
- Un manuscrito fuera del ámbito del actor responde `404`, nunca `403`. El `403` se reserva para roles sin acceso al módulo.
- El frontend refuerza con `roles.guard.ts`, pero el backend es la barrera real.

### Doble ciego
- Se aplica en el backend y no depende de que Angular oculte datos: serializadores con listas de campos permitidos separadas por rol (`AuthorManuscriptSerializer`, y una vista de evaluación para el Autor sin identidad del Revisor).
- Cada versión guarda tres hashes SHA-256: `original_sha256`, `sanitized_sha256` y `metadata_sha256`.
- `PdfService.sanitize` produce la copia que lee el Revisor, sin `/Info`, XMP, `/PieceInfo`, anotaciones ni contenido activo. La reabre y la revisa de nuevo; si conserva contenido activo, se descarta y se rechaza la carga.
- Las notificaciones al Autor nunca incluyen el nombre del Revisor ni el reporte de fuga de identidad.
- Estado: la sanitización y el historial filtrado existen; los endpoints del Revisor aún no.

### Auditoría inmutable
- `audit_audit_log` es append-only por trigger de PostgreSQL (`prevent_audit_mutation`, migración `0002`), que rechaza `UPDATE` y `DELETE`.
- Cadena de hash: `entry_hash = sha256(JSON_canónico + previous_hash)`. Las inserciones se serializan con `pg_advisory_xact_lock`.
- `AuditService.record()` corre dentro de la misma transacción que la acción crítica. Si no puede escribir, la acción se revierte y se responde `503` (`AUDIT_UNAVAILABLE`).
- Solo guarda identificadores y códigos: nunca contraseñas, contenido de manuscritos ni comentarios confidenciales.
- `X-Request-ID` (middleware y Nginx) correlaciona cada solicitud con la auditoría.

### Integridad de datos
- Manuscritos: sin borrado físico (trigger `prevent_manuscript_delete`); baja lógica con `CheckConstraint` que liga `is_active=false` con `withdrawn_at`.
- `ManuscriptVersion` y `StatusEvent` son `AppendOnlyModel` con triggers de inmutabilidad.
- Bloqueo optimista con `lock_version` expuesto como `ETag` / `If-Match`.
- Idempotencia con `IdempotencyKey`: guarda el hash de la solicitud y la respuesta durante 24 horas, con unicidad `(user_id, endpoint, key)`.
- Código de seguimiento `GPC-AAAA-######` generado por una secuencia de PostgreSQL.

### Almacenamiento y volúmenes aislados
- Estructura de `media_data`: `private/{drafts,manuscripts}`, `public/catalog` y `tmp/uploads`, todos con permisos `0750`.
- Los PDF **nunca** salen por Django: este responde con `X-Accel-Redirect` a ubicaciones `internal` de Nginx (`/_protected/` privado con `no-store`, `/_catalog/` público con caché de 5 minutos). `/media/` está en `deny all`.
- `media_data` es de escritura para `backend` y de solo lectura para `web`. El grupo `media` usa GID 101, igual que `nginx`, para que Nginx pueda leer.
- El contenedor del backend corre como usuario `app` sin shell, con `umask 0027`. `.env` está ignorado por Git.
- Las cargas pasan por Nginx con `client_max_body_size 60m` y buffer a disco; Django aplica el límite real de 50 MB.

### Cabeceras y transporte
- Nginx envía CSP estricta (`default-src 'self'`, `frame-ancestors 'none'`, `object-src 'none'`), `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy` y `Permissions-Policy`; `server_tokens off`.
- En producción: HSTS de un año con preload, cookies de sesión y CSRF `Secure`, `SECURE_PROXY_SSL_HEADER`.
- Los certificados TLS (`nginx/certs/*.pem`) se montan en tiempo de ejecución y están ignorados por Git.

### Patrones de diseño
- Capa de servicios en `apps/*/services/`, con vistas delgadas.
- Envelope de errores uniforme `{ "error": { code, message, details, request_id } }` mediante `DomainError` y `ErrorCode`.
- Separación de serializadores por rol.
- Frontend con stores de estado (`auth.store.ts`, `api-feedback.store.ts`), interceptores HTTP y guards funcionales.

---

## 4. Guía de endpoints de la API

Prefijo común: `/api/`. Formato JSON, salvo la carga de PDF (`multipart/form-data`, campo `file`) y la descarga (`application/pdf`).

**Leyenda de la columna «Auth»:** `P` público; `Token` JWT institucional en `Authorization: Bearer <access>`; `Cookie` refresh token en cookie `HttpOnly`. Los roles son `A` Autor, `R` Revisor, `E` Editor y `ADM` Administrador.

**Estado:** ✅ implementado y verificado en el código · 🗓 planificado en `plan.md` §2, sin implementar.

### 4.1 Convenciones transversales

| Tema | Regla |
|---|---|
| Paginación | `page`, `page_size` (máx. 100), `search`, `ordering`. Filtros comunes: `status`, `area`, `date_from`, `date_to`. |
| Idempotencia | Cabecera `Idempotency-Key` (1–100 caracteres: letras, números, `. _ : -`). Obligatoria en `submit`, nueva versión, veredicto y habilitación de corrección. El servidor la conserva 24 h; repetirla devuelve la misma respuesta sin duplicar efectos. |
| Concurrencia | La respuesta de un manuscrito trae `ETag`. `PATCH` exige `If-Match` con ese valor; uno desactualizado devuelve `409`. |
| Trazabilidad | Toda respuesta incluye `X-Request-ID`. El cliente puede enviarlo si cumple `^[A-Za-z0-9@._~-]{1,64}$`. |
| Errores | Envelope `{ "error": { "code", "message", "details", "request_id" } }`. |

Códigos de error de dominio: `AUTH_INVALID`, `AUTH_LOCKED`, `FORBIDDEN`, `NOT_FOUND`, `STATE_CONFLICT`, `VERSION_CONFLICT`, `ASSIGNMENT_CONFLICT`, `VERDICT_CONFLICT`, `CORRECTION_NOT_AUTHORIZED`, `PDF_INVALID`, `PDF_TOO_LARGE`, `PDF_UNSUPPORTED`, `STORAGE_UNAVAILABLE`, `AUDIT_UNAVAILABLE`, `VALIDATION_ERROR`, `RATE_LIMITED`.

Códigos HTTP: `200`/`201`/`204` éxito; `400` validación o PDF inválido; `401` sin autenticación; `403` rol sin acceso al módulo; `404` inexistente o fuera de ámbito; `409` conflicto de estado, versión o duplicado; `410` plazo vencido o recurso retirado; `413` PDF > 50 MB; `415` `Content-Type` distinto de `multipart/form-data`; `429` límite de intentos; `503` auditoría, base de datos o almacenamiento no disponible.

### 4.2 Salud y panel

| Estado | Método | Ruta | Auth | Cabeceras especiales | Notas |
|---|---|---|---|---|---|
| ✅ | `GET` | `/api/health/` | P | — | Verifica base de datos y volumen de escritura. `200` / `503`. Lo usa el healthcheck de Docker. |
| ✅ | `GET` | `/api/dashboard/` | Token | — | Todas las secciones habilitadas (`author`, `reviewer`, `editor`, `admin`) en una respuesta. Una sección fallida no rompe el `200`. |

### 4.3 Auth

| Estado | Método | Ruta | Auth | Cabeceras especiales | Éxito | Notas |
|---|---|---|---|---|---|---|
| ✅ | `POST` | `/api/auth/login/` | P | — | `200` | Cuerpo con credenciales. Devuelve access token, usuario y roles, y fija la cookie de refresh. Errores `400`, `401`, `429`, `503`. |
| ✅ | `POST` | `/api/auth/refresh/` | Cookie | Cookie `gpc_refresh` | `200` | Rota el refresh token y devuelve un access nuevo. Errores `401`, `429`. |
| ✅ | `POST` | `/api/auth/logout/` | Token | Cookie `gpc_refresh` | `204` | Revoca el refresh y limpia la cookie. Revocación y auditoría van en una transacción: `503` si la auditoría falla. |
| ✅ | `GET` | `/api/auth/me/` | Token | — | `200` | Identidad, roles activos y permisos de navegación. |

### 4.4 Manuscripts (Autor y Editor)

Todas las rutas son `/api/manuscripts/...` y requieren `Token`. `{id}` y `{version_id}` son UUID.

| Estado | Método | Ruta | Roles | Cabeceras especiales | Éxito | Notas |
|---|---|---|---|---|---|---|
| ✅ | `GET` | `/api/manuscripts/` | A (propios), E (ámbito) | — | `200` | Paginado y filtrable. Con ambos roles se obtiene la unión. |
| ✅ | `POST` | `/api/manuscripts/` | A | Respuesta con `ETag` | `201` | Crea un `DRAFT`. No crea versión. |
| ✅ | `GET` | `/api/manuscripts/{id}/` | A (propio), E | Respuesta con `ETag` | `200` | Serializador distinto por rol. |
| ✅ | `PATCH` | `/api/manuscripts/{id}/` | A (propio) | **`If-Match`** obligatorio; respuesta con `ETag` | `200` | Solo en `DRAFT` o `REQUIRES_CORRECTIONS`. Otro estado, `409`. |
| ✅ | `POST` | `/api/manuscripts/{id}/draft-file/` | A (propio) | `Content-Type: multipart/form-data` (campo `file`) | `201` / `200` | Solo en `DRAFT`. `201` si adjunta, `200` si reemplaza. No crea versión. `413`, `415`. |
| ✅ | `POST` | `/api/manuscripts/{id}/submit/` | A (propio) | **`Idempotency-Key`** obligatoria; respuesta con `ETag` | `201` | Solo desde `DRAFT`. Crea v1 y ronda 0, congela metadatos y devuelve el código de seguimiento y el sello de integridad. Misma clave repite la respuesta; clave nueva sobre un manuscrito ya enviado, `409`. |
| ✅ | `GET` | `/api/manuscripts/{id}/versions/` | A (propio), E | — | `200` | Lista paginada de iteraciones, de la más antigua a la más nueva. |
| ✅ | `POST` | `/api/manuscripts/{id}/versions/` | A (propio) | **`Idempotency-Key`** obligatoria; `multipart/form-data` (campo `file`); respuesta con `ETag` | `201` | Solo en `REQUIRES_CORRECTIONS`. Misma clave con el mismo PDF repite; con otro PDF, `409`. |
| ✅ | `GET` | `/api/manuscripts/{id}/versions/{version_id}/file/` | A (propio), E | — | `200` | PDF original por `X-Accel-Redirect`. Se audita antes; si falla, `503`. El Revisor no accede aquí. |
| ✅ | `GET` | `/api/manuscripts/{id}/history/` | A (propio), E | — | `200` | Historial inmutable, también tras la baja lógica. Sin actor, ruta ni hash de la copia sanitizada. |
| ✅ | `POST` | `/api/manuscripts/{id}/withdraw/` | A (propio) | Respuesta con `ETag` | `200` | Baja lógica desde cualquier estado. El motivo es obligatorio en `UNDER_REVIEW` y `ACCEPTED`. Un segundo intento, `409`. |

No existe `DELETE` para manuscritos. El plan además prevé que el Revisor asignado consulte `GET /api/manuscripts/{id}/` y `history/` de forma anonimizada. Esa parte está 🗓 y no aparece en el código actual.

### 4.5 Reviews (Revisor) — 🗓 sin implementar

Roles: `R` dueño de la asignación. `reviews/views.py` y `urls.py` están vacíos. La «Regla de corte»: el envío final solo se acepta si `now() < due_at`; en el instante exacto devuelve `410`.

| Método | Ruta | Cabeceras especiales | Éxito | Notas |
|---|---|---|---|---|
| `GET` | `/api/reviewer/assignments/` | — | `200` | Bandeja propia con plazo y estado. |
| `GET` | `/api/reviewer/assignments/{id}/` | — | `200` | Detalle anonimizado. |
| `GET` | `/api/reviewer/assignments/{id}/document/` | — | `200` | PDF **sanitizado** por `X-Accel-Redirect`, nombre genérico. `410` si la asignación no está activa. |
| `GET` | `/api/reviewer/assignments/{id}/evaluation/` | — | `200` | Borrador o evaluación final propia. |
| `PUT` | `/api/reviewer/assignments/{id}/evaluation/` | `If-Match` / `ETag` (`lock_version`) | `200` | Guarda el borrador privado. |
| `POST` | `/api/reviewer/assignments/{id}/evaluation/submit/` | — | `200` | Envío final inmutable; notifica al Editor. `503` si falla la auditoría. |
| `POST` | `/api/reviewer/assignments/{id}/conflict/` | — | `200` | Declara conflicto de interés y bloquea la evaluación. |
| `POST` | `/api/reviewer/assignments/{id}/identity-leak/` | — | `201` | Cuerpo: `report_type` (`IDENTITY_LEAK` u `OTHER`) y `description`. Canal confidencial. |
| `GET` | `/api/reviewer/evaluations/` | — | `200` | Historial propio, sin identidad de Autores. |
| `GET` | `/api/reviewer/evaluations/{id}/` | — | `200` | Solo lectura. |

### 4.6 Editor — 🗓 sin implementar

Rol: `E`. Todas requieren `Token`.

| Método | Ruta | Cabeceras especiales | Éxito | Notas |
|---|---|---|---|---|
| `GET` | `/api/editor/submissions/` | — | `200` | Bandeja de manuscritos en `SUBMITTED`. |
| `GET` | `/api/editor/submissions/{id}/` | — | `200` | Detalle completo. |
| `POST` | `/api/editor/submissions/{id}/start-review/` | — | `200` | Pasa a `UNDER_REVIEW`; puede asignar revisor en la misma transacción. |
| `GET` | `/api/editor/reviewers/` | — | `200` | Revisores elegibles por área y sin conflicto. |
| `POST` | `/api/editor/manuscripts/{id}/assignments/` | — | `201` | Asignación única; `due_at = assigned_at + 20 días`. Una activa previa, `409`. |
| `GET` | `/api/editor/manuscripts/{id}/assignments/` | — | `200` | Historial de asignaciones. |
| `POST` | `/api/editor/assignments/{id}/revoke/` | — | `200` | Motivo obligatorio. |
| `GET` | `/api/editor/assignments/expired/` | — | `200` | Asignaciones vencidas pendientes de decisión. |
| `POST` | `/api/editor/manuscripts/{id}/verdicts/` | **`Idempotency-Key`** obligatoria | `201` | Registra el veredicto; abre ronda o publica en el catálogo. Segundo veredicto sin autorización, `409`. |
| `GET` | `/api/editor/manuscripts/{id}/verdicts/` | — | `200` | Historial, incluidos los reemplazos administrativos. |
| `GET` | `/api/editor/manuscripts/{id}/evaluations/` | — | `200` | Evaluaciones completas con identidad del Revisor. |
| `GET` | `/api/editor/incidents/` | — | `200` | Incidentes confidenciales. |
| `POST` | `/api/editor/incidents/{id}/resolve/` | — | `200` | Cuerpo: `resolution` (`REQUEST_ANONYMIZED_VERSION`, `REASSIGN` o `DISMISS`). Una sola vez. |

### 4.7 Admin — 🗓 sin implementar

Rol: `ADM`. Todas requieren `Token`. No hay endpoints de gestión de usuarios ni roles: el aprovisionamiento es por comando de gestión o Django Admin.

| Método | Ruta | Cabeceras especiales | Éxito | Notas |
|---|---|---|---|---|
| `GET` | `/api/admin/audit/` | — | `200` | Consulta global, paginada y filtrable. |
| `GET` | `/api/admin/audit/{id}/` | — | `200` | Detalle; el propio acceso se audita. Incluye `can_authorize_correction`. |
| `POST` | `/api/admin/verdicts/{id}/authorize-correction/` | **`Idempotency-Key`** obligatoria | `201` | Cuerpo: `reason` (10–1000 caracteres). Solo el veredicto más reciente y con una autorización activa por veredicto, si no `409`. |

### 4.8 Catalog (público) — 🗓 sin implementar

Sin autenticación. Solo muestra artículos `ACCEPTED` con `is_active = true`; no expone evaluaciones, revisores, historial ni auditoría. Caché máxima de 5 minutos.

| Método | Ruta | Cabeceras especiales | Éxito | Notas |
|---|---|---|---|---|
| `GET` | `/api/catalog/` | — | `200` | Búsqueda y filtros. |
| `GET` | `/api/catalog/{code}/` | — | `200` | Ficha pública. `{code}` es el código `GPC-AAAA-######`. |
| `GET` | `/api/catalog/{code}/document/` | — | `200` | PDF de la versión aceptada por `X-Accel-Redirect` público. `410` si fue retirado. |

### 4.9 Notifications — 🗓 sin implementar

Requieren `Token`; el aviso debe ser del propio usuario.

| Método | Ruta | Cabeceras especiales | Éxito | Notas |
|---|---|---|---|---|
| `GET` | `/api/notifications/` | — | `200` | Avisos propios, leídos y no leídos. |
| `PATCH` | `/api/notifications/{id}/read/` | — | `200` | Marca un aviso como leído. |
| `POST` | `/api/notifications/read-all/` | — | `204` | Marca todos como leídos. |

---

## 5. Avance por fase (`.spec-kit/tasks.md`)

| Fase | Alcance | Estado |
|---|---|---|
| 0 | Fundación | Hecha |
| 1 | Identidad y panel | Hecha (auth, `me`, `dashboard`) |
| 2 | Autor y documentos (TSK-40 a TSK-44) | **Cerrada** con TSK-44 (commit `d87934e`) |
| 3 | Editor y veredictos | Pendiente |
| 4 | Revisor y doble ciego | Pendiente |
| 5 | Catálogo, auditoría y avisos | Pendiente |
| 6 | Endurecimiento | Pendiente |

La siguiente fase es la 3 (Editor y veredictos).

---

## 6. Observaciones y deuda técnica

Cambios locales sin commitear detectados en la auditoría:

1. **`frontend/src/environments/environment.production.ts` tiene `production: false`.** Antes era `true`. Afecta al build de producción; conviene revertirlo si no fue intencional.
2. **`environment*.ts` tiene ahora `apiUrl` y `apiBaseUrl`** con el mismo valor. Hay que confirmar cuál usa el código y dejar uno.
3. **`db` publica el puerto `5432` y `adminer` quedó en `frontend_net` (puerto `8888`).** Debilita el aislamiento de `backend_net`; son ajustes de desarrollo que no deben llegar a producción.
4. **`credentials.txt` está sin versionar y `.gitignore` no lo cubre.** Riesgo de commit accidental con credenciales; conviene añadirlo al `.gitignore`.
5. **`frontend/proxy.conf.json`** apunta a `http://localhost` (el Nginx del compose) y es coherente con `ng serve --proxy-config`.

Pendientes operativos:

- El contenedor `backend` en ejecución usa la imagen previa a TSK-44; hay que reconstruirlo (`docker compose build backend`) para que existan `submit` y `versions`.
- `ManuscriptService.listVersions` (frontend) está implementado pero ninguna pantalla lo usa todavía; el historial usa `history/`.
- `reviews/` y `notifications/` en el backend están vacías, así que arrancar la Fase 3 y la 4 implica crear sus modelos desde cero.
- `scripts/` contiene `backup.sh`, `restore.sh`, `verify_integrity.sh` y `check_env.sh`; sus contenidos no se revisaron en esta auditoría.
- **Nginx solo escucha en el puerto 80** (`listen 80`) y el compose publica solo el `80`. Los certificados de `nginx/certs/` se montan, pero ningún bloque `server` los usa todavía. El TLS y el puerto 443 quedan por configurar antes de producción.
- **`/admin/` no está enrutado por Nginx:** solo `/api/`, `/static/` y la SPA tienen `location`, así que el Django Admin no es accesible a través del compose. `location /` lo entregaría a la SPA.

---

## 7. Enlaces y referencias

### 7.1 Accesos del entorno local

Valores del `docker-compose.yml` y de las configuraciones actuales. Los usuarios y contraseñas **no** se documentan aquí: están en `.env` (ignorado por Git) y en `credentials.txt` (sin versionar).

| Recurso | URL / dirección | Qué es | Notas |
|---|---|---|---|
| SPA Angular (producción local) | `http://localhost/` | Servicio `web`: Nginx sirviendo la SPA compilada | Puerto 80. Las rutas profundas caen en `index.html`. |
| API REST | `http://localhost/api/` | Nginx → `backend:8000` (Gunicorn) | Devuelve `{"service": "gestion-publicaciones-cientificas", "api": "v1"}`. |
| Health check | `http://localhost/api/health/` | Estado de la base de datos y del volumen de escritura | Es el que usa el healthcheck de Docker. |
| Servidor de desarrollo Angular | `http://localhost:4200/` | `npm start` en `frontend/` (`ng serve --proxy-config proxy.conf.json`) | Puerto por defecto de Angular (no hay `port` en `angular.json`). El proxy reenvía `/api` a `http://localhost`, es decir, al Nginx del compose; el compose debe estar levantado. |
| Adminer | `http://localhost:8888/` | Cliente web de la base de datos | Solo desarrollo. En el formulario: sistema PostgreSQL, servidor `db`, y base, usuario y contraseña de `.env` (`POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`). |
| PostgreSQL desde el host | `localhost:5432` | Puerto publicado por `db` | Cambio local sin commitear; cualquier cliente SQL sirve (DBeaver, `psql`, el panel de bases de datos del IDE). |
| Django Admin | `/admin/` (solo dentro de la red de Docker en `backend:8000`) | Administración de Django | **No accesible por Nginx**; ver la sección 6. |

Comandos útiles (desde la raíz del repositorio):

```bash
docker compose up -d --build        # levanta db, backend, web y adminer
docker compose build backend        # reconstruye el backend (necesario tras TSK-44)
docker compose logs -f backend      # registros de Gunicorn/Django
docker compose exec db pg_isready   # comprueba la base de datos
```

### 7.2 Documentación del proyecto

| Documento | Ruta | Contenido |
|---|---|---|
| Constitución | `.spec-kit/constitution.md` | Principios no negociables del proyecto |
| Especificación | `.spec-kit/specify.md` | Historias de usuario y requisitos |
| Aclaraciones | `.spec-kit/clarify.md` | Decisiones que precisan la especificación |
| Plan técnico | `.spec-kit/plan.md` | Modelos (§1), endpoints (§2), frontend (§3), almacenamiento (§4), despliegue (§5), seguridad (§6), pruebas (§7) |
| Tareas | `.spec-kit/tasks.md` | TSK por fase (0 a 6) |
| Respaldos | `scripts/BACKUP.md` | Procedimiento de respaldo y restauración |
| Certificados TLS | `nginx/certs/README.md` | Cómo colocar `fullchain.pem` y `privkey.pem` |
| README general | `README.md` | Presentación del repositorio |
| README del frontend | `frontend/README.md` | Notas del proyecto Angular |
| Variables de entorno | `.env.example` | Plantilla de `.env` (el real nunca se versiona) |
| CI | `.github/workflows/` | Flujos de GitHub Actions |

### 7.3 Documentación oficial del stack

**Backend**

| Tecnología | Documentación |
|---|---|
| Django 5.2 | https://docs.djangoproject.com/en/5.2/ |
| Django REST Framework | https://www.django-rest-framework.org/ |
| Simple JWT | https://django-rest-framework-simplejwt.readthedocs.io/ |
| Gunicorn | https://docs.gunicorn.org/ |
| psycopg 3 | https://www.psycopg.org/psycopg3/docs/ |
| pikepdf | https://pikepdf.readthedocs.io/ |
| pytest-django | https://pytest-django.readthedocs.io/ |
| factory_boy | https://factoryboy.readthedocs.io/ |

**Base de datos**

| Tecnología | Documentación |
|---|---|
| PostgreSQL 16 | https://www.postgresql.org/docs/16/ |
| Triggers (base de la auditoría inmutable) | https://www.postgresql.org/docs/16/triggers.html |
| Advisory locks (serialización de la cadena de hash) | https://www.postgresql.org/docs/16/explicit-locking.html#ADVISORY-LOCKS |
| Imagen Docker `postgres` | https://hub.docker.com/_/postgres |
| Adminer | https://www.adminer.org/ |

**Frontend**

| Tecnología | Documentación |
|---|---|
| Angular | https://angular.dev/ |
| RxJS | https://rxjs.dev/ |
| TypeScript | https://www.typescriptlang.org/docs/ |
| Vitest | https://vitest.dev/ |

**Infraestructura**

| Tecnología | Documentación |
|---|---|
| Docker | https://docs.docker.com/ |
| Docker Compose | https://docs.docker.com/compose/ |
| Dockerfile multietapa | https://docs.docker.com/build/building/multi-stage/ |
| Nginx | https://nginx.org/en/docs/ |
| Nginx `proxy_pass` y buffering de cuerpos | https://nginx.org/en/docs/http/ngx_http_proxy_module.html |
| `X-Accel-Redirect` (entrega protegida de PDF) | https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_ignore_headers |
| Nginx en contenedor | https://hub.docker.com/_/nginx |

### 7.4 Estándares y buenas prácticas relacionadas con los patrones aplicados

| Tema | Referencia |
|---|---|
| `ETag` | https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/ETag |
| `If-Match` (bloqueo optimista) | https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/If-Match |
| `Idempotency-Key` (borrador del IETF) | https://datatracker.ietf.org/doc/draft-ietf-httpapi-idempotency-key-header/ |
| Content-Security-Policy | https://developer.mozilla.org/en-US/docs/Web/HTTP/CSP |
| Cookies `HttpOnly`, `Secure`, `SameSite` | https://developer.mozilla.org/en-US/docs/Web/HTTP/Cookies |
| HSTS | https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Strict-Transport-Security |
| OWASP: hoja de trucos de autenticación | https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html |
| OWASP: JWT para Java (principios aplicables a cualquier lenguaje) | https://cheatsheetseries.owasp.org/cheatsheets/JSON_Web_Token_for_Java_Cheat_Sheet.html |
| OWASP: carga de archivos | https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html |
| RFC 7519 (JWT) | https://www.rfc-editor.org/rfc/rfc7519 |
