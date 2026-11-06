# Feature Specification: Flujo Editorial de Manuscritos Científicos

**Feature Branch**: `001-editorial-workflow`

**Created**: 2026-10-20

**Status**: Draft

**Input**: User description: "Flujos funcionales para los actores principales (Autor, Revisor,
Editor, Administrador): autenticación, carga del manuscrito, asignación de revisores,
emisión del veredicto y control de versiones (v1, v2), más auditoría, historial y catálogo
público."

## Clarifications

### Session 2026-10-20

- Q: ¿Qué significa exactamente "publicación" en el sistema y en qué punto del flujo un manuscrito pasa a ser considerado un artículo publicado? → A: "Publicación/artículo" es el mismo manuscrito una vez alcanza el estado Publicado; no existe una entidad separada.
- Q: ¿Cómo se manejan los manuscritos con múltiples autores (coautoría), y quién tiene permiso para editar y entregar versiones? → A: Un Autor principal (responsable) gestiona el manuscrito (editar, entregar versiones, dar de baja); los coautores se registran con orden y datos de contacto pero sin permisos de gestión.
- Q: ¿Cómo se visualizan y quién puede consultar las versiones anteriores de un manuscrito? → A: Se conservan todas las versiones; el Revisor ve solo la versión vigente asignada; Autor, Editor y Administrador ven el historial completo con fecha y número de versión.
- Q: ¿Qué ocurre si dos personas con permiso de gestión editan el mismo manuscrito al mismo tiempo? → A: Bloqueo optimista: se rechaza el guardado si la copia está desactualizada y se pide recargar; solo se guarda el primer cambio válido.
- Q: ¿Qué metadatos son indispensables en el registro de un manuscrito y cuáles quedan para una fase futura? → A: Obligatorios desde el inicio: título, resumen, palabras clave, idioma, área temática/categoría, DOI, ISSN, ORCID de autores y financiamiento, más el PDF; no se difiere ningún metadato obligatorio.

## User Scenarios & Testing *(mandatory)*

Las historias se priorizan por valor de negocio. Cada una es verificable de forma
independiente: implementar solo una entrega un resultado útil a un actor concreto.

### User Story 1 - Autenticación y selección de perfil (Priority: P1)

Un miembro de la comunidad universitaria (Administrador, Editor, Revisor o Autor) ingresa
con sus credenciales institucionales para acceder únicamente a las funciones de su perfil.
Un docente que cumple más de un papel elige con qué rol desea entrar.

**Why this priority**: Toda operación del sistema depende de saber quién es el usuario y qué
rol desempeña; sin autenticación no existe control de acceso ni trazabilidad de autoría.

**Independent Test**: Se verifica en su totalidad autenticando cuentas con distintos perfiles
y comprobando que cada una accede solo a lo que su rol permite, entregando valor inmediato:
la plataforma queda protegida y segmentada por responsabilidades.

**Acceptance Scenarios**:

1. **Given** un usuario con credenciales institucionales válidas y cuenta activa, **When**
   inicia sesión, **Then** el sistema crea su sesión y carga las capacidades de su rol.
2. **Given** credenciales incorrectas o una cuenta inactiva, **When** el usuario intenta
   iniciar sesión, **Then** el sistema rechaza el acceso e informa el motivo sin revelar datos
   sensibles.
3. **Given** un docente habilitado como Autor y Revisor, **When** elige un rol al ingresar,
   **Then** el sistema restringe su experiencia a las funciones de ese rol, pudiendo cambiar
   de perfil en un nuevo inicio de sesión.
4. **Given** intentos de acceso fallidos repetidos, **When** se supera el límite configurado,
   **Then** el sistema bloquea temporalmente los intentos y lo notifica al usuario.

---

### User Story 2 - Registro y versionado del manuscrito por el Autor (Priority: P2)

Un Autor registra un manuscrito con sus metadatos obligatorios y un documento principal en
formato PDF. Puede corregir metadatos mientras el manuscrito está en Borrador o requiere
correcciones, y entregar nuevas versiones corregidas conservando las anteriores.

**Why this priority**: Es la entrada del flujo editorial; sin manuscritos no hay nada que
revisar ni publicar. El versionado garantiza la integridad y trazabilidad documental.

**Independent Test**: Se verifica registrando un manuscrito, observando su estado inicial,
intentando cargar un archivo inválido y luego entregando una segunda versión, comprobando que
la primera permanece intacta.

**Acceptance Scenarios**:

1. **Given** un Autor autenticado con los metadatos obligatorios y un PDF válido, **When**
   registra el manuscrito, **Then** el sistema lo crea en estado Borrador y confirma la
   recepción.
2. **Given** un archivo que no es PDF, un PDF corrupto o un archivo que excede el tamaño
   permitido, **When** el Autor intenta adjuntarlo, **Then** el sistema rechaza la carga e
   indica la causa.
3. **Given** un manuscrito en estado Borrador o "Requiere Correcciones", **When** el Autor
   edita sus metadatos, **Then** el sistema guarda los cambios.
4. **Given** un manuscrito en estado "Requiere Correcciones" con versión v1 existente,
   **When** el Autor entrega el PDF corregido, **Then** el sistema crea la versión v2 y
   conserva v1 sin sobrescribirla.
5. **Given** un manuscrito que no está en "Requiere Correcciones", **When** el Autor intenta
   subir una nueva versión, **Then** el sistema lo impide.
6. **Given** un manuscrito del Autor, **When** solicita darlo de baja, **Then** el sistema
   aplica una baja lógica y deja de mostrarlo como envío activo.
7. **Given** un Autor autenticado, **When** consulta su panel, **Then** el sistema lista
   exclusivamente sus propios manuscritos con su estado y acciones pendientes.

---

### User Story 3 - Asignación de revisores y evaluación a doble ciego (Priority: P2)

Un Editor visualiza los manuscritos recién recibidos, los pone en revisión y asigna uno o más
Revisores. Cada Revisor completa un formulario de evaluación y emite una recomendación, sin
acceder nunca a la identidad del Autor.

**Why this priority**: La evaluación por pares es el núcleo del flujo editorial y su
imparcialidad (doble ciego) es un requisito no negociable de la institución.

**Independent Test**: Se verifica recibiendo un manuscrito, asignando revisores, registrando
una evaluación y confirmando que el Revisor nunca ve datos del Autor y que solo ve sus propias
asignaciones.

**Acceptance Scenarios**:

1. **Given** un manuscrito en estado "Recibido", **When** el Editor lo pone en revisión,
   **Then** el sistema cambia automáticamente su estado a "En Revisión".
2. **Given** un manuscrito "En Revisión", **When** el Editor asigna uno o más Revisores,
   **Then** el sistema registra las asignaciones y notifica a los implicados.
3. **Given** un Revisor con un manuscrito asignado, **When** consulta los datos del
   manuscrito, **Then** el sistema excluye cualquier identificador o nombre del Autor.
4. **Given** un Revisor autenticado, **When** consulta sus tareas, **Then** el sistema muestra
   únicamente sus asignaciones.
5. **Given** un Revisor asignado, **When** completa el formulario de evaluación y emite su
   recomendación, **Then** el sistema registra el dictamen.
6. **Given** un Revisor que ya emitió su evaluación, **When** el Editor intenta asignarle el
   mismo manuscrito de nuevo, **Then** el sistema lo impide.

---

### User Story 4 - Solicitud de correcciones y veredicto editorial (Priority: P2)

Un Editor solicita correcciones al Autor con observaciones, y una vez que existe al menos una
evaluación, emite la decisión final: Aceptado, Rechazado o Requiere Correcciones.

**Why this priority**: Cierra el ciclo editorial y comunica formalmente el resultado al Autor.

**Independent Test**: Se verifica solicitando correcciones sobre un manuscrito evaluado y
emitiendo cada uno de los tres veredictos posibles, comprobando el estado resultante.

**Acceptance Scenarios**:

1. **Given** un manuscrito evaluado, **When** el Editor solicita correcciones con
   observaciones, **Then** el sistema cambia el estado a "Requiere Correcciones" y notifica
   al Autor con el detalle.
2. **Given** un manuscrito con al menos una evaluación registrada, **When** el Editor emite un
   veredicto (Aceptado, Rechazado o Requiere Correcciones), **Then** el sistema actualiza el
   estado definitivo y lo notifica.
3. **Given** un manuscrito sin evaluaciones registradas, **When** el Editor intenta emitir un
   veredicto, **Then** el sistema lo impide.
4. **Given** un manuscrito Aceptado, **When** se publica, **Then** queda disponible en el
   catálogo público.

---

### User Story 5 - Auditoría, historial y catálogo público (Priority: P3)

Los actores autorizados consultan el historial de sus documentos; el Administrador consulta la
bitácora inmutable de acciones críticas; y el público busca artículos aprobados en el catálogo
mediante filtros.

**Why this priority**: Da trazabilidad, transparencia y difusión del conocimiento, pero
depende de que existan los flujos anteriores.

**Independent Test**: Se verifica realizando acciones críticas, comprobando que generan
registros inalterables, y buscando en el catálogo un artículo aprobado con distintos filtros.

**Acceptance Scenarios**:

1. **Given** una acción crítica (inicio de sesión, cambio de estado, asignación o veredicto),
   **When** ocurre, **Then** el sistema registra un evento inmutable con responsable, fecha y
   acción.
2. **Given** un Administrador autenticado, **When** consulta la bitácora, **Then** el sistema
   la muestra ordenada cronológicamente y no permite modificarla ni eliminarla.
3. **Given** un Autor, Revisor o Editor, **When** consulta el historial, **Then** el sistema
   muestra únicamente los documentos a los que su rol le da acceso.
4. **Given** un usuario del catálogo, **When** busca por término o aplica filtros, **Then** el
   sistema devuelve los artículos aprobados coincidentes.

---

### Edge Cases

- ¿Qué ocurre si un Autor intenta subir una nueva versión cuando el estado no es "Requiere
  Correcciones"? El sistema debe impedirlo (escenario 2.5).
- ¿Qué ocurre si se intenta emitir un veredicto sin evaluaciones? El sistema debe impedirlo
  (escenario 4.3).
- ¿Qué ocurre si se intenta modificar o eliminar un registro de auditoría? El sistema debe
  bloquearlo (escenario 5.2).
- ¿Qué ocurre si un manuscrito "Dado de baja" recibe intentos de asignación o evaluación? El
  sistema debe impedir toda transición sobre él.
- ¿Qué ocurre si un docente con doble rol intenta operar simultáneamente como Autor y Revisor?
  El sistema debe resolver permisos por el rol activo sin escalar privilegios.
- ¿Qué ocurre si el catálogo recibe una búsqueda sin resultados? El sistema debe informar
  claramente que no hay coincidencias.
- ¿Qué ocurre si un coautor (no principal) intenta editar el manuscrito, entregar una versión
  o darlo de baja? El sistema debe denegar la acción porque solo el Autor principal gestiona el
  envío.
- ¿Qué ocurre si un Revisor intenta acceder a una versión anterior del manuscrito? El sistema
  debe mostrarle únicamente la versión vigente asignada y denegar el acceso al historial.
- ¿Qué ocurre si dos usuarios guardan cambios sobre el mismo manuscrito a la vez? El sistema
  debe aceptar solo el primer guardado válido y rechazar el desactualizado pidiendo recargar
  (bloqueo optimista).

## Requirements *(mandatory)*

### Functional Requirements

**Autenticación y roles**

- **FR-001**: El sistema DEBE autenticar a los usuarios con credenciales institucionales y
  validar que la cuenta esté activa.
- **FR-002**: El sistema DEBE permitir a un docente que desempeña varios papeles elegir el rol
  con el que ingresa, restringiendo su experiencia a ese perfil.
- **FR-003**: El sistema DEBE limitar los intentos de inicio de sesión fallidos y bloquear
  temporalmente al superar el umbral configurado.
- **FR-004**: El sistema DEBE aplicar control de acceso por rol en cada operación, denegando
  las acciones no autorizadas.
- **FR-004a**: El sistema DEBE aplicar bloqueo optimista en toda edición de manuscrito: cada
  manuscrito lleva un contador de revisión y, si un usuario intenta guardar cambios sobre una
  copia desactualizada, el sistema rechaza el guardado e indica que debe recargar. Solo se
  persiste el primer cambio válido.

**Flujo del Autor**

- **FR-005**: El sistema DEBE permitir al Autor registrar un manuscrito con metadatos
  obligatorios y un documento en formato PDF. Los metadatos obligatorios son: título, resumen,
  palabras clave, idioma, área temática/categoría, DOI, ISSN, financiamiento y ORCID de los
  autores. Ninguno de ellos puede quedar vacío.
- **FR-006**: El sistema DEBE aceptar única y exclusivamente archivos en formato PDF, y
  rechazar archivos de otro formato, corruptos o que excedan el tamaño permitido.
- **FR-007**: El sistema DEBE iniciar todo manuscrito en estado Borrador.
- **FR-008**: El sistema DEBE permitir al Autor editar metadatos únicamente en estados
  Borrador o "Requiere Correcciones".
- **FR-009**: El sistema DEBE permitir al Autor entregar una nueva versión del documento
  únicamente cuando el manuscrito esté en "Requiere Correcciones".
- **FR-010**: El sistema DEBE conservar cada versión entregada de forma inalterable, con un
  identificador único de versión, sin sobrescribir versiones anteriores.
- **FR-010a**: El sistema DEBE permitir al Autor, al Editor y al Administrador consultar el
  historial completo de versiones de un manuscrito (número de versión, fecha y documento). El
  Revisor DEBE poder acceder únicamente a la versión vigente asignada, nunca a versiones
  anteriores.
- **FR-011**: El sistema DEBE permitir al Autor consultar exclusivamente sus propios
  manuscritos y su estado. Solo el Autor principal (responsable del envío) puede editar,
  entregar versiones y dar de baja el manuscrito; los coautores no tienen permisos de gestión.
- **FR-012**: El sistema DEBE permitir al Autor dar de baja un manuscrito mediante eliminación
  lógica, ocultándolo de los envíos activos.

**Flujo del Editor**

- **FR-013**: El sistema DEBE permitir al Editor visualizar los manuscritos nuevos y cambiar
  su estado a "En Revisión".
- **FR-014**: El sistema DEBE permitir al Editor asignar uno o más Revisores a un manuscrito.
- **FR-015**: El sistema DEBE permitir al Editor solicitar correcciones al Autor registrando
  observaciones.
- **FR-016**: El sistema DEBE permitir al Editor emitir el veredicto final (Aceptado,
  Rechazado o Requiere Correcciones) únicamente si existe al menos una evaluación registrada.
- **FR-017**: El sistema DEBE permitir al Editor consultar el historial de revisiones, estados
  y decisiones de los manuscritos que gestiona.

**Flujo del Revisor**

- **FR-018**: El sistema DEBE permitir al Revisor completar un formulario de evaluación con
  observaciones y emitir una recomendación.
- **FR-019**: El sistema DEBE garantizar el anonimato: un Revisor NUNCA debe acceder a los
  campos de identidad del Autor mientras el manuscrito esté en evaluación.
- **FR-020**: El sistema DEBE mostrar al Revisor únicamente las asignaciones que le
  corresponden.

**Auditoría, historial y catálogo**

- **FR-021**: El sistema DEBE generar registros de auditoría inmutables para las acciones
  críticas, incluyendo al menos responsable, fecha y acción.
- **FR-022**: El sistema DEBE permitir al Administrador consultar la bitácora de auditoría
  global ordenada cronológicamente, sin permitir su modificación ni eliminación.
- **FR-023**: El sistema DEBE permitir a cada actor consultar el historial de los documentos a
  los que su rol le da acceso.
- **FR-024**: El sistema DEBE permitir buscar y filtrar artículos aprobados en el catálogo
  público. Un "artículo" o "publicación" es el mismo manuscrito que alcanzó el estado
  Publicado; el sistema NO crea una entidad separada para ello.
- **FR-025**: El sistema DEBE notificar por correo electrónico los eventos clave (asignación,
  solicitud de correcciones, veredicto, cambio de estado).

### Key Entities *(include if feature involves data)*

- **Usuario**: actor del sistema, con identidad institucional, cuenta activa y uno o varios
  roles (Autor, Revisor, Editor, Administrador); un mismo docente puede desempeñar más de uno.
- **Manuscrito**: trabajo científico postulado, con metadatos obligatorios (título, resumen,
  palabras clave, idioma, área temática/categoría, DOI, ISSN, financiamiento y ORCID de los
  autores), estado del ciclo de vida, autor responsable y clasificación temática.
  Es la única entidad del ciclo editorial: al llegar al estado Publicado se denomina
  "publicación" o "artículo", sin crear un registro aparte.
- **Versión de Manuscrito**: entrega inmutable del manuscrito, con número de versión único,
  documento PDF asociado y marca de anonimización. De cada versión se conservan número y fecha;
  la versión vigente es la última entregada.
- **Autoría**: vínculo entre una persona y un manuscrito, con orden de autoría y datos de
  contacto (protegidos del Revisor). Uno de los autores es el Autor principal responsable del
  envío y único con permisos de gestión.
- **Asignación de Revisión**: designación de un Revisor a un manuscrito por parte del Editor,
  con estado de la asignación.
- **Evaluación**: dictamen técnico de un Revisor sobre una asignación, con observaciones y
  recomendación.
- **Veredicto**: resolución editorial final del Editor sobre el manuscrito.
- **Registro de Auditoría**: bitácora inmutable de acciones críticas (responsable, acción,
  entidad afectada, fecha).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Un Autor puede registrar un manuscrito completo (metadatos + PDF) en menos de 5
  minutos.
- **SC-002**: El 100% de los archivos que no sean PDF son rechazados con un mensaje claro del
  motivo.
- **SC-003**: El 0% de las consultas realizadas por un Revisor expone datos de identidad del
  Autor durante la evaluación.
- **SC-004**: El 100% de las acciones críticas queda registrado en la bitácora y ningún
  registro puede ser alterado o eliminado por usuarios ordinarios.
- **SC-005**: El 100% de los intentos de emitir un veredicto sin evaluaciones es bloqueado.
- **SC-006**: El sistema admite 50 usuarios concurrentes con una tasa de éxito de al menos 95%
  y respuestas percibidas como inmediatas (menos de 2 segundos en el 95% de las operaciones).
- **SC-007**: Una búsqueda en el catálogo devuelve resultados coincidentes en el 95% de los
  casos en menos de 2 segundos.
- **SC-008**: Una segunda versión entregada nunca elimina ni altera la primera: el 100% del
  historial de versiones permanece consultable.
- **SC-009**: El 100% de los intentos de un coautor (no principal) por gestionar un manuscrito
  es denegado.
- **SC-010**: El 100% de los accesos de un Revisor a versiones anteriores (no vigentes) es
  denegado, mientras que Autor, Editor y Administrador pueden ver el historial completo.
- **SC-011**: El 100% de las ediciones concurrentes sobre una copia desactualizada es
  rechazado sin pérdida de datos, conservando siempre el primer cambio válido.
- **SC-012**: El 100% de los manuscritos registrados sin alguno de los metadatos obligatorios
  (FR-005) es rechazado con un mensaje que indica el campo faltante.

## Assumptions

- Se reutilizan las credenciales institucionales de la universidad; no se crean cuentas
  locales con contraseñas propias.
- El ciclo de vida del manuscrito tiene los estados: Borrador, Recibido, En Revisión, Requiere
  Correcciones, Aceptado, Rechazado, Publicado y Dado de baja.
- "Publicación", "artículo" y "manuscrito publicado" son sinónimos del mismo manuscrito en
  estado Publicado; no existe una entidad "publicación" independiente.
- La anonimización completa del contenido y metadatos del PDF para el doble ciego se detalla en
  una especificación posterior; aquí se exige que el Revisor no acceda a la identidad del Autor.
- El tamaño máximo permitido del PDF se fijará en una iteración posterior de clarificación.
- Todos los metadatos listados en FR-005 (incluidos DOI, ISSN, financiamiento y ORCID) son
  obligatorios desde el inicio; no se difiere ninguno a fases futuras.
- El catálogo público solo expone artículos en estado Aceptado o Publicado.
- Las notificaciones por correo usan el canal configurado por la institución y no bloquean la
  acción del usuario si el envío falla.
- La eliminación de manuscritos es siempre lógica (baja), nunca física, para preservar la
  trazabilidad.
