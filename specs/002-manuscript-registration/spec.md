# Feature Specification: Registro de Manuscrito con Metadatos y PDF Válido

**Feature Branch**: `feature/SPEC-002-manuscript-registration`

**Created**: 2026-10-19

**Status**: Draft

**Input**: User description: "SPEC-002: El registro de manuscritos debe exigir todos los metadatos obligatorios definidos por el proyecto y un archivo PDF válido para iniciar el proceso editorial (RF-02, criterios REG-04.1 a REG-04.4)."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Registro completo de un manuscrito (Priority: P1)

Un autor (Docente UNL) autenticado registra un nuevo manuscrito: completa todos los metadatos obligatorios definidos por el proyecto, adjunta el documento en formato PDF y envía la solicitud. El sistema valida que todo esté presente y correcto, crea el registro y da inicio al proceso editorial.

**Why this priority**: Es el origen de todo el flujo editorial de la plataforma; sin registro de manuscrito no hay nada que revisar, asignar ni publicar.

**Independent Test**: Puede probarse de forma aislada enviando un registro con todos los metadatos obligatorios y un PDF válido, verificando que se crea el registro con HTTP `201 Created`.

**Acceptance Scenarios**:

1. **Given** un autor autenticado con todos los metadatos obligatorios completos y un archivo PDF válido, **When** envía la solicitud de registro, **Then** el sistema crea el registro del manuscrito y responde HTTP `201 Created`.
2. **Given** un autor autenticado, **When** envía el formulario de registro, **Then** el sistema le presenta claramente qué metadatos son obligatorios.
3. **Given** un manuscrito recién registrado, **When** el autor lo consulta, **Then** el sistema muestra el registro con sus metadatos y el estado inicial del proceso editorial.

---

### User Story 2 - Rechazo de registros incompletos o con PDF inválido (Priority: P1)

Un autor intenta registrar un manuscrito sin todos los metadatos obligatorios, o adjuntando un archivo que no es un PDF válido (extensión incorrecta, contenido dañado o archivo vacío). El sistema rechaza el envío, indica qué falta o qué es inválido, y no crea ningún registro.

**Why this priority**: Es la contraparte de integridad obligatoria de la US1 (criterios REG-04.1 a REG-04.3); sin ella el proceso editorial se iniciaría con datos incompletos o archivos inutilizables. Misma prioridad crítica que la US1.

**Independent Test**: Puede probarse de forma aislada enviando, por un lado un registro con metadatos incompletos y por otro un registro con un archivo no-PDF o dañado, verificando el rechazo en ambos casos y la inexistencia de registros creados.

**Acceptance Scenarios**:

1. **Given** un autor con metadatos obligatorios incompletos, **When** intenta enviar el registro, **Then** el sistema rechaza el envío, informa qué campos faltan y no crea ningún registro.
2. **Given** un archivo que no es PDF (por extensión o por contenido), **When** el autor intenta adjuntarlo, **Then** el sistema rechaza el archivo e informa que solo se aceptan documentos PDF válidos.
3. **Given** un archivo PDF dañado o vacío, **When** el autor intenta adjuntarlo, **Then** el sistema lo rechaza como PDF inválido.
4. **Given** un registro rechazado, **When** el autor corrige los datos o el archivo, **When** vuelve a enviar, **Then** el sistema procesa el nuevo envío según las reglas normales.

---

### User Story 3 - Visualización del manuscrito registrado por el autor (Priority: P2)

El autor consulta el detalle de un manuscrito que ya registró: ve sus metadatos y el estado del proceso editorial, con la garantía de que la versión PDF almacenada es la que él adjuntó.

**Why this priority**: Da confianza y trazabilidad al autor tras el registro; no es requisito para iniciar el proceso editorial, por eso va detrás del registro y su validación.

**Independent Test**: Puede probarse registrando un manuscrito y luego abriendo su detalle, verificando que los metadatos coinciden y el estado inicial es el esperado.

**Acceptance Scenarios**:

1. **Given** un manuscrito registrado, **When** su autor accede al detalle, **Then** el sistema muestra los metadatos registrados y el estado del proceso editorial.
2. **Given** un usuario que no es el autor ni tiene rol de coordinador, **When** intenta acceder al detalle del manuscrito, **Then** el sistema deniega el acceso.

---

### Edge Cases

- ¿Qué sucede cuando el autor sube un archivo grande que excede el límite permitido? → El sistema rechaza el archivo por superar el tamaño máximo y no inicia el registro.
- ¿Qué ocurre si el autor abandona el formulario a medio completar? → No se crea ningún registro; los datos no confirmados no persisten.
- **¿Qué ocurre si el PDF contiene metadatos de autoría o afiliación institucional?** → El sistema DEBE sanitizar el PDF (retirar metadatos de autor, firmas de software y afiliación) antes de persistirlo, conforme al principio de evaluación a doble ciego de la Constitución.
- ¿Qué sucede si dos autores envían el mismo manuscrito simultáneamente? → Se crean registros independientes; la detección de duplicados no forma parte de esta feature.
- ¿Qué ocurre si el envío se interrumpe por falla de red? → No se crea registro parcial; el autor puede reintentar.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El sistema DEBE permitir a un autor autenticado registrar un manuscrito proporcionando todos los metadatos obligatorios definidos por el proyecto (REG-04.1).
- **FR-002**: El sistema DEBE exigir obligatoriamente la adjunción de un documento en formato PDF para completar el registro (REG-04.2).
- **FR-003**: El sistema DEBE validar que el archivo adjunto sea efectivamente un PDF (no solo por extensión) y cumpla las restricciones técnicas aplicables: contenido íntegro, no vacío y dentro del tamaño máximo permitido (REG-04.3).
- **FR-004**: El sistema DEBE crear el registro del manuscrito únicamente cuando se cumplen simultáneamente los metadatos obligatorios y la validación del PDF, dando inicio al proceso editorial (REG-04.4).
- **FR-005**: El sistema DEBE responder HTTP `201 Created` ante un registro exitoso.
- **FR-006**: El sistema DEBE rechazar envíos con metadatos incompletos o PDF inválido, informando la causa y sin crear ningún registro.
- **FR-007**: El sistema DEBE sanitizar el PDF almacenado retirando metadatos de autoría, firmas de software de creación y datos de afiliación institucional, en cumplimiento del protocolo de doble ciego.
- **FR-008**: El sistema DEBE asignar a cada manuscrito registrado un estado inicial del proceso editorial y permitir su consulta por el autor.
- **FR-009**: El sistema DEBE permitir únicamente al autor del manuscrito y a los roles autorizados (Coordinador) acceder a sus datos y archivo.
- **FR-010**: El sistema DEBE garantizar que el envío interrumpido no produzca registros parciales.

### Key Entities

- **Manuscrito**: Artículo postulado por un autor; posee metadatos obligatorios (título, resumen, palabras clave, área temática, entre otros definidos por el proyecto), estado del proceso editorial, autor propietario y una o más versiones.
- **Versión de manuscrito**: Entrega específica del documento asociada a un manuscrito; incluye el archivo PDF sanitizado, fecha de envío y número de versión (las iteraciones son inmutables en su versionado).
- **Autor (Docente)**: Usuario UNL que postula manuscritos; propietario de los registros que crea.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: El 100% de los manuscritos registrados poseen la totalidad de metadatos obligatorios y un PDF sanitizado válido.
- **SC-002**: Ningún registro se crea con metadatos incompletos o archivo no-PDF: la tasa de registros inválidos persistidos es 0.
- **SC-003**: El 100% de los envíos exitosos responden HTTP `201 Created` y quedan consultables por su autor.
- **SC-004**: El 100% de los PDF almacenados presentan metadatos de autoría/afiliación retirados (verificable al inspeccionar el archivo).
- **SC-005**: Un autor competente completa el registro de un manuscrito en menos de 10 minutos.
- **SC-006**: El 100% de los envíos rechazados informan la causa específica (campos faltantes o archivo inválido) al autor.

## Assumptions

- Los metadatos obligatorios exactos (título, resumen, palabras clave, área temática, autores co-autores, etc.) se definen según el Proceso Editorial UNL y se concretan en la fase de planificación.
- El límite máximo de tamaño del PDF se fija en planificación con un valor estándar del dominio.
- "Efectivamente PDF" significa validar la firma interna del formato, no solo la extensión del archivo.
- La sanitización de metadatos del PDF aplica a la versión que se almacena y distribuye a revisores (protocolo de doble ciego de la Constitución).
- El autor debe estar autenticado (dependencia de SPEC-001) y poseer rol Docente/Autor.
- La detección de plagio y duplicados queda fuera del alcance de esta feature.
