# Phase 0 — Research: Flujo Editorial de Manuscritos Científicos

**Feature**: `001-editorial-workflow` | **Date**: 2026-10-20

Este documento resuelve las incógnitas técnicas del contexto de plan y fija las decisiones de
implementación con su justificación, alineadas a la Constitución v2.0.0.

## R1. Validación real de archivos PDF

- **Decision**: Validar el contenido binario del archivo con `pypdf` (`PdfReader`) dentro del
  serializador de carga, verificando el encabezado `%PDF-` y que el documento parsee sin error
  (`PdfReadError`). Rechazar cualquier archivo que no sea un PDF válido con `400 Bad Request`.
  Imponer el tamaño máximo en el validador (`file.size > settings.MAX_UPLOAD_SIZE`) y reforzar
  con `DATA_UPLOAD_MAX_MEMORY_SIZE` / `FILE_UPLOAD_MAX_MEMORY_SIZE`.
- **Rationale**: La extensión `.pdf` y el MIME declarado por el cliente son falsificables; solo
  el parseo estructural garantiza que sea un PDF real (FR-006, Principio III).
- **Alternatives considered**: `python-magic` (sniff de encabezado, más débil por sí solo);
  `pikepdf` (validación qpdf más estricta, se reserva para sanitización); `FileExtensionValidator`
  de Django (solo línea base de extensión).

## R2. Anonimización de metadatos del PDF (doble ciego)

- **Decision**: Sanitizar el PDF con `pikepdf` antes de exponerlo a un Revisor: eliminar el
  diccionario de información (`DocInfo`, incluye Author/Producer/CreationDate) y el paquete XMP
  (`del pdf.Root.Metadata`), y reescribir el archivo (`pdf.save(..., linearize=True)`) para
  descartar revisiones incrementales previas. Ejecutar en la capa de servicio (`PDFService`),
  nunca en el modelo ni en la vista.
- **Rationale**: Tanto `/Info` como XMP (y el historial de actualizaciones) filtran identidad;
  es requisito no negociable que el Revisor jamás acceda a datos del Autor (FR-019, SC-003,
  Principio II). `pikepdf` es más exhaustivo que `pypdf` en fugas a nivel de objeto.
- **Alternatives considered**: `pypdf` (`writer.metadata = None`, menos exhaustivo en `/Creator`
  dentro de XMP); `exiftool` vía subprocess (más completo pero añade dependencia de sistema);
  PyMuPDF.

## R3. Bloqueo optimista y edición concurrente (Django ORM + MySQL 8.0)

- **Decision**: Campo `version = PositiveIntegerField(default=0)` en modelos editables. Cada
  guardado usa un UPDATE condicional atómico:
  `Model.objects.filter(pk=obj.pk, version=claimed).update(campo=..., version=F("version") + 1)`.
  Si el número de filas afectadas es 0, se lanza un conflicto (`409 Conflict`) indicando recargar.
  Exponer `version` en el serializador. Implementado en `ManuscriptService`.
- **Rationale**: Los editores mantienen formularios abiertos minutos; el bloqueo pesimista
  (`select_for_update`) retiene locks entre peticiones y arriesga deadlocks/agotamiento del pool
  en MySQL InnoDB. El UPDATE condicional es atómico y sin bloqueo (FR-004a, SC-011).
- **Alternatives considered**: `django-concurrency` (`IntegerVersionField`, añade dependencia);
  `select_for_update()` dentro de `transaction.atomic()` (solo para secciones críticas muy cortas);
  `django-optimistic-lock` (sin mantenimiento).

## R4. Autenticación JWT y RBAC

- **Decision**: Emitir/refrescar tokens con `djangorestframework-simplejwt`
  (`TokenObtainPairView` con rotación de refresh y blacklist). Los roles son **Grupos de Django**
  (`Autor`, `Revisor`, `Editor`, `Administrador`) mapeados al campo `active_role` del `User`.
  Autorización con una clase de permiso propia `IsRole(allowed_roles={...})` y verificación
  por-objeto (`has_perm`/`has_role`) en `get_object`. Selección de rol activo al autenticar
  mediante endpoint dedicado.
- **Rationale**: Un backend propio solo necesita emitir/refrescar tokens, no el stack completo de
  `dj-rest-auth` (registro, MFA, cookies). Mantiene autenticación (authN) separada de autorización
  (authZ) y combina roles sin escalar privilegios (FR-001..FR-004, Principio II).
- **Alternatives considered**: `dj-rest-auth[JWT]` (demasiado para el alcance); `django-guardian`
  (permisos por objeto a nivel de BD, útil si crece la granularidad); `django-rules` (reglas por
  predicado sin filas en BD).

## R5. Auditoría inmutable (append-only)

- **Decision**: Modelo `AuditLog` en `apps/core` que extiende un `BaseModel` de solo-anexado:
  se sobrescriben `save()` y `delete()` para bloquear modificaciones y borrados, y se refuerza la
  inmutabilidad a nivel de **base de datos** con triggers MySQL `BEFORE UPDATE`/`BEFORE DELETE`
  que emiten `SIGNAL SQLSTATE '45000'`. Toda escritura pasa por `AuditService` (acción, usuario,
  entidad afectada, fecha). La bitácora se expone solo-lectura al Administrador.
- **Rationale**: Las protecciones a nivel ORM son eludibles por `queryset.update()` o SQL crudo;
  la Constitución (Principio IV) exige inmutabilidad real y trazabilidad (FR-021, FR-022, SC-004).
- **Alternatives considered**: `django-auditlog` (diffs a nivel de campo, pero no garantiza
  append-only a nivel BD); `django-simple-history` (snapshots); `django-pghistory` (solo Postgres).

## R6. Estados del ciclo de vida y transiciones

- **Decision**: Enum `ManuscriptStatus` con 8 estados: `DRAFT`, `RECEIVED`, `UNDER_REVIEW`,
  `REQUIRES_REVISION`, `ACCEPTED`, `REJECTED`, `PUBLISHED`, `WITHDRAWN`. Las transiciones se
  centralizan en `ManuscriptService` con una máquina de estados explícita que valida cada cambio
  antes de persistirlo y emite el evento de auditoría correspondiente.
- **Rationale**: Centralizar las transiciones evita estados inconsistentes y facilita las pruebas
  de los escenarios de aceptación y casos límite (FR-007..FR-016).
- **Alternatives considered**: `django-fsm` / `django-fsm-2` (útil, pero se prefiere control
  explícito y tipado para mantener desacoplamiento y trazabilidad fina).

## R7. Entorno de pruebas y CI

- **Decision**: pytest + pytest-django con `config.settings_test` (SQLite en memoria) para
  pruebas rápidas en CI; pruebas de contrato sobre DRF. La suite completa debe pasar en verde
  junto con ruff, black --check, isort --check, `manage.py check` y `makemigrations --check`.
- **Rationale**: Determinismo y velocidad en CI (Principio V); MySQL real se valida en el
  entorno Docker (container-first) cuando Docker está disponible.
- **Alternatives considered**: Ejecutar MySQL en CI (más lento, mayor costo); solo pruebas
  manuales (insuficiente para Principio V).

## R8. Metadatos obligatorios del manuscrito

- **Decision**: Campos obligatorios: `title`, `abstract`, `keywords`, `language`, `research_area`
  /`category`, `doi`, `issn`, `funding`, y `orcid` por autor, más el PDF. Todos validados como
  requeridos (sin diferir ninguno a fases futuras).
- **Rationale**: Clarificación Q5 de la sesión de `/speckit.clarify`; cubre evaluación, catálogo e
  interoperabilidad sin retrabajo posterior (FR-005, SC-012).
- **Alternatives considered**: Diferir DOI/ISSN/ORCID/financiamiento (rechazado por decisión del
  analista/institución).

## Outstanding unknowns

Ninguna. Todas las incógnitas del Technical Context quedaron resueltas.
