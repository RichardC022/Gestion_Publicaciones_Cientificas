# Phase 1 — Data Model: Flujo Editorial de Manuscritos Científicos

**Feature**: `001-editorial-workflow` | **Date**: 2026-10-20

Convenciones (Constitución, Estándares de Datos): `BigAutoField` como PK por defecto;
`created_at`/`updated_at` en todo modelo de negocio vía `core.BaseModel`; `PROTECT`/`SET_NULL`
en entidades críticas; `db_table` e índices explícitos en campos de filtrado frecuente. Idioma
técnico en inglés para modelos/campos.

## 1. Entidades y campos

### 1.1 `core.BaseModel` (abstracto)

| Campo | Tipo | Reglas |
|-------|------|--------|
| `id` | BigAutoField | PK |
| `created_at` | DateTimeField(auto_now_add) | inmutable |
| `updated_at` | DateTimeField(auto_now) | — |

`Meta.abstract = True`.

### 1.2 `core.AuditLog` (inmutable / append-only)

| Campo | Tipo | Reglas |
|-------|------|--------|
| `id` | BigAutoField | PK |
| `actor` | FK → `users.User`, `SET_NULL`, null | responsable de la acción |
| `action` | CharField / Choice | p. ej. `LOGIN`, `MANUSCRIPT_CREATED`, `STATUS_CHANGED`, `REVIEWER_ASSIGNED`, `EVALUATION_SUBMITTED`, `VERDICT_ISSUED`, `ROLE_CHANGED` |
| `entity_type` | CharField | nombre de la entidad afectada |
| `entity_id` | CharField/BigInteger | id de la entidad afectada |
| `payload` | JSONField, blank | detalles no sensibles |
| `created_at` | DateTimeField(auto_now_add) | fecha/hora |

**Reglas de inmutabilidad**: `save()` bloquea updates si ya existe; `delete()` lanza excepción;
triggers PostgreSQL `BEFORE UPDATE`/`BEFORE DELETE` que ejecutan una función PL/pgSQL con
`RAISE EXCEPTION`. Solo-lectura en la
API para el Administrador (FR-021, FR-022, Principio IV).

### 1.3 `users.User` (extiende `AbstractUser`)

| Campo | Tipo | Reglas |
|-------|------|--------|
| (campos base) | — | `AbstractUser` (`username`, `password`, `email`, ...) |
| `document_id` | CharField, unique | identidad institucional |
| `active_role` | CharField / Choice | rol activo: `AUTHOR`/`REVIEWER`/`EDITOR`/`ADMIN` |
| `is_author_enabled` | BooleanField | habilitado como Autor |
| `is_reviewer_enabled` | BooleanField | habilitado como Revisor |
| `is_editor_enabled` | BooleanField | habilitado como Editor |
| `roles` | M2M → `auth.Group` | grupos de rol |

**Métodos**: `switch_role(role)`, `has_role(role)`, `is_author`/`is_reviewer`/`is_editor`/`is_admin`
(propiedades derivadas). **Regla**: los permisos combinan roles sin escalar privilegios; el rol
activo restringe la experiencia (FR-002, FR-004).

### 1.4 `publications.ResearchArea` / `publications.Category`

| Modelo | Campos |
|--------|--------|
| `ResearchArea` | `name` (unique), `description` |
| `Category` | `name` (unique), `description` |

### 1.5 `publications.Manuscript`

| Campo | Tipo | Reglas |
|-------|------|--------|
| `title` | CharField | obligatorio (FR-005) |
| `abstract` | TextField | obligatorio |
| `keywords` | CharField/JSON | obligatorio |
| `language` | CharField | obligatorio |
| `research_area` | FK → `ResearchArea`, `PROTECT` | obligatorio |
| `category` | FK → `Category`, `PROTECT` | obligatorio |
| `doi` | CharField | obligatorio (FR-005) |
| `issn` | CharField | obligatorio |
| `funding` | TextField | obligatorio |
| `status` | CharField / Choice (`ManuscriptStatus`) | inicia en `DRAFT` (FR-007) |
| `submitting_author` | FK → `users.User`, `PROTECT` | Autor principal responsable |
| `version` | PositiveIntegerField(default=0) | bloqueo optimista (FR-004a) |
| `is_active` | BooleanField(default=True) | baja lógica (FR-012) |
| `published_at` | DateTimeField, null | al pasar a `PUBLISHED` |

**Índices**: `status`, `submitting_author`, `research_area`, `category`; GIN/`db_index` sobre
`title`/`keywords` para el catálogo.

**Ver FR-002/FR-011**: solo el Autor principal (`submitting_author`) edita, versiona y da de baja.

### 1.6 `publications.ManuscriptVersion` (inmutable)

| Campo | Tipo | Reglas |
|-------|------|--------|
| `manuscript` | FK → `Manuscript`, `PROTECT` | relación |
| `number` | PositiveIntegerField | secuencia 1, 2, ... única por manuscrito (FR-010) |
| `file` | FileField (upload_to protegido) | PDF validado |
| `is_anonymized` | BooleanField | marca de sanitización (doble ciego) |
| `uploaded_by` | FK → `users.User`, `SET_NULL` | autor de la carga |
| `created_at` | DateTimeField(auto_now_add) | fecha de entrega |

**Restricción**: `unique_together = (manuscript, number)`; no sobrescritura (cada entrega crea un
registro nuevo); el Revisor accede solo a la versión vigente (FR-010a, Principio III).

### 1.7 `publications.Author` (autoría / coautoría)

| Campo | Tipo | Reglas |
|-------|------|--------|
| `manuscript` | FK → `Manuscript`, `PROTECT` | — |
| `user` | FK → `users.User`, `SET_NULL`, null | si es usuario del sistema |
| `full_name` | CharField | obligatorio |
| `email` | EmailField | **protegido del Revisor** |
| `affiliation` | CharField | protegido del Revisor |
| `orcid` | CharField | obligatorio (FR-005) |
| `order` | PositiveSmallIntegerField | orden de autoría |
| `is_principal` | BooleanField | marca al Autor principal |

**Restricción**: `unique_together` por (manuscript, order). Solo un `is_principal=True` por
manuscrito (FR-011, clarificación Q2).

### 1.8 `reviews.ReviewAssignment`

| Campo | Tipo | Reglas |
|-------|------|--------|
| `manuscript` | FK → `Manuscript`, `PROTECT` | — |
| `reviewer` | FK → `users.User`, `PROTECT` | rol Revisor |
| `assigned_by` | FK → `users.User`, `SET_NULL` | Editor |
| `status` | CharField / Choice (`AssignmentStatus`) | `PENDING`/`ACCEPTED`/`DECLINED`/`COMPLETED` |
| `due_date` | DateField, null | plazo |

**Restricción**: `unique_together = (manuscript, reviewer)` — impide reasignar el mismo revisor
(FR-014, escenario 3.6).

### 1.9 `reviews.Evaluation`

| Campo | Tipo | Reglas |
|-------|------|--------|
| `assignment` | OneToOne/FK → `ReviewAssignment`, `PROTECT` | — |
| `comments_to_author` | TextField | observaciones |
| `comments_to_editor` | TextField | confidencial |
| `recommendation` | CharField / Choice (`Recommendation`) | `ACCEPT`/`MINOR`/`MAJOR`/`REJECT` |
| `submitted_at` | DateTimeField(auto_now_add) | — |

**Regla**: es la evidencia que habilita el veredicto (FR-016, FR-018).

### 1.10 `reviews.ReviewVerdict`

| Campo | Tipo | Reglas |
|-------|------|--------|
| `manuscript` | OneToOne/FK → `Manuscript`, `PROTECT` | — |
| `issued_by` | FK → `users.User`, `SET_NULL` | Editor |
| `decision` | CharField / Choice (`VerdictDecision`) | `ACCEPTED`/`REJECTED`/`REQUIRES_REVISION` |
| `observations` | TextField | para el Autor |
| `issued_at` | DateTimeField(auto_now_add) | — |

**Regla**: solo se emite si existe al menos una `Evaluation` (FR-016, SC-005).

## 2. Enumeraciones / máquinas de estado

### 2.1 `ManuscriptStatus`

`DRAFT → RECEIVED → UNDER_REVIEW → {REQUIRES_REVISION → UNDER_REVIEW | ACCEPTED | REJECTED}`
`ACCEPTED → PUBLISHED`; `* → WITHDRAWN` (solo por baja lógica del Autor principal, FR-012).

**Transiciones válidas** (validadas en `ManuscriptService`):

| Desde | A | Disparador | Requisito |
|-------|---|-----------|-----------|
| DRAFT | RECEIVED | Autor envía | metadatos + PDF válidos |
| RECEIVED | UNDER_REVIEW | Editor | — |
| UNDER_REVIEW | REQUIRES_REVISION | Editor | con observaciones |
| REQUIRES_REVISION | UNDER_REVIEW | Autor entrega nueva versión | en estado REQUIRES_REVISION (FR-009) |
| UNDER_REVIEW | ACCEPTED/REJECTED | Editor | ≥ 1 evaluación (FR-016) |
| ACCEPTED | PUBLISHED | Editor | — |
| * (salvo PUBLISHED) | WITHDRAWN | Autor principal | baja lógica (FR-012) |

Transiciones fuera de esta tabla → rechazadas (escenarios 2.5, 4.3; casos límite).

### 2.2 Otras enumeraciones

- `AssignmentStatus`: `PENDING`, `ACCEPTED`, `DECLINED`, `COMPLETED`.
- `Recommendation`: `ACCEPT`, `MINOR_REVISION`, `MAJOR_REVISION`, `REJECT`.
- `VerdictDecision`: `ACCEPTED`, `REJECTED`, `REQUIRES_REVISION`.
- `UserRole` / `active_role`: `AUTHOR`, `REVIEWER`, `EDITOR`, `ADMIN`.

## 3. Relaciones (resumen)

```text
User (1) ──< Manuscript (submitting_author, PROTECT)
Manuscript (1) ──< ManuscriptVersion (PROTECT)
Manuscript (1) ──< Author (PROTECT)         # coautoría
Manuscript (1) ──< ReviewAssignment (PROTECT)
User (reviewer) (1) ──< ReviewAssignment (PROTECT)
ReviewAssignment (1) ── Evaluation (PROTECT)
Manuscript (1) ── ReviewVerdict (PROTECT)
Manuscript (M) >── ResearchArea (PROTECT)
Manuscript (M) >── Category (PROTECT)
User (M) >── Group/roles (M2M)
AuditLog >── User (actor, SET_NULL)
```

## 4. Reglas de validación (derivadas de requisitos)

1. **Metadatos** (FR-005): todos los campos obligatorios presentes; si falta alguno → rechazo
   indicando el campo (SC-012).
2. **PDF** (FR-006): parseo estructural válido y tamaño ≤ `MAX_UPLOAD_SIZE`; si no → `400`.
3. **Versionado** (FR-010): nueva versión solo en `REQUIRES_REVISION`; `number` incremental único;
   nunca sobrescribir.
4. **Doble ciego** (FR-019, RNF-07): los serializadores de `reviews` **excluyen** `Author.full_name`,
   `Author.email`, `Author.affiliation` y cualquier identificador del Autor; el PDF expuesto al
   Revisor va sanitizado (`is_anonymized=True`).
5. **Veredicto** (FR-016): requiere ≥ 1 `Evaluation`; en otro caso → `400`/`409`.
6. **Concurrencia** (FR-004a): UPDATE condicional por `version`; conflicto → `409`.
7. **Auditoría** (FR-021, FR-022): toda transición crítica genera `AuditLog`; prohibido update/delete.

## 5. RNF / índices de rendimiento

- Índices en `Manuscript.status`, `Manuscript.submitting_author`, `ManuscriptVersion.manuscript`
  (+`number`), `ReviewAssignment.reviewer`, `AuditLog.created_at`.
- Paginación obligatoria en listados y catálogo (RNF-01, SC-006).
- Búsqueda del catálogo sobre `title`/`keywords`/`abstract`, restringida a `status ∈
  {ACCEPTED, PUBLISHED}` e `is_active=True` (FR-024, assumption del spec).
