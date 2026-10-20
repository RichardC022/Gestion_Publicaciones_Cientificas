# Implementation Plan: Flujo Editorial de Manuscritos Científicos

**Branch**: `001-editorial-workflow` | **Date**: 2026-10-20 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-editorial-workflow/spec.md`

## Summary

Implementar el flujo editorial completo de ScientificPub UNL sobre Django 5.1 + MySQL 8.0:
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
django-cors-headers, Pillow (transitivo si aplica), mysqlclient (driver MySQL)

**Storage**: MySQL 8.0+ (respaldo de datos de negocio); sistema de archivos `media/` protegido
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
| Restricciones / RNF | MySQL 8.0, container-first, HTTPS, migraciones dentro del contenedor | PASS |

**Resultado inicial**: Sin violaciones. No se requiere Complexity Tracking.

### Re-evaluación post-diseño (tras Phase 1)

| Principio | Cómo lo materializa el diseño | Estado |
|-----------|-------------------------------|--------|
| I. MVC sobre Django | Apps desacopladas; servicios (`ManuscriptService`, `AuditService`, `PDFService`) concentran la lógica; serializadores/vistas solo orquestan | PASS |
| II. RBAC + Doble Ciego | `IsRole` + `get_object`; serializadores de `reviews` sin identidad del Autor; PDF sanitizado con `pikepdf` antes de exponerlo | PASS |
| III. PDF + versionamiento inmutable | Validación estructural `pypdf`; `ManuscriptVersion` con `number` único y `unique_together`; no sobrescritura | PASS |
| IV. Auditoría inmutable | `AuditLog` append-only + triggers MySQL `SIGNAL SQLSTATE` | PASS |
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
├── settings.py          # settings base (MySQL, DRF, JWT, media, email)
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

## Complexity Tracking

> **Sin violaciones constitucionales. Esta sección se deja vacía a propósito.**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| — | — | — |
