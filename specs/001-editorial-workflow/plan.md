# Implementation Plan: Flujo Editorial de Manuscritos Científicos

**Branch**: `001-editorial-workflow` | **Date**: 2026-10-20 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-editorial-workflow/spec.md`

## Summary

Implementar el flujo editorial completo de ScientificPub UNL sobre Django 5.1 + PostgreSQL 16:
autenticación institucional con selección de rol (RBAC), registro y versionado inmutable de
manuscritos en PDF, asignación de revisores con doble ciego (anonimización de PDF), emisión de
veredictos, auditoría inmutable, notificaciones por correo y catálogo público. La API se expone
con Django REST Framework autenticada por JWT (`djangorestframework-simplejwt`). El enfoque
técnico se ancla en la Constitución v2.0.0: MVC/MVT, RBAC + doble ciego (Principio II),
PDF exclusivo y versionamiento inmutable (Principio III), auditoría inmutable (Principio IV) y
calidad/CI (Principio V).

## Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**: Django 5.1.x, djangorestframework, djangorestframework-simplejwt
(JWT), pypdf (validación de PDF), pikepdf (sanitización de metadatos), django-filter,
django-cors-headers, Pillow (transitivo si aplica), psycopg (driver PostgreSQL)

**Storage**: PostgreSQL 16+ (respaldo de datos de negocio); sistema de archivos `media/` protegido
para PDFs (almacenamiento de objetos S3 como evolución futura tras interfaz de servicio)

**Testing**: pytest + pytest-django (unitarias, integración y contrato); `config.settings_test`
con SQLite en memoria para CI rápido; pruebas de contrato contra DRF

**Target Platform**: Servidor Linux con contenedores Docker / Docker Compose (container-first)

**Project Type**: Web application (backend API Django; frontend fuera del alcance de esta
iteración o servido por plantillas Django)

**Performance Goals**: 50 usuarios concurrentes, tasa de éxito ≥ 95%, p95 < 2 s (RNF-01); busca
en catálogo < 2 s en el 95% de los casos (SC-007)

**Constraints**: PDF exclusivamente (rechazo `400` a otros formatos); anonimato de doble ciego
aplicado en la capa de consulta y serializadores; PDFs no expuestos como estáticos públicos;
comunicación HTTPS; secretos por variables de entorno (RNF-06)

**Scale/Scope**: Conjunto de usuarios de la comunidad universitaria (docentes, autores,
editores, revisores, administradores); ~decenas de miles de manuscritos y versiones a largo
plazo; 8 estados de ciclo de vida; 4 actores con RBAC combinable

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principio | Gate | Estado |
|-----------|------|--------|
| I. Arquitectura MVC sobre Django | Stack Python 3.11+/Django; lógica en modelos/servicios; sin frameworks de servidor alternativos; apps desacopladas (`users`, `publications`, `reviews`, `core`) | PASS |
| II. RBAC + Doble Ciego (NO NEGOCIABLE) | Permisos por rol en cada endpoint; anonimización de identidad del Autor en consultas/serializadores; sanitización de PDF antes de exponerlo al Revisor | PASS |
| III. PDF exclusivo + versionamiento inmutable (NO NEGOCIABLE) | Validación real de PDF; cada versión con identificador único; no sobrescritura; almacenamiento protegido | PASS |
| IV. Auditoría inmutable | Bitácora append-only; inmutabilidad reforzada a nivel de BD; eventos críticos cubiertos | PASS |
| V. Calidad / Pruebas / CI | black (88), isort (black), ruff 0 warnings, type hints + docstrings PEP 257, pytest determinista, CI verde | PASS |
| Restricciones / RNF | PostgreSQL 16, container-first, HTTPS, migraciones dentro del contenedor | PASS |

**Resultado inicial**: Sin violaciones. No se requiere Complexity Tracking.

### Re-evaluación post-diseño (tras Phase 1)

| Principio | Cómo lo materializa el diseño | Estado |
|-----------|-------------------------------|--------|
| I. MVC sobre Django | Apps desacopladas; servicios (`ManuscriptService`, `AuditService`, `PDFService`) concentran la lógica; serializadores/vistas solo orquestan | PASS |
| II. RBAC + Doble Ciego | `IsRole` + `get_object`; serializadores de `reviews` sin identidad del Autor; PDF sanitizado con `pikepdf` antes de exponerlo | PASS |
| III. PDF + versionamiento inmutable | Validación estructural `pypdf`; `ManuscriptVersion` con `number` único y `unique_together`; no sobrescritura | PASS |
| IV. Auditoría inmutable | `AuditLog` append-only + triggers PostgreSQL (`RAISE EXCEPTION`) | PASS |
| V. Calidad / Pruebas / CI | pytest + settings_test; suite en CI junto a linters y `makemigrations --check` | PASS |

**Resultado post-diseño**: Sin violaciones introducidas. Gate superado.

## Project Structure

### Documentation (this feature)

```text
specs/001-editorial-workflow/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
│   └── openapi.yaml
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
config/
├── settings.py          # settings base (PostgreSQL, DRF, JWT, media, email)
├── settings_test.py     # SQLite en memoria para tests/CI
├── urls.py              # enrutador raíz (solo despacho)
├── asgi.py
└── wsgi.py

apps/
├── core/                # BaseModel abstracto, AuditLog inmutable, servicios transversales
│   ├── models.py
│   ├── migrations/
│   ├── services/        # AuditService, StorageService, PDFService (validación/sanitización)
│   ├── permissions.py   # clases de permiso RBAC
│   └── tests/
├── users/               # User, UserRole, switch_role(); auth institucional + JWT
│   ├── models.py
│   ├── serializers.py
│   ├── views.py
│   ├── services/
│   ├── migrations/
│   └── tests/
├── publications/        # Manuscript, ManuscriptVersion, Author, ResearchArea, Category
│   ├── models.py
│   ├── serializers.py
│   ├── views.py
│   ├── services/        # ManuscriptService (versionado, transiciones, bloqueo optimista)
│   ├── migrations/
│   └── tests/
└── reviews/             # ReviewAssignment, Evaluation, ReviewVerdict (doble ciego)
    ├── models.py
    ├── serializers.py   # serializadores anonimizados (sin identidad del Autor)
    ├── views.py
    ├── services/
    ├── migrations/
    └── tests/

media/                   # PDFs protegidos (acceso por rol, no estático público)
tests/                   # pruebas transversales de integración/contrato si aplica
```

**Structure Decision**: Aplicación web con backend Django único, organizada como **apps
desacopladas** dentro de `apps/` (`core`, `users`, `publications`, `reviews`), tal como fija la
Constitución (Principio I). La lógica de dominio vive en `services/` y `models.py`; las vistas y
serializadores solo orquestan entrada/salida. No se introduce frontend separado en esta
iteración: la API REST/DRF es la interfaz, consumible por un frontend posterior.

## Architecture Design (Django)

Esta sección materializa las cuatro exigencias del arquitecto y es la entrada directa de
`/speckit.tasks`. Cada bloque respeta las capas de la Constitución: **modelos** (dominio +
persistencia), **servicios** (lógica de negocio), **serializadores/vistas** (orquestación E/S).

### A1. Modelos exactos de base de datos

Convenciones: `BigAutoField` PK; `created_at`/`updated_at` vía `core.BaseModel`; `db_table`
explícito; `PROTECT`/`SET_NULL` en entidades críticas; `verbose_name` en inglés.

```text
core_audit_log (AuditLog)                     # append-only, inalterable
├── id                BigAutoField PK
├── actor_id          FK users_user  SET_NULL null        # responsable
├── action            CharField(32, indexed)              # LOGIN, STATUS_CHANGED, ...
├── entity_type       CharField(64, indexed)
├── entity_id         BigAutoField (indexed, sin FK para preservar histórico)
├── payload           JSONField blank (sin datos sensibles)
└── created_at        DateTimeField(auto_now_add, indexed)

users_user (User : AbstractUser)              # AUTH_USER_MODEL
├── document_id       CharField(20, unique)               # identidad institucional
├── email             EmailField(unique)                  # institucional
├── active_role       CharField(16, choices=UserRole)     # rol activo de sesión
├── is_author_enabled / is_reviewer_enabled / is_editor_enabled  BooleanField
└── groups (M2M auth.Group)                               # roles = grupos Django

users_userrole (UserRole)                     # catálogo de roles (Autor/Revisor/Editor/Admin)
├── code              CharField(16, unique)
└── name              CharField(64)

publications_research_area / publications_category
├── name              CharField(128, unique)
└── description       TextField blank

publications_manuscript (Manuscript : BaseModel)
├── title             CharField(512, indexed)
├── abstract          TextField
├── keywords          CharField(512, indexed)
├── language          CharField(8)
├── research_area_id  FK ResearchArea PROTECT (indexed)
├── category_id       FK Category     PROTECT (indexed)
├── doi               CharField(128)                      # obligatorio
├── issn              CharField(16)                       # obligatorio
├── funding           TextField                           # obligatorio
├── status            CharField(16, choices=ManuscriptStatus, indexed)  # inicia DRAFT
├── submitting_author_id FK users.User PROTECT (indexed)  # Autor principal
├── version           PositiveIntegerField(default=0)     # bloqueo optimista
├── is_active         BooleanField(default=True, indexed) # baja lógica
└── published_at      DateTimeField null blank

publications_manuscript_version (ManuscriptVersion)       # inmutable
├── manuscript_id     FK Manuscript PROTECT (indexed)
├── number            PositiveIntegerField                # 1,2,... (FR-010)
├── file              FileField(upload_to='manuscripts/%Y/%m/')
├── is_anonymized     BooleanField(default=False)
├── uploaded_by_id    FK users.User SET_NULL null
├── created_at        DateTimeField(auto_now_add)
└── UNIQUE (manuscript_id, number)

publications_author (Author)                  # autoría / coautoría (protegida del Revisor)
├── manuscript_id     FK Manuscript PROTECT
├── user_id           FK users.User SET_NULL null
├── full_name         CharField(256)
├── email             EmailField                         # protegido del Revisor
├── affiliation       CharField(256)                     # protegido del Revisor
├── orcid             CharField(32)                      # obligatorio (FR-005)
├── order             PositiveSmallIntegerField          # orden de autoría
├── is_principal      BooleanField(default=False)        # único por manuscrito
└── UNIQUE (manuscript_id, order)

reviews_review_assignment (ReviewAssignment : BaseModel)
├── manuscript_id     FK Manuscript PROTECT
├── reviewer_id       FK users.User  PROTECT (indexed)
├── assigned_by_id    FK users.User  SET_NULL
├── status            CharField(16, choices=AssignmentStatus)
├── due_date          DateField null blank
└── UNIQUE (manuscript_id, reviewer_id)                   # impide reasignar (esc. 3.6)

reviews_evaluation (Evaluation : BaseModel)
├── assignment_id     OneToOne ReviewAssignment PROTECT
├── comments_to_author TextField
├── comments_to_editor TextField
├── recommendation    CharField(24, choices=Recommendation)
└── submitted_at      DateTimeField(auto_now_add)

reviews_review_verdict (ReviewVerdict : BaseModel)
├── manuscript_id     OneToOne Manuscript PROTECT
├── issued_by_id      FK users.User SET_NULL
├── decision          CharField(24, choices=VerdictDecision)
├── observations      TextField
└── issued_at         DateTimeField(auto_now_add)
```

**Réplica exacta en código esperada en `data-model.md`** (fuente de verdad de campos/tipos).

### A2. Diseño de vistas MVC y rutas API

Django materializa MVC como **MVT + capa de servicios**. Regla constitucional: la lógica de
negocio NO vive en vistas ni en `urls.py`.

| Capa | Arquitectura | Responsabilidad |
|------|--------------|-----------------|
| Modelo | `apps/*/models.py` | Entidades, constraints, `BaseModel`, `AuditLog` |
| Servicio | `apps/*/services/` | Transiciones, versionado, doble ciego, validación PDF, auditoría |
| Vista (Controlador) | `apps/*/views.py` (DRF ViewSets) | Orquestar E/S, invocar servicios, mapear errores a HTTP |
| Serializador | `apps/*/serializers.py` | Forma de los datos y **proyección por rol** |
| Enrutador | `config/urls.py` + `apps/*/urls.py` | Solo despacho (`DefaultRouter`) |

Rutas (contrato completo en `contracts/openapi.yaml`):

```text
/api/v1/auth/login/                 POST    -> TokenObtainPairView (JWT)
/api/v1/auth/refresh/               POST    -> TokenRefreshView (rotación)
/api/v1/auth/switch-role/           POST    -> UserViewSet.switch_role()  [IsAuthenticated]

/api/v1/manuscripts/                GET/POST      -> ManuscriptViewSet (Autor principal)
/api/v1/manuscripts/{id}/           GET/PATCH     -> detalle/edición (bloqueo optimista)
/api/v1/manuscripts/{id}/withdraw/  POST          -> ManuscriptService.withdraw()
/api/v1/manuscripts/{id}/versions/  GET/POST      -> ManuscriptVersionViewSet
/api/v1/manuscripts/{id}/submit-review/        POST -> EditorialService.submit_to_review()
/api/v1/manuscripts/{id}/assignments/          POST -> EditorialService.assign_reviewers()
/api/v1/manuscripts/{id}/request-revision/     POST -> EditorialService.request_revision()
/api/v1/manuscripts/{id}/verdict/              POST -> EditorialService.issue_verdict()

/api/v1/reviews/assignments/                    GET  -> ReviewerAssignmentViewSet (anonimizado)
/api/v1/reviews/assignments/{id}/evaluation/    POST -> ReviewService.submit_evaluation()

/api/v1/catalog/                    GET     -> PublicCatalogView (AllowAny; solo ACCEPTED/PUBLISHED)
/api/v1/audit/                      GET     -> AuditLogViewSet (solo Admin, ReadOnly)
```

**Clases de permiso** (`core/permissions.py`): `IsAuthor`, `IsReviewer`, `IsEditor`, `IsAdmin`,
`IsRole(allowed_roles)` (combina roles del usuario sin escalar privilegios, FR-004).

### A3. Estrategia del Doble Ciego a nivel de ORM

Objetivo: el rol Revisor **jamás** obtiene identidad del Autor, aplicado en la capa de consulta
y en los serializadores (no solo en la interfaz) — Principio II + RNF-07 + FR-019 + SC-003.

1. **QuerySet dedicado y proyección mínima (`reviews/services/queries.py`)**:
   `AnonymousManuscriptQuerySet` que llama `.only(...)`/`.defer(...)` para excluir los campos
   relacionados con autoría y, sobre todo, **no hace `select_related('authors')` ni
   `submitting_author`**. La relación `Author` (con `full_name`, `email`, `affiliation`) no se
   une nunca en consultas del revisor.
2. **Manager segregado**: `Manuscript.reviewer_objects = ReviewerManuscriptManager()` que
   devuelve solo manuscritos asignados al revisor y sin joins a autoría.
3. **Serializadores anonimizados (`reviews/serializers.py`)**:
   `AnonymizedManuscriptSerializer` expone únicamente `id`, `title`, `abstract`, `keywords`,
   `language`, `research_area`, `category`, versión vigente (`number`, `file` sanitizado). No
   declara campos de autor. El `SerializerMethodField` de cualquier dato derivado tiene prohibido
   resolver nombres.
4. **Defensa en profundidad**: un test guardarraíl (`test_double_blind.py`) serializa cada
   respuesta del revisor y **falla** si aparece cualquier `full_name`/`email`/`affiliation`/
   `orcid` del autor ni el `submitting_author`. Es el gate de regresión del anonimato.
5. **PDF sanitizado**: la versión expuesta al revisor es la vigente con `is_anonymized=True`
   (A4); nunca se sirve el archivo original.

> La restricción se aplica por **proyección de consulta + serializador + test guardarraíl**, no
> por lógica condicional en la vista (evita fugas accidentales en listados o búsquedas).

### A4. Estrategia de control de archivos PDF y estados

**Validación de archivo** (`core/services/pdf_service.py`):
- Extensión + `python-magic` como prefiltro y **parseo estructural** con `pypdf`
  (`PdfReader`) para confirmar `%PDF-` y ausencia de corrupción → si falla, `400 Bad Request`
  (FR-006, Principio III).
- Tamaño máximo por `settings.MAX_UPLOAD_SIZE` en el validador; refuerzo con
  `DATA_UPLOAD_MAX_MEMORY_SIZE`/`FILE_UPLOAD_MAX_MEMORY_SIZE`.

**Anonimización** (antes de exponer al Revisor):
- `pikepdf`: `DocInfo = None`, eliminar `Root.Metadata` (XMP), reescribir con `linearize=True`
  para descartar historial incremental → se guarda como versión `is_anonymized=True`.

**Versionado inmutable** (FR-009, FR-010, Principio III):
- Cada corrección crea un `ManuscriptVersion` nuevo con `number = max+1`; **jamás** `UPDATE`
  sobre el archivo anterior. `UNIQUE(manuscript_id, number)` garantiza integridad.
- Se permite la nueva versión **solo** en estado `REQUIRES_REVISION`; cualquier otro estado →
  `400`.

**Almacenamiento protegido**:
- `media/manuscripts/%Y/%m/` **no** servido como estático. Descarga/exposición **solo** vía
  endpoint autorizado (`FileResponse` con verificación de rol y de versión vigente); el revisor
  recibe el PDF sanitizado, nunca la ruta cruda.

**Máquina de estados** (`publications/services/manuscript_service.py`): transiciones validadas
centralmente (tabla en `data-model.md`); cada transición emite `AuditService.log(...)`. Estados:
`DRAFT → RECEIVED → UNDER_REVIEW → {REQUIRES_REVISION|ACCEPTED|REJECTED}`, `ACCEPTED → PUBLISHED`,
`* → WITHDRAWN` (baja lógica).

**Interoperabilidad DOI** (previsto, fuera del alcance de esta iteración según Constitución): el
campo `doi` se almacena ya; la resolución/redirección a repositorios externos se expondrá tras
una interfaz de servicio (`InteroperabilityService`) sin acoplarse a modelos.

## Complexity Tracking

> **Sin violaciones constitucionales. Esta sección se deja vacía a propósito.**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| — | — | — |
