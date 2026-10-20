# Feature Specification: Dominio Editorial y Autenticación por Roles

**Feature Branch**: `001-domain-and-auth`

**Created**: 2026-10-20

**Status**: Draft

**Input**: User description: "Modelo de dominio del flujo editorial (manuscritos, versiones, asignación de revisores, evaluaciones, veredicto y auditoría) más autenticación de usuarios con control de acceso basado en roles, como base del primer incremento funcional."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Persistencia del modelo de dominio editorial (Priority: P1)

Un desarrollador del equipo necesita que las entidades del flujo editorial (manuscritos, versiones, autores, asignaciones, evaluaciones, veredictos y bitácora de auditoría) existan como esquema de base de datos, con identificadores únicos, campos de auditoría e integridad referencial protegida, para poder construir sobre ellas la API y las vistas.

**Why this priority**: Sin el esquema de datos no puede implementarse ninguna funcionalidad del flujo editorial. Es el cimiento del MVP y define el contrato de datos del sistema.

**Independent Test**: Se puede verificar aplicando las migraciones sobre una base de datos limpia y comprobando que todas las tablas se crean con sus restricciones e índices, y que las relaciones de protección impiden borrados accidentales en cascada.

**Acceptance Scenarios**:

1. **Given** una base de datos vacía, **When** se aplican las migraciones, **Then** se crean las tablas de usuarios, manuscritos, versiones, asignaciones, evaluaciones, veredictos y auditoría con sus claves e índices.
2. **Given** un manuscrito con versiones asociadas, **When** se intenta eliminar físicamente el manuscrito, **Then** el sistema lo impide por la restricción de integridad (protección referencial).
3. **Given** cualquier entidad de negocio creada, **When** se persiste, **Then** registra automáticamente fecha de creación y fecha de última actualización.

---

### User Story 2 - Autenticación con control de acceso por roles (Priority: P2)

Un usuario del sistema (Administrador, Editor, Revisor o Autor) desea iniciar sesión con sus credenciales institucionales y que el sistema le conceda únicamente las capacidades de su rol, de modo que nadie acceda a funciones que no le corresponden.

**Why this priority**: La autenticación y el RBAC son transversales: toda operación posterior (subir manuscrito, asignar revisor, emitir veredicto) depende de conocer quién es el usuario y qué rol tiene.

**Independent Test**: Se puede probar creando usuarios con distintos roles, autenticándolos y comprobando que las operaciones permitidas y denegadas devuelven los códigos de estado esperados (acceso concedido vs. `403 Forbidden`).

**Acceptance Scenarios**:

1. **Given** un usuario con credenciales válidas y cuenta activa, **When** inicia sesión, **Then** el sistema valida la información, crea la sesión y carga los permisos de su rol.
2. **Given** credenciales incorrectas o una cuenta inactiva, **When** el usuario intenta iniciar sesión, **Then** el sistema rechaza el acceso y no crea sesión.
3. **Given** un usuario autenticado cuyo rol no autoriza una operación protegida, **When** la ejecuta, **Then** el sistema la deniega con `403 Forbidden`.
4. **Given** un docente que puede desempeñar más de un perfil, **When** selecciona el rol activo, **Then** el sistema habilita las capacidades de dicho perfil.

---

### User Story 3 - Confidencialidad del doble ciego a nivel de datos (Priority: P2)

Un Revisor desea que la información que consulta sobre un manuscrito asignado nunca exponga la identidad del Autor, de modo que la evaluación por pares permanezca imparcial.

**Why this priority**: El anonimato es un principio no negociable de la institución; debe quedar garantizado desde el diseño de datos, no solo en la presentación.

**Independent Test**: Se puede probar solicitando los datos de un manuscrito en el contexto del Revisor y verificando que la representación de datos para revisión excluye cualquier identificador o nombre del Autor.

**Acceptance Scenarios**:

1. **Given** un manuscrito asignado a un Revisor, **When** el Revisor obtiene la representación de datos para revisión, **Then** dicha representación no incluye nombre ni identificador del Autor.
2. **Given** una acción crítica sobre un manuscrito (cambio de estado, asignación o veredicto), **When** ocurre, **Then** el sistema genera un registro de auditoría inalterable.

---

### Edge Cases

- ¿Qué ocurre si se intenta subir una nueva versión de un manuscrito cuando su estado no es "Requiere Correcciones"? El sistema debe rechazar la operación.
- ¿Qué ocurre si se intenta emitir un veredicto sin evaluaciones registradas? El sistema debe impedirlo.
- ¿Qué ocurre si un usuario tiene más de un rol? El sistema debe resolver permisos por la unión de capacidades de sus roles activos, sin escalar privilegios indebidos.
- ¿Qué ocurre si se intenta modificar o eliminar un registro de auditoría? El sistema debe bloquearlo.
- ¿Qué ocurre si el archivo adjunto no es PDF? El sistema debe rechazarlo antes de persistir el manuscrito (cubierto por HU-012 / RF-14).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El sistema DEBE permitir la autenticación de usuarios mediante credenciales institucionales (RF-01).
- **FR-002**: El sistema DEBE modelar usuarios con al menos los roles Autor, Revisor, Editor y Administrador, y permitir que un docente desempeñe más de un perfil (RF-12, RF-16).
- **FR-003**: El sistema DEBE restringir cada operación según el rol del usuario autenticado, denegando con `403 Forbidden` cuando no corresponda (RF-16).
- **FR-004**: El sistema DEBE representar el manuscrito y sus metadatos obligatorios, con un ciclo de vida de estados explícito (RF-02, RF-21, RF-22).
- **FR-005**: El sistema DEBE versionar los manuscritos conservando cada versión de forma inalterable e impidiendo la sobrescritura (RF-06, RNF-05).
- **FR-006**: El sistema DEBE permitir la asignación de uno o más revisores a un manuscrito, cambiando su estado a "En Revisión" (RF-03, RF-17).
- **FR-007**: El sistema DEBE registrar evaluaciones con observaciones y recomendación por parte del revisor (RF-04, RF-18).
- **FR-008**: El sistema DEBE permitir el cierre del proceso con el registro del veredicto final: Aceptado, Rechazado o Requiere Correcciones (RF-07, RF-19).
- **FR-009**: El sistema DEBE generar automáticamente registros de auditoría inalterables para acciones críticas (RF-08, RNF-08).
- **FR-010**: El sistema DEBE garantizar, a nivel de representación de datos, que el revisor nunca reciba la identidad del autor (RNF-07).
- **FR-011**: Toda entidad de negocio DEBE registrar fecha de creación y de última actualización, y usar identificadores únicos (Constitución: Diseño de Modelos).
- **FR-012**: El sistema DEBE impedir la eliminación física en cascada de entidades críticas mediante relaciones de protección o anulación (Constitución: Integridad Referencial).

### Key Entities *(include if feature involves data)*

- **User**: Actor del sistema con identidad institucional y uno o más roles (Autor, Revisor, Editor, Administrador); atributos de cuenta (activo, credenciales) y utilidades de autorización.
- **Manuscript**: Trabajo científico postulado; metadatos obligatorios (título, resumen, palabras clave, idioma), estado del ciclo de vida, autor responsable, categoría; se relaciona con sus versiones y con sus asignaciones de revisión.
- **ManuscriptVersion**: Instantánea inmutable de un manuscrito entregada por el autor; número o identificador único de versión, archivo PDF asociado y marca de sanitización de metadatos.
- **Author**: Perfil de autoría asociado a un manuscrito (puede haber varios autores por trabajo), con orden de autoría.
- **Category / ResearchArea**: Categoría temática o área de conocimiento para clasificación y filtrado del catálogo.
- **ReviewAssignment**: Vinculación entre un manuscrito y un revisor designado por el editor, con estado de la asignación.
- **Evaluation**: Dictamen técnico de un revisor sobre una asignación: observaciones, recomendación y fechas.
- **ReviewVerdict**: Resolución editorial final del editor sobre el manuscrito (Aceptado / Rechazado / Requiere Correcciones), con observaciones.
- **AuditLog**: Bitácora inmutable de acciones críticas: actor, entidad afectada, acción, marcas de tiempo y datos relevantes; protegida contra modificación y eliminación.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: El 100% de las entidades del flujo editorial descritas existen como tablas con identificadores únicos, campos de auditoría e índices en los campos de filtrado frecuentes.
- **SC-002**: El 100% de las operaciones protegidas por rol devuelven el código de estado correcto (concedido o `403 Forbidden`) en las pruebas automatizadas.
- **SC-003**: Ninguna representación de datos entregada al rol Revisor contiene la identidad del Autor (0 fugas detectadas en pruebas).
- **SC-004**: El 100% de las acciones críticas definidas genera un registro de auditoría que no puede modificarse ni eliminarse.
- **SC-005**: Las migraciones se aplican limpiamente desde cero sin errores ni advertencias.

## Assumptions

- Se reutiliza el sistema de autenticación nativo de Django como base, extendido con el modelo de usuario propio del proyecto.
- Los estados del manuscrito del ciclo de vida son: Borrador, Recibido, En Revisión, Requiere Correcciones, Aceptado, Rechazado, Publicado y Dado de baja.
- La sanitización de metadatos del PDF se especificará e implementará en una feature posterior; en esta feature solo se persiste la marca correspondiente en la versión.
- El almacenamiento de archivos PDF usa volúmenes locales protegidos (`media/`) en esta iteración; la evaluación de almacenamiento en la nube queda pendiente (dossier §10).
- El límite máximo de tamaño de PDF se fijará en una iteración posterior (RF-14/HU-012); esta feature no lo implementa.
- La API REST (DRF/JWT) se especificará en una feature posterior; aquí se entregan modelos, RBAC y las utilidades de dominio.
