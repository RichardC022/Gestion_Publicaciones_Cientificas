# Quickstart — Flujo Editorial de Manuscritos Científicos

**Feature**: `001-editorial-workflow` | **Date**: 2026-10-20

Guía de validación de extremo a extremo. No incluye código de implementación; los cuerpos de
modelos/servicios/migraciones y la suite completa viven en `tasks.md` y la fase de implementación.

## Prerequisites

- Docker Desktop en ejecución (container-first, Constitución).
- Variables de entorno cargadas desde `.env` (copiado de `.env.example`), incluyendo `SECRET_KEY`,
  `DEBUG`, `ALLOWED_HOSTS`, `DB_*` y credenciales de correo.
- Datos base: grupos de rol (`Autor`, `Revisor`, `Editor`, `Administrador`), algunas
  `ResearchArea`/`Category` y usuarios de prueba para cada rol.

## Setup

```bash
cp .env.example .env
docker compose up -d --build
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
docker compose exec web python manage.py seed_demo   # comando de gestión de la implementación
```

En host sin Docker (solo para verificación rápida de código/tests):

```powershell
$env:SECRET_KEY='test'; python -m pytest -q
```

## Validation scenarios

Cada escenario corresponde a las historias de usuario y criterios de éxito del spec. Los
detalles de campos y reglas están en [`data-model.md`](./data-model.md); los endpoints y códigos
de respuesta en [`contracts/openapi.yaml`](./contracts/openapi.yaml).

### VS-1 — Autenticación y selección de rol (US1 / FR-001..FR-004)

1. `POST /api/v1/auth/login/` con credenciales institucionales válidas → `200` con `access`/`refresh`.
2. Reintentar con password erróneo → `400`; superar el umbral → `429` (bloqueo temporal).
3. Con un docente habilitado como Autor y Revisor, `POST /auth/switch-role/` → la experiencia
   queda restringida al rol activo.

**Esperado**: cada rol accede solo a sus operaciones; acciones no autorizadas → `403`.

### VS-2 — Registro y versionado (US2 / FR-005..FR-012)

1. `POST /manuscripts/` con metadatos completos + PDF → `201`, estado `DRAFT`.
2. Repetir sin un campo obligatorio (p. ej. `doi`) → `400` indicando el campo (SC-012).
3. Subir un `.docx` o un PDF corrupto → `400` (FR-006).
4. `PATCH /manuscripts/{id}/` con `version` desactualizada → `409` (SC-011).
5. Tras pasar a `REQUIRES_REVISION`, `POST /manuscripts/{id}/versions/` → crea v2; v1 permanece
   intacta y consultable (SC-008).
6. Intentar subir versión en estado distinto de `REQUIRES_REVISION` → `400` (escenario 2.5).
7. Como coautor (no principal) intentar `PATCH` → `403` (SC-009).

### VS-3 — Asignación y doble ciego (US3 / FR-013..FR-020)

1. Editor: `POST /manuscripts/{id}/submit-review/` → `UNDER_REVIEW` (FR-013).
2. Editor: `POST /manuscripts/{id}/assignments/` con `reviewer_ids` → `201`.
3. Reasignar el mismo revisor → `400` (escenario 3.6).
4. Revisor: `GET /reviews/assignments/` → respuesta **sin** identidad del Autor (FR-019, SC-003).
5. Revisor: `POST /reviews/assignments/{id}/evaluation/` → `201`.
6. Revisor intenta `GET /manuscripts/{id}/versions/` → `403` (SC-010).

**Esperado**: el Revisor nunca ve nombre, correo, filiación del Autor ni versiones anteriores.

### VS-4 — Correcciones y veredicto (US4 / FR-015, FR-016)

1. Editor solicita correcciones → `REQUIRES_REVISION` + notificación (FR-015).
2. Intentar veredicto sin evaluaciones → `400` (SC-005).
3. Con ≥ 1 evaluación, emitir `ACCEPTED`/`REJECTED`/`REQUIRES_REVISION` → `200`.

### VS-5 — Auditoría, historial y catálogo (US5 / FR-021..FR-025)

1. Ejecutar acciones críticas (login, transición, asignación, veredicto) y verificar que cada
   una generó un `AuditLog`.
2. `GET /api/v1/audit/` como Administrador → bitácora ordenada; intentar `PUT`/`DELETE` → `405`.
3. `GET /api/v1/catalog/?q=...&category=...` sin autenticación → solo artículos `ACCEPTED`/`PUBLISHED`.
4. Verificar recepción de correos en los eventos clave (FR-025); un fallo de envío no bloquea la
   acción.

## Expected outcomes / gates

- CI en verde: `ruff`, `black --check`, `isort --check`, `manage.py check`,
  `makemigrations --check`, `pytest` (Constitución V).
- Todos los escenarios anteriores reproducibles de forma determinista.
- Cobertura explícita de casos límite (concurrencia, metadatos faltantes, transiciones inválidas,
  acceso a versiones, coautor sin permisos).
