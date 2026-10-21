# Feature Specification: Autenticación con Credenciales Institucionales

**Feature Branch**: `feature/SPEC-001-institutional-auth`

**Created**: 2026-10-19

**Status**: Draft

**Input**: User description: "SPEC-001: El sistema debe autenticar únicamente con credenciales institucionales válidas y cuentas activas (RF-01, criterios AUTH-03.1 a AUTH-03.4)."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Inicio de sesión con credenciales institucionales válidas (Priority: P1)

Un usuario docente, revisor o coordinador de la UNL ingresa a la plataforma con sus credenciales institucionales. El sistema las valida contra el repositorio de usuarios institucionales, comprueba que la cuenta esté activa y concede el acceso cargando únicamente los permisos que le corresponden por rol.

**Why this priority**: Sin autenticación no existe acceso a ninguna otra función de la plataforma; es la puerta de entrada de todo el sistema y base del control de roles (RBAC).

**Independent Test**: Puede probarse de forma aislada autenticando con una cuenta institucional activa y verificando que se otorga acceso (HTTP `200 OK`) y se cargan sus permisos.

**Acceptance Scenarios**:

1. **Given** un usuario con credenciales institucionales válidas y cuenta activa, **When** envía sus credenciales para iniciar sesión, **Then** el sistema concede acceso con HTTP `200 OK` y carga sus permisos.
2. **Given** un usuario registrado en el repositorio institucional con cuenta activa, **When** se autentica correctamente, **Then** su sesión queda establecida y puede navegar a las funciones propias de su rol.
3. **Given** un usuario sin sesión iniciada, **When** intenta acceder a un recurso protegido, **Then** el sistema deniega el acceso y solicita autenticación.

---

### User Story 2 - Rechazo de credenciales inválidas o cuentas inactivas (Priority: P1)

Un usuario intenta autenticarse con credenciales incorrectas o pertenecientes a una cuenta inactiva. El sistema rechaza el acceso con el código HTTP apropiado, sin revelar cuál de las dos condiciones falló y sin iniciar sesión alguno.

**Why this priority**: Es la contraparte de seguridad obligatoria de la US1 (criterios AUTH-03.2 a AUTH-03.4); sin ella la autenticación sería insegura. Misma prioridad crítica que la US1.

**Independent Test**: Puede probarse de forma aislada enviando credenciales incorrectas y, por separado, credenciales correctas de una cuenta inactiva, verificando en ambos casos el rechazo.

**Acceptance Scenarios**:

1. **Given** un usuario con credenciales inválidas, **When** intenta iniciar sesión, **Then** el sistema rechaza el acceso con el código HTTP apropiado (HTTP `401 Unauthorized`) y no se establece sesión.
2. **Given** un usuario con credenciales válidas pero cuenta inactiva, **When** intenta iniciar sesión, **Then** el sistema rechaza el acceso con el código HTTP apropiado (HTTP `403 Forbidden`) y no se establece sesión.
3. **Given** un intento de autenticación fallido, **When** el sistema responde, **Then** no revela si el fallo se debió a credenciales inválidas o a cuenta inactiva más allá del código HTTP correspondiente, sin filtrar datos sensibles del usuario.
4. **Given** una cuenta institucional activa que es desactivada, **When** su portador intenta iniciar sesión nuevamente, **Then** el sistema rechaza el acceso.

---

### User Story 3 - Cierre de sesión (Priority: P2)

El usuario autenticado cierra su sesión voluntariamente y el sistema invalida el acceso, de modo que un posterior uso de sus credenciales de sesión no permite continuar navegando.

**Why this priority**: Completa el ciclo de autenticación y protege estaciones de trabajo compartidas; siendo un flujo simple se posterga detrás del login y el rechazo.

**Independent Test**: Puede probarse autenticándose, cerrando sesión y verificando que un recurso protegido vuelve a requerir autenticación.

**Acceptance Scenarios**:

1. **Given** un usuario autenticado, **When** solicita cerrar sesión, **Then** el sistema invalida la sesión y responde con éxito.
2. **Given** un usuario con la sesión cerrada, **When** intenta usar su credencial de sesión anterior, **Then** el sistema rechaza el acceso.

---

### Edge Cases

- ¿Qué sucede cuando un usuario con credenciales válidas pero cuenta inactiva intenta iniciar sesión? → Rechazo con código HTTP apropiado (cubierto en US2).
- ¿Cómo maneja el sistema un bloqueo por intentos fallidos repetidos? → El sistema aplica un bloqueo temporal progresivo tras intentos fallidos consecutivos para mitigar fuerza bruta.
- ¿Qué ocurre si el repositorio de usuarios institucionales no está disponible? → El sistema responde con error del servidor (HTTP `503 Service Unavailable`) sin conceder acceso.
- ¿Qué sucede si un usuario activo intenta iniciar sesión desde dos dispositivos? → Se permiten sesiones independientes por dispositivo; el cierre de una no afecta a la otra.
- ¿Qué ocurre si una sesión permanece inactiva? → La sesión expira tras un período de inactividad y el usuario debe autenticarse de nuevo.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El sistema DEBE autenticar a los usuarios únicamente mediante credenciales institucionales válidas.
- **FR-002**: El sistema DEBE validar las credenciales institucionales contra el repositorio de usuarios institucionales (AUTH-03.1).
- **FR-003**: El sistema DEBE verificar que la cuenta del usuario se encuentre activa antes de conceder el acceso (AUTH-03.2).
- **FR-004**: El sistema DEBE conceder el acceso solo cuando ambas condiciones —credenciales válidas y cuenta activa— se cumplen simultáneamente (AUTH-03.3).
- **FR-005**: El sistema DEBE rechazar el acceso con el código HTTP apropiado cuando las credenciales son inválidas o la cuenta está inactiva (AUTH-03.4), sin iniciar sesión.
- **FR-006**: El sistema DEBE cargar los permisos del usuario autenticado conforme a su rol institucional (Docente/Autor, Coordinador/Editor, Revisor).
- **FR-007**: El sistema DEBE impedir el acceso a cualquier recurso protegido sin una sesión autenticada válida.
- **FR-008**: El sistema DEBE permitir al usuario cerrar sesión, invalidando la credencial de sesión.
- **FR-009**: El sistema DEBE aplicar bloqueo temporal tras intentos fallidos consecutivos de autenticación.
- **FR-010**: El sistema DEBE expirar las sesiones tras un período de inactividad.
- **FR-011**: El sistema DEBE garantizar que los mensajes de error de autenticación no filtren información sensible más allá del código HTTP correspondiente.

### Key Entities

- **Usuario Institucional**: Persona de la comunidad UNL (docente, coordinador o revisor) con credenciales institucionales; posee rol, estado de cuenta (activo/inactivo) y permisos asociados.
- **Sesión**: Estado temporal de acceso de un usuario autenticado; tiene fecha de inicio, expiración por inactividad y puede invalidarse mediante cierre de sesión.
- **Registro de acceso**: Evidencia de intentos de autenticación (exitosos o fallidos) para auditoría de seguridad.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: El 100% de los inicios de sesión con credenciales válidas y cuenta activa resultan en acceso concedido con HTTP `200 OK`.
- **SC-002**: El 100% de los intentos con credenciales inválidas o cuentas inactivas son rechazados; la tasa de accesos no autorizados es 0.
- **SC-003**: Un usuario legítimo completa el inicio de sesión en menos de 30 segundos.
- **SC-004**: El 100% de los recursos protegidos inaccesibles sin sesión devuelven denegación verificable.
- **SC-005**: El 100% de los eventos de autenticación (exitosos y fallidos) quedan registrados para auditoría.

## Assumptions

- "Credenciales institucionales" son las emitidas/gestionadas por la UNL para su comunidad (mismo repositorio de usuarios que emplea la institución); el mecanismo exacto (directorio LDAP/AD, federation SSO u otro) se resuelve en la fase de planificación.
- Los roles del sistema son los definidos por la Constitución: Docente (Autor), Coordinador (Administrador/Editor) y Revisor (Evaluador).
- Solo existen los estados de cuenta relevantes para este alcance: activa e inactiva.
- El repositorio de usuarios institucionales es la fuente de verdad de las credenciales; no se crean cuentas locales alternativas en esta feature.
- Los umbrales de bloqueo por intentos fallidos y de expiración por inactividad se fijan en la fase de planificación con valores estándar del dominio.
