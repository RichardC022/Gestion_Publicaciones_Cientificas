# Especificación Funcional — Sistema de Gestión de Publicaciones Científicas

**Archivo:** `specify.md`  
**Metodología:** SpecKit — Specification-Driven Development  
**Versión:** 1.0  
**Fecha:** 22 de octubre de 2026  
**Estado:** Listo para planificación  
**Autor:** Analista de Sistemas Ágil  
**Fuente de verdad:** Dossier de requisitos del sistema (RF-01 a RF-22) y reglas de negocio vigentes

> **Principio rector:** este documento describe qué necesita el negocio y cómo se verificará. No prescribe tecnologías, productos, arquitecturas ni mecanismos de implementación.

---

## 1. Control del documento

| Elemento | Descripción |
|---|---|
| Nombre del sistema | Sistema de Gestión de Publicaciones Científicas |
| Ámbito | Flujo editorial completo de manuscritos académicos |
| Cobertura funcional | 22 requisitos funcionales (RF-01 a RF-22) |
| Módulos incluidos | Autenticación y panel unificado; Panel del Autor; Panel del Editor; Panel del Revisor; Catálogo y Auditoría; Trazabilidad e Historial; Notificaciones transversales |
| Fuera de alcance | Ranking automatizado de revisores (Fase 2), evaluaciones paralelas con más de un revisor y procesos editoriales no descritos en este documento |
| Nivel de detalle | Especificación funcional verificable, previa a la planificación técnica |

### 1.1 Decisiones vigentes que ajustan el dossier

Estas decisiones prevalecen sobre cualquier redacción anterior del dossier y deben considerarse al leer las historias:

| Código | Decisión vigente | Impacto |
|---|---|---|
| D-01 | El sistema **no solicita elegir un rol inicial**. El panel unificado muestra simultáneamente todos los apartados habilitados para la persona. | Ajusta la lectura de RF-12: la necesidad de multirrol se satisface con visibilidad simultánea, no con selección de perfil. |
| D-02 | Cada manuscrito tiene **exactamente un Revisor activo** a la vez. No se permiten evaluaciones paralelas de dos o más revisores. | Ajusta la lectura de RF-03: la asignación es única; para cambiar de revisor debe revocarse la asignación vigente. |
| D-03 | El catálogo de artículos aceptados es **público** y no exige inicio de sesión. | Ajusta la lectura de RF-13: cualquier persona puede buscar y consultar los artículos aceptados. |
| D-04 | Si el Revisor no evalúa al cumplirse **20 días exactos**, el Editor puede revocar la asignación y reasignar el manuscrito. | Incorpora una regla de control del plazo no detallada en el dossier original. |
| D-05 | Toda iteración conserva un registro inmutable con el **PDF exacto** y los **metadatos tal como se enviaron** en esa ronda. | Amplía el alcance de RF-06, RF-10 y RF-21 con trazabilidad documental completa. |
| D-06 | El contador de **rondas de corrección** es visible para Autor, Revisor y Editor. | Se separa del contador de versiones para evitar ambigüedad. |

---

## 2. Propósito, problema y valor

### 2.1 Problema

La gestión de manuscritos científicos suele realizarse mediante comunicaciones dispersas. Esa práctica produce pérdida de versiones, dificultad para conocer el estado real de cada envío, vulneración del anonimato en la evaluación por pares y ausencia de evidencia verificable sobre las decisiones editoriales.

### 2.2 Propuesta de valor

Centralizar el ciclo editorial en un flujo único, trazable y confidencial, donde:

- El Autor registra, corrige y consulta sus manuscritos sin perder ninguna versión.
- El Editor coordina el proceso con un único Revisor activo por manuscrito y controla el plazo de evaluación.
- El Revisor evalúa con imparcialidad, sin conocer la identidad del Autor.
- El Administrador dispone de evidencia inmutable de las acciones críticas.
- El público consulta únicamente los artículos aceptados.
- Cada ronda de corrección conserva el PDF y los metadatos exactos que se enviaron.

### 2.3 Objetivos funcionales

1. Garantizar que cada persona acceda solo a las funciones y documentos que le corresponden.
2. Permitir que una persona con varios perfiles trabaje sin elegir un rol inicial.
3. Asegurar que todo manuscrito tenga un flujo de estados claro y verificable.
4. Proteger la identidad del Autor y del Revisor durante la evaluación.
5. Conservar de forma inmutable todas las versiones, metadatos y decisiones.
6. Controlar el plazo de evaluación de 20 días sin revocaciones automáticas.
7. Publicar en el catálogo únicamente artículos aceptados y vigentes.
8. Proporcionar al Administrador un registro de auditoría completo e inalterable.

---

## 3. Alcance

### 3.1 Incluido

- Inicio de sesión con credenciales institucionales.
- Panel unificado para personas con uno o varios perfiles.
- Registro, consulta, edición, baja lógica y versionado de manuscritos.
- Validación estricta de archivos PDF.
- Coordinación editorial: recepción, paso a revisión, asignación única de Revisor, revocación por plazo y veredicto.
- Evaluación doble ciego con formulario estructurado.
- Catálogo público de artículos aceptados.
- Auditoría inmutable de acciones críticas.
- Historial inmutable de iteraciones con PDF y metadatos exactos.
- Contador visible de rondas de corrección.
- Notificaciones institucionales de eventos clave.

### 3.2 Excluido de esta versión

- Ranking automatizado de revisores y cualquier penalización automática por incumplimiento del plazo.
- Evaluación simultánea por más de un Revisor.
- Selección inicial de rol o conmutador de rol dentro de la sesión.
- Acceso público a manuscritos no aceptados, a evaluaciones o a la auditoría.
- Edición o eliminación de versiones, del historial o de la auditoría.
- Borrado físico de manuscritos.
- Integraciones con índices, repositorios externos, servicios de similitud o pagos.
- Gestión avanzada de coautoría, invitaciones o firma de autoría.
- Restauración de manuscritos dados de baja.
- Procesos formales de retractación, apelación o sanción distintos de la baja lógica.

---

## 4. Actores

| Actor | Descripción | Necesidad principal |
|---|---|---|
| **Autor** | Docente o estudiante de la institución que registra manuscritos, adjunta el PDF, corrige y consulta el estado de sus envíos. | Gestionar sus manuscritos y conocer qué acción le corresponde. |
| **Revisor** | Docente autorizado con experiencia en un área, que evalúa los manuscritos asignados sin conocer la identidad del Autor. | Emitir una evaluación imparcial dentro del plazo. |
| **Editor** | Responsable de coordinar el flujo: recibir manuscritos, pasarlos a revisión, asignar al Revisor, controlar el plazo y registrar el veredicto. | Conducir el proceso editorial con trazabilidad y sin bloqueos. |
| **Administrador** | Responsable de consultar la auditoría y velar por la integridad del proceso. | Disponer de evidencia inmutable de las acciones críticas. |
| **Público** | Cualquier persona que consulta el catálogo de artículos aceptados. | Buscar y leer publicaciones aprobadas sin iniciar sesión. |
| **Persona multirrol** | Docente que puede ser Autor y Revisor al mismo tiempo, o que además tiene funciones de Editor. | Ver todos sus apartados a la vez, sin elegir un rol inicial. |

**Regla de identidad:** una misma persona puede acumular varios roles. Los permisos son aditivos, pero cada acción sigue sujeta a las reglas de acceso por documento y a la separación de funciones.

---

## 5. Glosario

| Término | Definición |
|---|---|
| **Manuscrito** | Documento académico registrado por un Autor, con metadatos, estado editorial y una o varias versiones. |
| **Versión** | Archivo PDF concreto asociado a un manuscrito. Se identifica como v1, v2, v3 y siguientes. Es inmutable. |
| **Iteración** | Envío formal de una versión, junto con los metadatos vigentes en ese momento. |
| **Ronda de corrección** | Ciclo abierto cuando el Editor registra el veredicto "Requiere Correcciones". La primera ronda es la 1; el envío inicial corresponde a la ronda 0. |
| **Revisor activo** | Revisor cuya asignación está vigente para un manuscrito y una versión determinados. Solo puede haber uno por manuscrito. |
| **Plazo de evaluación** | Periodo de 20 días calendario contados desde el instante exacto de la asignación del Revisor. |
| **Doble ciego** | Regla por la cual el Revisor no conoce la identidad del Autor y el Autor no conoce la identidad del Revisor. |
| **Veredicto** | Decisión editorial final: Aceptado, Rechazado o Requiere Correcciones. |
| **Baja lógica** | Marca que retira un manuscrito de los listados activos y del catálogo, sin eliminar su historial ni sus evidencias. |
| **Historial** | Registro cronológico e inmutable de las iteraciones, estados, asignaciones, evaluaciones y decisiones de un manuscrito. |
| **Auditoría** | Registro global e inmutable de acciones críticas, consultable únicamente por el Administrador. |
| **Catálogo** | Consulta pública de artículos en estado Aceptado y no dados de baja. |
| **Metadatos** | Información descriptiva del manuscrito: título, resumen, palabras clave, área, idioma, autores, filiaciones y contacto del autor responsable. |
| **PDF exacto** | Copia íntegra del archivo recibido en una iteración, conservada sin sobrescritura y con un sello que permite verificar su integridad. |
| **Sello de integridad** | Elemento verificable que permite comprobar que el PDF conservado no ha sido alterado. |
| **Estado** | Situación editorial actual del manuscrito dentro del flujo permitido. |

---

## 6. Reglas de negocio

| Código | Regla |
|---|---|
| **RN-01** | El acceso requiere credenciales institucionales válidas y una cuenta activa. No existe autorregistro. |
| **RN-02** | Tras el inicio de sesión, el sistema muestra un panel unificado. **No se solicita elegir un rol inicial.** Si la persona es Autor y Revisor, ambos apartados se muestran simultáneamente y con separación visual clara. |
| **RN-03** | Cada acción se autoriza por rol y por relación con el documento. Un rol no concede acceso a todos los documentos. |
| **RN-04** | Cada manuscrito tiene **exactamente un Revisor activo** a la vez. Para asignar a otra persona, primero debe revocarse la asignación vigente. |
| **RN-05** | El plazo de evaluación es de **20 días calendario exactos**, contados desde el instante de la asignación. Al cumplirse el plazo sin evaluación final, el sistema marca la asignación como vencida y habilita al Editor para revocar y reasignar. **No existe revocación automática.** |
| **RN-06** | El doble ciego es bidireccional: el Revisor no ve la identidad ni los metadatos personales del Autor; el Autor no ve la identidad del Revisor. El Editor y el Administrador autorizado sí pueden conocer ambas identidades. |
| **RN-07** | Solo se aceptan archivos cuyo contenido sea un PDF válido, legible, no dañado, no protegido con contraseña, sin contenido activo no permitido y dentro del tamaño máximo institucional. La extensión del nombre no es suficiente para aceptar el archivo. |
| **RN-08** | El Autor solo puede editar metadatos cuando el manuscrito está en **Borrador** o **Requiere Correcciones**. En cualquier otro estado los metadatos son de solo lectura. |
| **RN-09** | El Autor solo puede enviar una nueva versión cuando el manuscrito está en **Requiere Correcciones**. Cada envío crea la versión consecutiva y conserva las anteriores. |
| **RN-10** | Las versiones y el historial son inmutables. Cada iteración conserva el PDF exacto y una copia de los metadatos tal como se enviaron. No se sobrescribe ni se elimina ningún registro. |
| **RN-11** | La eliminación de un manuscrito es siempre **lógica**. El registro desaparece de los listados activos y del catálogo, pero conserva historial, versiones y auditoría. |
| **RN-12** | El veredicto se registra después de una evaluación final del Revisor asignado. "Requiere Correcciones" exige observaciones; "Rechazado" exige justificación. Un veredicto registrado no se sobrescribe. |
| **RN-13** | Las acciones críticas generan un registro de auditoría inmutable. Si la auditoría no puede registrarse, la acción crítica no se completa. Ningún rol puede modificar o eliminar la auditoría. |
| **RN-14** | El catálogo es público y muestra únicamente manuscritos en estado Aceptado y no dados de baja. No expone evaluaciones, identidades de revisores, historial ni información interna. |
| **RN-15** | El contador de rondas de corrección es visible. El envío inicial es la ronda 0; cada veredicto "Requiere Correcciones" abre la siguiente ronda. El contador de versiones es independiente. |
| **RN-16** | Los eventos clave generan notificaciones por el canal institucional y en el panel de la persona. Las notificaciones respetan el doble ciego. Un fallo de notificación no revierte la acción, pero queda registrado y se reintenta. |
| **RN-17** | Rige la separación de funciones: nadie evalúa su propio manuscrito, nadie decide sobre un manuscrito del que es autor o coautor y nadie altera la auditoría que lo involucra. |
| **RN-18** | Solo se permiten las transiciones de estado definidas en este documento. Toda transición no permitida se bloquea y se registra. |
| **RN-19** | Los plazos y registros temporales se expresan en la zona horaria institucional. Los 20 días son calendario continuo. |
| **RN-20** | Se aplica minimización de datos: cada actor ve solo la información necesaria para su función. La auditoría no conserva el contenido del manuscrito ni datos personales innecesarios. |

## 7. Ciclo de vida, estados y versionado

### 7.1 Estados editoriales

| Estado | Significado | Quién lo activa | Acciones permitidas |
|---|---|---|---|
| **Borrador** | Manuscrito en preparación. | Autor | Editar metadatos, cargar PDF, enviar a revisión, dar de baja lógica. |
| **Enviado** | Manuscrito pendiente de revisión inicial del Editor. | Autor al enviar | Consultar; el Editor puede pasarlo a En Revisión; el Autor puede dar de baja lógica. No se editan metadatos ni se cargan versiones. |
| **En Revisión** | Manuscrito con un Revisor activo o pendiente de asignación. | Editor | Asignar un Revisor, revocar y reasignar, evaluar (Revisor), registrar veredicto (Editor). El Autor solo consulta. |
| **Requiere Correcciones** | El Editor solicitó ajustes. | Editor | El Autor edita metadatos, envía nueva versión o da de baja lógica. El Revisor no evalúa hasta el nuevo envío. |
| **Aceptado** | Veredicto favorable. | Editor | Visible en el catálogo. Sin edición ni nuevas versiones. El Autor puede dar de baja lógica, lo que retira el artículo del catálogo. |
| **Rechazado** | Veredicto desfavorable. | Editor | Sin edición ni nuevas versiones. No aparece en el catálogo. El Autor puede dar de baja lógica para archivarlo. |

**Baja lógica:** no es un estado editorial. Es una marca que puede aplicarse sobre cualquier estado y retira el manuscrito de los listados activos y del catálogo, conservando todo su historial.

### 7.2 Transiciones permitidas

| Desde | Hacia | Actor | Condición |
|---|---|---|---|
| Borrador | Enviado | Autor | Metadatos obligatorios completos y PDF válido. |
| Enviado | En Revisión | Editor | Revisión inicial del envío. Puede asignar al Revisor en la misma acción o dejarlo pendiente de asignación. |
| En Revisión | En Revisión | Editor | Revocación y reasignación por vencimiento de 20 días, conflicto de interés o error de asignación. Solo puede quedar un Revisor activo. |
| En Revisión | Requiere Correcciones | Editor | Evaluación final registrada y observaciones obligatorias. |
| En Revisión | Aceptado | Editor | Evaluación final registrada. |
| En Revisión | Rechazado | Editor | Evaluación final registrada y justificación obligatoria. |
| Requiere Correcciones | Enviado | Autor | Nueva versión válida y metadatos actualizados. Abre la respuesta a la ronda vigente. |
| Cualquier estado | Dado de baja | Autor | Confirmación y baja lógica. No se borra físicamente. |

**Transiciones prohibidas:** Borrador a En Revisión, Enviado a Aceptado o Rechazado, Requiere Correcciones a Aceptado o Rechazado sin nuevo envío y evaluación, y cualquier cambio desde Aceptado o Rechazado hacia la edición.

### 7.3 Modelo de versiones y rondas

1. El primer envío formal crea la **versión v1** y la **ronda 0**.
2. Cada veredicto "Requiere Correcciones" abre una nueva ronda: 1, 2, 3 y siguientes.
3. La respuesta del Autor a esa ronda se registra como la versión consecutiva: v2, v3 y siguientes.
4. Una edición de metadatos no crea versión ni ronda. Solo el envío formal de un PDF crea una iteración.
5. Si el Autor edita metadatos en "Requiere Correcciones" y luego envía una nueva versión, el nuevo registro conserva los metadatos actualizados; el registro anterior no cambia.
6. La reasignación de Revisor no altera la ronda ni la versión. El nuevo Revisor recibe un plazo propio de 20 días.
7. Un manuscrito puede tener más versiones que rondas si el Autor abandona una corrección; el historial conserva ambos datos por separado.
8. Ejemplo: v1/ronda 0 → correcciones → v2/ronda 1 → correcciones → v3/ronda 2 → aceptado.

### 7.4 Historial frente a auditoría

| Aspecto | Historial | Auditoría |
|---|---|---|
| Alcance | Un manuscrito concreto. | Todas las acciones críticas del sistema. |
| Contenido | Versiones, PDF exacto, metadatos, estados, asignaciones, evaluaciones y veredictos. | Actor, rol, fecha, acción, entidad afectada, resultado y motivo cuando corresponda. |
| Quién consulta | Autor sobre lo propio; Revisor sobre lo asignado; Editor sobre su ámbito. | Únicamente el Administrador. |
| Inmutabilidad | No se edita ni se elimina; solo se agregan eventos. | No se edita ni se elimina; solo se agregan eventos. |
| Contenido del manuscrito | Conserva el PDF y los metadatos de cada iteración. | No conserva el contenido del manuscrito. |

---

## 8. Capacidades por rol

| Capacidad | Autor | Revisor | Editor | Administrador | Público |
|---|---|---|---|---|---|
| Iniciar sesión institucional | Sí | Sí | Sí | Sí | No |
| Ver panel unificado | Sí | Sí | Sí | Sí | No |
| Registrar manuscrito | Sí | No | No | No | No |
| Consultar manuscritos propios | Solo propios | No | No | No | No |
| Editar metadatos | Solo propios y en estados permitidos | No | No | No | No |
| Dar de baja lógica | Solo propios | No | No | No | No |
| Enviar nueva versión | Solo propios y en Requiere Correcciones | No | No | No | No |
| Ver manuscritos nuevos | No | No | Sí | No | No |
| Pasar a En Revisión | No | No | Sí | No | No |
| Asignar, revocar o reasignar Revisor | No | No | Sí | No | No |
| Evaluar manuscrito asignado | No | Solo asignados | No | No | No |
| Consultar evaluaciones propias | No | Solo propias | No | No | No |
| Registrar veredicto | No | No | Sí | No | No |
| Consultar historial | Solo propios | Solo versión asignada y sin identidad del Autor | Solo su ámbito | No | No |
| Consultar auditoría | No | No | No | Sí | No |
| Buscar y consultar catálogo | Sí | Sí | Sí | Sí | Sí |
| Recibir notificaciones | Sí | Sí | Sí | Sí | No |

**Nota:** una persona con varios roles suma capacidades, pero no puede usarlas para saltarse la separación de funciones ni el acceso por documento.

---

## 9. Historias de usuario

### 9.1 Resumen de historias

| ID | Historia | Prioridad | RF principal |
|---|---|---|---|
| HU-01 | Inicio de sesión con credenciales institucionales | P1 | RF-01 |
| HU-02 | Panel unificado sin selección previa de rol | P1 | RF-12 |
| HU-03 | Control de acceso por rol y por objeto | P1 | RF-16 |
| HU-04 | Registrar manuscrito con metadatos y PDF | P1 | RF-02 |
| HU-05 | Validar formato y condiciones del PDF | P1 | RF-14 |
| HU-06 | Consultar estado y tareas pendientes | P1 | RF-05 |
| HU-07 | Editar metadatos solo en Borrador o Requiere Correcciones | P2 | RF-21 |
| HU-08 | Dar de baja lógica un manuscrito | P2 | RF-22 |
| HU-09 | Enviar nueva versión en Requiere Correcciones | P2 | RF-06 |
| HU-10 | Visualizar nuevos envíos y pasar a En Revisión | P1 | RF-17 |
| HU-11 | Asignar exactamente un Revisor experto | P1 | RF-03 |
| HU-12 | Revocar y reasignar por inactividad de 20 días | P2 | RF-03 |
| HU-13 | Registrar veredicto final y solicitar correcciones | P1 | RF-07, RF-15, RF-19 |
| HU-14 | Consultar asignaciones pendientes y plazos | P1 | RF-04, RF-18 |
| HU-15 | Completar formulario de evaluación estructurado | P1 | RF-04, RF-18 |
| HU-16 | Evaluar bajo doble ciego | P1 | RF-04, RF-18 |
| HU-17 | Consultar historial de evaluaciones propias | P2 | RF-09 |
| HU-18 | Buscar y filtrar artículos aceptados en el catálogo público | P2 | RF-13 |
| HU-19 | Consultar ficha pública de un artículo aceptado | P3 | RF-13 |
| HU-20 | Registrar auditoría inmutable de acciones críticas | P1 | RF-08 |
| HU-21 | Consultar el registro de auditoría global | P2 | RF-11 |
| HU-22 | Visualizar el contador de rondas de corrección | P2 | RF-05, RF-06, RF-10 |
| HU-23 | Consultar el historial inmutable de iteraciones | P2 | RF-10 |
| HU-24 | Recibir notificaciones de eventos clave | P2 | RF-20 |

---

### Módulo 1: Autenticación y Panel Unificado (Dashboard)

#### HU-01 — Inicio de sesión con credenciales institucionales

**Prioridad:** P1  
**Trazabilidad:** RF-01, RF-16; RN-01, RN-03, RN-13, RN-19.

**Como** usuario institucional (Autor, Revisor, Editor o Administrador), **quiero** iniciar sesión con mis credenciales institucionales, **para** acceder de forma segura a las funciones que me corresponden.

**Criterios de aceptación**

1. **CA-HU-01-01 — Acceso exitoso:** Dado que la persona ingresa credenciales institucionales válidas y su cuenta está activa, cuando confirma el inicio de sesión, entonces el sistema crea una sesión autenticada y la dirige a su panel unificado, sin solicitar la elección de un rol.
2. **CA-HU-01-02 — Credenciales inválidas (error):** Dado que la persona ingresa credenciales incorrectas, cuando intenta acceder, entonces el sistema deniega el acceso con un mensaje genérico que no revela si la cuenta existe y registra el intento fallido.
3. **CA-HU-01-03 — Cuenta inactiva o suspendida (error):** Dado que la cuenta está inactiva o suspendida, cuando la persona intenta acceder con credenciales correctas, entonces el sistema deniega el acceso con el mismo mensaje genérico y registra el evento.
4. **CA-HU-01-04 — Límite de intentos (caso límite):** Dado que se alcanza el límite institucional de intentos fallidos (por defecto, cinco intentos en quince minutos), cuando la persona intenta un nuevo acceso, entonces el sistema bloquea temporalmente el intento durante el periodo definido, informa el tiempo de espera y registra el bloqueo.
5. **CA-HU-01-05 — Cierre de sesión (éxito):** Dado que la persona tiene una sesión activa, cuando selecciona cerrar sesión, entonces la sesión termina y cualquier acceso posterior exige autenticarse de nuevo.
6. **CA-HU-01-06 — Sesión expirada (caso límite):** Dado que la sesión supera el tiempo de inactividad institucional, cuando la persona intenta realizar una acción, entonces el sistema cierra la sesión, solicita autenticación y no muestra datos protegidos.
7. **CA-HU-01-07 — Registro de auditoría (éxito):** Dado un intento de acceso exitoso o fallido, cuando el sistema lo procesa, entonces registra fecha, identificador de la persona, resultado y motivo del rechazo cuando corresponda, sin conservar la contraseña.
8. **CA-HU-01-08 — Acceso ya autenticado (caso límite):** Dado que la persona ya tiene una sesión activa, cuando vuelve a solicitar el inicio de sesión, entonces el sistema la dirige a su panel sin crear una sesión duplicada.

---

#### HU-02 — Panel unificado sin selección previa de rol

**Prioridad:** P1  
**Trazabilidad:** RF-12, RF-16; RN-02, RN-17, RN-20.

**Como** docente que puede ser Autor y Revisor, **quiero** que al iniciar sesión se muestre un panel unificado con todos mis apartados, **para** trabajar sin que el sistema me obligue a elegir un rol inicial ni perder funciones.

**Criterios de aceptación**

1. **CA-HU-02-01 — Acceso directo al panel (éxito):** Dado que la persona inicia sesión correctamente, cuando el sistema la recibe, entonces muestra directamente el panel unificado, sin una pantalla intermedia de selección de rol.
2. **CA-HU-02-02 — Multirrol simultáneo (éxito):** Dado que la persona tiene los perfiles de Autor y Revisor, cuando se carga el panel, entonces ambos apartados se muestran simultáneamente, claramente diferenciados, cada uno con sus pendientes y acciones, sin necesidad de conmutar de rol.
3. **CA-HU-02-03 — Perfil único (éxito):** Dado que la persona tiene un solo perfil habilitado, cuando se carga el panel, entonces solo se muestra el apartado correspondiente, sin apartados de roles inexistentes; si no tiene actividad, se muestra su estado vacío.
4. **CA-HU-02-04 — Perfiles adicionales (éxito):** Dado que la persona también tiene perfil de Editor o Administrador, cuando se carga el panel, entonces los apartados adicionales se muestran junto con los demás, con la misma separación visual.
5. **CA-HU-02-05 — Separación de datos (éxito):** Dado el panel multirrol, cuando la persona consulta cada apartado, entonces el apartado de Autor muestra solo sus manuscritos y el de Revisor solo sus asignaciones, sin mezclar datos.
6. **CA-HU-02-06 — Falla parcial (error):** Dado que un apartado no puede cargarse, cuando se presenta el panel, entonces los demás apartados siguen disponibles, se informa el problema y se ofrece reintentar, sin recurrir a una selección de rol.
7. **CA-HU-02-07 — Sin roles habilitados (error):** Dado que la persona no tiene ningún rol activo, cuando inicia sesión, entonces el sistema muestra un mensaje claro de "sin roles habilitados", impide el acceso a funciones y solicita contactar al Administrador.
8. **CA-HU-02-08 — Rol retirado durante la sesión (caso límite):** Dado que un rol es retirado mientras la sesión está activa, cuando la persona intenta usar una función de ese rol, entonces el sistema deniega la acción, actualiza el panel y muestra un mensaje informativo.
9. **CA-HU-02-09 — Conflicto entre perfiles (caso límite):** Dado que la persona es Autora de un manuscrito y también Revisora del mismo, cuando se carga el panel, entonces el manuscrito no aparece en el apartado de Revisor y prevalece la regla de conflicto de interés.
10. **CA-HU-02-10 — Sin pasos intermedios (éxito):** Dado el panel unificado, cuando la persona necesita pasar de una tarea de Autor a una de Revisor, entonces puede hacerlo directamente en la misma vista, sin asistentes ni cambios de perfil.

---

#### HU-03 — Control de acceso por rol y por objeto

**Prioridad:** P1  
**Trazabilidad:** RF-16; RN-03, RN-17, RN-20.

**Como** usuario institucional, **quiero** que el sistema me permita ver y hacer solo lo que mi rol y mi relación con cada manuscrito autorizan, **para** proteger la confidencialidad y la integridad del proceso.

**Criterios de aceptación**

1. **CA-HU-03-01 — Acceso por rol (éxito):** Dado un usuario autenticado, cuando navega por el sistema, entonces solo ve los apartados y acciones correspondientes a sus roles habilitados.
2. **CA-HU-03-02 — Acceso por objeto (éxito):** Dado un manuscrito concreto, cuando un actor intenta consultarlo o modificarlo, entonces el sistema verifica además que tenga relación autorizada con ese manuscrito.
3. **CA-HU-03-03 — Autor sobre documentos ajenos (error):** Dado un Autor, cuando intenta acceder a un manuscrito de otra persona, entonces el sistema deniega el acceso sin revelar si el manuscrito existe.
4. **CA-HU-03-04 — Revisor sobre asignaciones ajenas (error):** Dado un Revisor, cuando intenta abrir un manuscrito no asignado o consultar datos de autoría, entonces el sistema deniega el acceso sin revelar la existencia del recurso.
5. **CA-HU-03-05 — Editor con conflicto (error):** Dado un Editor que es autor o coautor de un manuscrito, cuando intenta registrar un veredicto o una corrección, entonces el sistema bloquea la acción por conflicto de interés y registra el intento.
6. **CA-HU-03-06 — Administrador sobre la auditoría (error):** Dado un Administrador, cuando intenta modificar o eliminar un registro de auditoría o de historial, entonces el sistema deniega la operación y registra el intento.
7. **CA-HU-03-07 — Acción no autorizada (error):** Dado cualquier intento de ejecutar una acción sin permiso, cuando el sistema lo detecta, entonces bloquea la acción, no expone datos y muestra un mensaje genérico de "no autorizado".
8. **CA-HU-03-08 — Acceso público (error):** Dado un miembro del público, cuando intenta acceder a secciones internas, entonces el sistema lo redirige al catálogo o al inicio de sesión, sin mostrar información interna.
9. **CA-HU-03-09 — Rol suficiente, objeto insuficiente (caso límite):** Dado un usuario con un rol habilitado, cuando intenta actuar sobre un documento fuera de su ámbito, entonces el rol no es suficiente y la acción se bloquea.
10. **CA-HU-03-10 — Registro de denegaciones (éxito):** Dado un intento denegado, cuando el sistema lo procesa, entonces registra actor, fecha, acción intentada y resultado en la auditoría.

---

### Módulo 2: Panel del Autor (Gestión de Manuscritos)

#### HU-04 — Registrar manuscrito con metadatos y PDF

**Prioridad:** P1  
**Trazabilidad:** RF-02, RF-14; RN-07, RN-08, RN-10.

**Como** Autor, **quiero** registrar un manuscrito con los metadatos obligatorios y un archivo PDF válido, **para** iniciar formalmente el proceso editorial y conservar una primera versión íntegra.

**Criterios de aceptación**

1. **CA-HU-04-01 — Registro en borrador (éxito):** Dado un Autor autenticado, cuando completa total o parcialmente los metadatos y guarda, entonces el sistema conserva el manuscrito en estado Borrador sin crear todavía una versión formal.
2. **CA-HU-04-02 — Metadatos obligatorios (éxito):** Dado el formulario de registro, cuando el Autor lo completa, entonces el sistema exige como mínimo título, resumen, palabras clave, área de conocimiento, idioma, al menos un autor con filiación y los datos de contacto del autor responsable.
3. **CA-HU-04-03 — Autor registrante (caso límite):** Dado un Autor autenticado, cuando registra un manuscrito, entonces debe figurar como autor o coautor del mismo; si no figura, el sistema bloquea el registro.
4. **CA-HU-04-04 — Envío formal (éxito):** Dado un manuscrito con metadatos completos y un PDF válido, cuando el Autor confirma el envío, entonces el sistema lo pasa a estado Enviado, crea la versión v1 y la ronda 0, conserva el PDF exacto y los metadatos, y muestra un código único de seguimiento.
5. **CA-HU-04-05 — Campos incompletos (error):** Dado un formulario con campos obligatorios vacíos, cuando el Autor intenta enviar, entonces el sistema impide el envío, resalta cada campo faltante y conserva lo ya ingresado como borrador.
6. **CA-HU-04-06 — PDF inválido (error):** Dado un archivo que no cumple las condiciones de HU-05, cuando el Autor intenta adjuntarlo, entonces el sistema lo rechaza, no crea la versión y explica el motivo.
7. **CA-HU-04-07 — Envío duplicado (caso límite):** Dado un Autor que confirma el envío más de una vez, cuando el sistema procesa la solicitud, entonces crea un solo manuscrito y una sola versión v1; las solicitudes posteriores informan que el envío ya fue registrado.
8. **CA-HU-04-08 — Envío interrumpido (caso límite):** Dado un envío interrumpido antes de completarse, cuando el Autor vuelve a ingresar, entonces no existe un manuscrito ni una versión parcial; el borrador previo se conserva.
9. **CA-HU-04-09 — Conflicto de interés (caso límite):** Dado un Autor que también es Revisor, cuando registra un manuscrito, entonces el sistema impide que ese mismo manuscrito le sea asignado para evaluación.
10. **CA-HU-04-10 — Registro de auditoría (éxito):** Dado el registro y el envío formal, cuando se completan, entonces el sistema registra la creación, el envío, la versión y la fecha en la auditoría.

---

#### HU-05 — Validar formato y condiciones del PDF

**Prioridad:** P1  
**Trazabilidad:** RF-14; RN-07.

**Como** Autor, **quiero** que el sistema valide el archivo adjunto antes de aceptarlo, **para** asegurar que el manuscrito cumple el formato y las condiciones institucionales.

**Criterios de aceptación**

1. **CA-HU-05-01 — PDF válido (éxito):** Dado un archivo cuyo contenido es un PDF válido, legible, no dañado, no protegido con contraseña y dentro del tamaño máximo, cuando el Autor lo adjunta, entonces el sistema lo acepta, muestra su nombre y tamaño, y habilita el envío.
2. **CA-HU-05-02 — Formato distinto (error):** Dado un archivo con extensión distinta de PDF, cuando el Autor intenta adjuntarlo, entonces el sistema lo rechaza y muestra que solo se admiten archivos PDF.
3. **CA-HU-05-03 — Extensión engañosa (error):** Dado un archivo con extensión `.pdf` cuyo contenido no corresponde a un PDF válido, cuando el Autor lo adjunta, entonces el sistema lo rechaza y no crea ninguna versión.
4. **CA-HU-05-04 — Archivo dañado o vacío (error):** Dado un PDF truncado, vacío o ilegible, cuando el Autor lo adjunta, entonces el sistema lo rechaza e indica que el archivo no puede abrirse correctamente.
5. **CA-HU-05-05 — Archivo protegido (error):** Dado un PDF protegido con contraseña o con restricciones que impiden su lectura, cuando el Autor lo adjunta, entonces el sistema lo rechaza y solicita una versión sin protección.
6. **CA-HU-05-06 — Tamaño excedido (error):** Dado un PDF que supera el tamaño máximo institucional, cuando el Autor lo adjunta, entonces el sistema lo rechaza, indica el límite vigente y no conserva una carga parcial.
7. **CA-HU-05-07 — Contenido no permitido (error):** Dado un archivo con contenido activo o ejecutable no permitido por la política institucional, cuando el sistema lo analiza, entonces lo rechaza por seguridad y registra el intento.
8. **CA-HU-05-08 — Límite exacto (caso límite):** Dado un PDF cuyo tamaño es exactamente igual al máximo permitido, cuando el Autor lo adjunta, entonces el sistema lo acepta.
9. **CA-HU-05-09 — Carga interrumpida (caso límite):** Dado un intento de carga que se interrumpe, cuando el Autor vuelve a ingresar, entonces no existe una versión parcial y la versión anterior, si existía, permanece vigente.
10. **CA-HU-05-10 — Reemplazo antes del envío (caso límite):** Dado un PDF ya aceptado pero aún no enviado, cuando el Autor adjunta otro archivo válido, entonces solo se conserva el último archivo aceptado y no se duplica la versión.

---

#### HU-06 — Consultar estado y tareas pendientes

**Prioridad:** P1  
**Trazabilidad:** RF-05; RN-20.

**Como** Autor, **quiero** consultar el estado de mis manuscritos y las acciones que me corresponden, **para** saber qué debo hacer y en qué etapa está cada envío.

**Criterios de aceptación**

1. **CA-HU-06-01 — Listado propio (éxito):** Dado un Autor autenticado, cuando consulta su panel, entonces ve únicamente sus manuscritos con código, título, estado actual, versión actual, ronda de corrección, última actualización y acción pendiente.
2. **CA-HU-06-02 — Detalle comprensible (éxito):** Dado un manuscrito propio, cuando el Autor abre su detalle, entonces ve las observaciones de corrección, el veredicto cuando exista y la siguiente acción esperada, sin datos de identidad del Revisor.
3. **CA-HU-06-03 — Búsqueda y filtros (éxito):** Dado un conjunto de manuscritos propios, cuando el Autor busca por título o código y filtra por estado o fecha, entonces obtiene solo los que cumplen los criterios.
4. **CA-HU-06-04 — Archivados (éxito):** Dado un manuscrito dado de baja lógica, cuando el Autor activa la vista de archivados, entonces lo encuentra con la etiqueta "Dado de baja" y puede consultar su historial.
5. **CA-HU-06-05 — Sin manuscritos (error):** Dado un Autor sin manuscritos, cuando consulta el panel, entonces ve un estado vacío con un mensaje claro y la acción para registrar uno nuevo.
6. **CA-HU-06-06 — Documento ajeno (error):** Dado un Autor, cuando intenta consultar el manuscrito de otra persona, entonces el sistema no lo muestra y deniega el acceso directo sin revelar su existencia.
7. **CA-HU-06-07 — Estado desactualizado (caso límite):** Dado un manuscrito cuyo estado cambió mientras el Autor lo visualizaba, cuando el Autor intenta una acción basada en el estado anterior, entonces el sistema bloquea la acción, actualiza la vista y explica el cambio.
8. **CA-HU-06-08 — Sin acción pendiente (caso límite):** Dado un manuscrito en espera de revisión, cuando el Autor consulta el detalle, entonces se muestra "En espera de revisión" y no se ofrece una acción inexistente.
9. **CA-HU-06-09 — Manuscrito rechazado (caso límite):** Dado un manuscrito rechazado, cuando el Autor consulta el detalle, entonces ve el veredicto y la justificación; el sistema no permite cargar una nueva versión de ese manuscrito, pero el Autor puede registrar uno nuevo.
10. **CA-HU-06-10 — Filtros sin resultados (error):** Dado un filtro sin coincidencias, cuando el Autor consulta, entonces ve un mensaje de "sin resultados" y puede limpiar los filtros.

---

#### HU-07 — Editar metadatos solo en Borrador o Requiere Correcciones

**Prioridad:** P2  
**Trazabilidad:** RF-21; RN-08, RN-10.

**Como** Autor, **quiero** editar los metadatos de mi manuscrito únicamente cuando esté en Borrador o Requiere Correcciones, **para** corregir la información sin alterar versiones ya evaluadas.

**Criterios de aceptación**

1. **CA-HU-07-01 — Edición en Borrador (éxito):** Dado un manuscrito en Borrador, cuando el Autor modifica los metadatos, entonces el sistema guarda los cambios, valida los campos obligatorios y no crea una versión ni una ronda.
2. **CA-HU-07-02 — Edición en Requiere Correcciones (éxito):** Dado un manuscrito en Requiere Correcciones, cuando el Autor modifica los metadatos, entonces el sistema guarda los cambios, conserva intacto el registro de la versión anterior y registra la modificación para la próxima iteración.
3. **CA-HU-07-03 — Edición bloqueada (error):** Dado un manuscrito en Enviado, En Revisión, Aceptado o Rechazado, cuando el Autor intenta editar, entonces el sistema muestra los metadatos en modo de solo lectura y bloquea la acción con un mensaje que indica el estado.
4. **CA-HU-07-04 — Campo obligatorio vacío (error):** Dado un formulario de metadatos, cuando el Autor intenta guardar con un campo obligatorio vacío, entonces el sistema impide el guardado y resalta el campo.
5. **CA-HU-07-05 — Edición concurrente (caso límite):** Dado que la misma persona edita el manuscrito en dos sesiones simultáneas, cuando ambas intentan guardar, entonces el sistema detecta el conflicto, conserva una sola versión de los cambios e informa a la otra sesión que debe actualizar la información.
6. **CA-HU-07-06 — Autor responsable (caso límite):** Dado un manuscrito con un autor responsable designado, cuando el Autor intenta retirarlo sin designar a otro, entonces el sistema bloquea la acción.
7. **CA-HU-07-07 — Sin nueva versión (caso límite):** Dado un cambio exclusivo de metadatos, cuando el Autor guarda, entonces el contador de versiones y el de rondas no cambian.
8. **CA-HU-07-08 — Trazabilidad del cambio (éxito):** Dado un cambio de metadatos en Requiere Correcciones, cuando se guarda, entonces el sistema registra fecha, actor y campos modificados, sin alterar los metadatos conservados en iteraciones anteriores.

---

#### HU-08 — Dar de baja lógica un manuscrito

**Prioridad:** P2  
**Trazabilidad:** RF-22; RN-11, RN-13.

**Como** Autor, **quiero** dar de baja lógica un manuscrito propio, **para** retirarlo de los listados y del catálogo sin perder el historial ni la evidencia del proceso.

**Criterios de aceptación**

1. **CA-HU-08-01 — Baja confirmada (éxito):** Dado un manuscrito propio, cuando el Autor solicita la baja y confirma la acción, entonces el sistema aplica la marca "Dado de baja" y lo retira de los listados activos.
2. **CA-HU-08-02 — Motivo (éxito):** Dado un manuscrito en En Revisión o Aceptado, cuando el Autor solicita la baja, entonces el sistema exige un motivo antes de confirmar; en los demás estados el motivo es opcional.
3. **CA-HU-08-03 — Retiro del catálogo (éxito):** Dado un artículo Aceptado, cuando el Autor confirma la baja lógica, entonces el artículo deja de mostrarse en el catálogo público en un máximo de cinco minutos y su historial registra el retiro.
4. **CA-HU-08-04 — Revisión en curso (éxito):** Dado un manuscrito en En Revisión, cuando se da de baja, entonces la asignación activa se cancela, el Revisor y el Editor reciben aviso y no se admiten nuevas evaluaciones.
5. **CA-HU-08-05 — Documento ajeno (error):** Dado un Autor, cuando intenta dar de baja un manuscrito del que no es responsable, entonces el sistema deniega la acción sin revelar si el documento existe.
6. **CA-HU-08-06 — Baja repetida (caso límite):** Dado un manuscrito ya dado de baja, cuando el Autor intenta darlo de baja nuevamente, entonces el sistema informa que ya se encuentra en ese estado y no duplica la acción.
7. **CA-HU-08-07 — Borrado físico (error):** Dado cualquier intento de eliminar físicamente un manuscrito, cuando el sistema lo detecta, entonces lo impide y conserva versiones, historial y auditoría.
8. **CA-HU-08-08 — Baja durante una carga (caso límite):** Dado un manuscrito con una carga de PDF en curso, cuando el Autor confirma la baja, entonces la carga se cancela y no se crea una versión parcial.
9. **CA-HU-08-09 — Integridad histórica (caso límite):** Dado un manuscrito con versiones y veredictos previos, cuando se da de baja, entonces esos registros permanecen intactos y consultables por los roles autorizados.
10. **CA-HU-08-10 — Registro de auditoría (éxito):** Dado una baja lógica, cuando se completa, entonces el sistema registra actor, fecha, estado anterior y motivo en la auditoría.

---

#### HU-09 — Enviar nueva versión en Requiere Correcciones

**Prioridad:** P2  
**Trazabilidad:** RF-06; RN-09, RN-10, RN-15.

**Como** Autor, **quiero** enviar una nueva versión de mi manuscrito cuando el Editor haya solicitado correcciones, **para** atender las observaciones y continuar el proceso sin sobrescribir la versión anterior.

**Criterios de aceptación**

1. **CA-HU-09-01 — Nueva versión (éxito):** Dado un manuscrito en Requiere Correcciones, cuando el Autor adjunta un PDF válido y confirma el envío, entonces el sistema crea la versión consecutiva, la asocia a la ronda vigente, lo pasa a Enviado y conserva la versión anterior sin cambios.
2. **CA-HU-09-02 — Confirmación (éxito):** Dado un nuevo envío, cuando se completa, entonces el Autor ve el número de versión, la ronda, la fecha y el código del manuscrito, y el Editor recibe la notificación correspondiente.
3. **CA-HU-09-03 — Estado incorrecto (error):** Dado un manuscrito en Borrador, Enviado, En Revisión, Aceptado o Rechazado, cuando el Autor intenta cargar una nueva versión, entonces el sistema bloquea la acción y explica que solo se permite en Requiere Correcciones.
4. **CA-HU-09-04 — PDF inválido (error):** Dado un archivo que no cumple las condiciones de HU-05, cuando el Autor intenta enviarlo como nueva versión, entonces el sistema lo rechaza, no crea la versión y conserva el estado Requiere Correcciones.
5. **CA-HU-09-05 — Sin cambios (caso límite):** Dado un nuevo envío en el que ni el PDF ni los metadatos presentan cambios respecto de la versión anterior, cuando el Autor intenta confirmar, entonces el sistema bloquea el envío e indica que debe existir al menos una corrección.
6. **CA-HU-09-06 — Envíos simultáneos (caso límite):** Dado que se intentan registrar dos nuevas versiones a la vez, cuando el sistema las procesa, entonces solo una se registra como la siguiente versión y la otra recibe un mensaje de conflicto, sin sobrescribir archivos.
7. **CA-HU-09-07 — Carga interrumpida (caso límite):** Dado un envío interrumpido, cuando el Autor vuelve a ingresar, entonces no existe una versión parcial, el estado sigue siendo Requiere Correcciones y la versión anterior permanece vigente.
8. **CA-HU-09-08 — Solo metadatos (caso límite):** Dado un Autor que modifica metadatos pero no adjunta un PDF, cuando intenta enviar, entonces el sistema le permite guardar los metadatos, pero no registrar la nueva versión.
9. **CA-HU-09-09 — Abandono de la corrección (caso límite):** Dado un Autor que decide no continuar, cuando solicita la baja lógica, entonces la ronda y la versión quedan registradas en el historial como parte del proceso.
10. **CA-HU-09-10 — Registro de auditoría (éxito):** Dado un nuevo envío, cuando se completa, entonces el sistema registra la versión, la ronda, el PDF y los metadatos en el historial y en la auditoría.

---

### Módulo 3: Panel del Editor (Coordinación)

#### HU-10 — Visualizar nuevos envíos y pasar a En Revisión

**Prioridad:** P1  
**Trazabilidad:** RF-17; RN-18.

**Como** Editor, **quiero** visualizar los manuscritos nuevos y pasarlos a En Revisión, **para** iniciar formalmente la evaluación editorial.

**Criterios de aceptación**

1. **CA-HU-10-01 — Bandeja de nuevos envíos (éxito):** Dado un Editor autenticado, cuando consulta su panel, entonces ve los manuscritos en estado Enviado con código, título, autor, área, fecha, versión y ronda, y puede filtrarlos y ordenarlos.
2. **CA-HU-10-02 — Detalle del envío (éxito):** Dado un manuscrito nuevo, cuando el Editor lo abre, entonces ve los metadatos completos, la identidad de los autores, el PDF y un resumen del historial.
3. **CA-HU-10-03 — Paso a revisión (éxito):** Dado un manuscrito en Enviado, cuando el Editor confirma "Pasar a En Revisión", entonces el estado cambia, se registra actor y fecha, el Autor recibe aviso y el manuscrito queda pendiente de asignación de Revisor.
4. **CA-HU-10-04 — Transición con asignación (éxito):** Dado un manuscrito en Enviado, cuando el Editor decide pasar a revisión y asignar al Revisor en la misma acción, entonces ambas operaciones se completan juntas; si la asignación falla, el estado no cambia.
5. **CA-HU-10-05 — Estado incorrecto (error):** Dado un manuscrito que no está en Enviado, cuando el Editor intenta pasarlo a En Revisión, entonces el sistema bloquea la acción y muestra el estado actual.
6. **CA-HU-10-06 — Acción concurrente (caso límite):** Dado que otro Editor ya pasó el manuscrito a En Revisión, cuando el primero intenta la misma acción, entonces el sistema informa el conflicto, no duplica la transición y muestra el estado actualizado.
7. **CA-HU-10-07 — Manuscrito dado de baja (error):** Dado un manuscrito con baja lógica, cuando el Editor intenta abrirlo o pasarlo a revisión, entonces no aparece en la bandeja activa y la acción se bloquea.
8. **CA-HU-10-08 — Sin Revisor disponible (caso límite):** Dado un manuscrito que pasa a En Revisión sin un Revisor elegible, cuando el Editor confirma, entonces el estado cambia a En Revisión con la indicación "pendiente de asignación" y no se permite emitir veredicto hasta que exista una evaluación.
9. **CA-HU-10-09 — Envío inconsistente (error):** Dado un manuscrito sin metadatos completos o sin PDF válido, cuando el Editor intenta pasarlo a revisión, entonces el sistema bloquea la acción y reporta la inconsistencia.
10. **CA-HU-10-10 — Registro de auditoría (éxito):** Dado el paso a En Revisión, cuando se completa, entonces el sistema registra el cambio de estado en la auditoría.

---

#### HU-11 — Asignar exactamente un Revisor experto

**Prioridad:** P1  
**Trazabilidad:** RF-03; RN-04, RN-05, RN-17.

**Como** Editor, **quiero** asignar exactamente un Revisor experto a cada manuscrito en revisión, **para** garantizar una evaluación especializada, confidencial y sin duplicidad.

**Criterios de aceptación**

1. **CA-HU-11-01 — Lista de elegibles (éxito):** Dado un manuscrito en En Revisión, cuando el Editor busca Revisores, entonces el sistema muestra únicamente personas activas, con experiencia en el área del manuscrito o en un área afín, sin conflicto de interés y que no sean autores o coautores.
2. **CA-HU-11-02 — Asignación única (éxito):** Dado un Revisor elegible, cuando el Editor lo selecciona y confirma, entonces el sistema registra exactamente una asignación activa, fija la fecha y hora de inicio y calcula el plazo de 20 días calendario.
3. **CA-HU-11-03 — Notificaciones (éxito):** Dado una asignación confirmada, cuando se completa, entonces el Revisor recibe el aviso con el plazo y el Autor recibe un aviso de que el manuscrito está en revisión, sin conocer la identidad del Revisor.
4. **CA-HU-11-04 — Segundo Revisor (error):** Dado un manuscrito con un Revisor activo, cuando el Editor intenta asignar a otro sin revocar al primero, entonces el sistema bloquea la acción e indica que debe revocar la asignación vigente.
5. **CA-HU-11-05 — Conflicto de autoría (error):** Dado un Revisor que es autor o coautor del manuscrito, cuando el Editor intenta asignarlo, entonces el sistema bloquea la asignación por conflicto de interés y registra el intento.
6. **CA-HU-11-06 — Revisor no habilitado (error):** Dado un Revisor inactivo, sin el rol habilitado o sin experiencia declarada en el área ni en un área afín, cuando el Editor intenta asignarlo, entonces el sistema bloquea la acción y explica el motivo.
7. **CA-HU-11-07 — Asignación duplicada (caso límite):** Dado un Revisor ya asignado al mismo manuscrito y versión, cuando el Editor intenta asignarlo de nuevo, entonces el sistema impide la duplicación.
8. **CA-HU-11-08 — Sin elegibles (error):** Dado un manuscrito sin Revisores elegibles, cuando el Editor intenta asignar, entonces el sistema no permite la asignación y muestra un mensaje con las condiciones que deben cumplirse.
9. **CA-HU-11-09 — Asignación concurrente (caso límite):** Dado que dos Editores intentan asignar Revisores al mismo manuscrito al mismo tiempo, cuando el sistema procesa las solicitudes, entonces solo una asignación queda activa y la otra recibe un mensaje de conflicto.
10. **CA-HU-11-10 — Conflicto posterior (caso límite):** Dado un Revisor que declara un conflicto de interés después de ser asignado, cuando lo informa, entonces puede abstenerse, el Editor revoca la asignación con motivo y reasigna el manuscrito.
11. **CA-HU-11-11 — Registro de auditoría (éxito):** Dado una asignación, revocación o reasignación, cuando se completa, entonces el sistema registra Revisor, fecha, plazo y motivo en la auditoría.

---

#### HU-12 — Revocar y reasignar por inactividad de 20 días

**Prioridad:** P2  
**Trazabilidad:** RF-03; RN-04, RN-05, RN-13.

**Como** Editor, **quiero** revocar la asignación de un Revisor que no haya evaluado al cumplirse 20 días exactos y asignar a otro, **para** evitar que el proceso quede detenido.

**Criterios de aceptación**

1. **CA-HU-12-01 — Plazo visible (éxito):** Dado un Revisor asignado, cuando consulta su asignación, entonces ve la fecha y hora exactas de vencimiento, calculadas como 20 días calendario desde la asignación.
2. **CA-HU-12-02 — Vencimiento exacto (éxito):** Dado un Revisor sin evaluación final, cuando se cumple el instante exacto de los 20 días, entonces el sistema marca la asignación como "Plazo vencido", cierra el envío final de la evaluación y notifica al Editor.
3. **CA-HU-12-03 — Revocación manual (éxito):** Dado una asignación vencida, cuando el Editor confirma la revocación, entonces el sistema la registra como "revocada por inactividad", con fecha, actor y motivo, y mantiene el manuscrito en En Revisión.
4. **CA-HU-12-04 — Reasignación (éxito):** Dado un manuscrito con la asignación revocada, cuando el Editor asigna a un nuevo Revisor, entonces se crea una nueva asignación activa, se inicia un nuevo plazo de 20 días y se conserva la asignación anterior en el historial.
5. **CA-HU-12-05 — Sin revocación automática (caso límite):** Dado el vencimiento del plazo, cuando el Editor no actúa, entonces el manuscrito permanece en En Revisión con la alerta de vencimiento; el sistema no revoca ni reasigna por sí solo.
6. **CA-HU-12-06 — Revocación anticipada por inactividad (error):** Dado un plazo aún no vencido, cuando el Editor intenta revocar por inactividad, entonces el sistema bloquea la acción; solo se permite antes del plazo por conflicto de interés, error de asignación o cuenta inhabilitada, con motivo registrado.
7. **CA-HU-12-07 — Evaluación ya registrada (error):** Dado un Revisor que ya registró su evaluación final, cuando el Editor intenta revocarlo por inactividad, entonces el sistema bloquea la acción porque no existe incumplimiento.
8. **CA-HU-12-08 — Nueva asignación sin revocar (error):** Dado un manuscrito con una asignación vencida pero no revocada, cuando el Editor intenta asignar a otro Revisor, entonces el sistema exige primero la revocación.
9. **CA-HU-12-09 — Acciones concurrentes (caso límite):** Dado que dos Editores intentan revocar la misma asignación al mismo tiempo, cuando el sistema procesa las solicitudes, entonces solo una revocación se registra y la otra informa que la asignación ya fue revocada.
10. **CA-HU-12-10 — Límite exacto (caso límite):** Dado un envío de evaluación final en el instante exacto del vencimiento, cuando el sistema lo recibe, entonces aplica la regla de corte: se considera fuera de plazo desde el instante en que se cumplen los 20 días y no se registra como evaluación válida.
11. **CA-HU-12-11 — Registro de auditoría (éxito):** Dado un vencimiento, revocación o reasignación, cuando ocurre, entonces el sistema registra fecha, actor, Revisor anterior, Revisor nuevo y motivo.

---

#### HU-13 — Registrar veredicto final y solicitar correcciones

**Prioridad:** P1  
**Trazabilidad:** RF-07, RF-15, RF-19; RN-12, RN-15.

**Como** Editor, **quiero** registrar el veredicto final del manuscrito y, cuando corresponda, solicitar correcciones con observaciones, **para** comunicar formalmente el resultado y continuar o cerrar el proceso editorial.

**Criterios de aceptación**

1. **CA-HU-13-01 — Requisito de evaluación (éxito):** Dado un manuscrito en En Revisión con la evaluación final del Revisor asignado, cuando el Editor abre el veredicto, entonces puede seleccionar Aceptado, Rechazado o Requiere Correcciones.
2. **CA-HU-13-02 — Aceptación (éxito):** Dado un manuscrito con evaluación final, cuando el Editor registra Aceptado, entonces el estado cambia a Aceptado, el Autor recibe el aviso y el artículo queda disponible en el catálogo público en un plazo máximo de cinco minutos.
3. **CA-HU-13-03 — Rechazo (éxito):** Dado un manuscrito con evaluación final, cuando el Editor registra Rechazado y completa la justificación obligatoria, entonces el estado cambia a Rechazado, el Autor recibe la decisión y el manuscrito no aparece en el catálogo.
4. **CA-HU-13-04 — Correcciones (éxito):** Dado un manuscrito con evaluación final, cuando el Editor registra Requiere Correcciones y completa las observaciones obligatorias, entonces el estado cambia, la ronda de corrección se incrementa en uno, el Autor recibe las observaciones y puede editar metadatos y enviar una nueva versión.
5. **CA-HU-13-05 — Sin evaluación (error):** Dado un manuscrito sin evaluación final, cuando el Editor intenta registrar cualquier veredicto, entonces el sistema bloquea la acción e indica que debe existir una evaluación completa.
6. **CA-HU-13-06 — Correcciones sin observaciones (error):** Dado el veredicto Requiere Correcciones, cuando el Editor no ingresa observaciones, entonces el sistema impide el registro.
7. **CA-HU-13-07 — Rechazo sin justificación (error):** Dado el veredicto Rechazado, cuando el Editor no ingresa una justificación, entonces el sistema impide el registro.
8. **CA-HU-13-08 — Conflicto de interés (error):** Dado un Editor que es autor o coautor del manuscrito, cuando intenta registrar el veredicto, entonces el sistema bloquea la acción por conflicto y registra el intento.
9. **CA-HU-13-09 — Veredictos concurrentes (caso límite):** Dado que dos Editores registran veredictos al mismo tiempo, cuando el sistema los procesa, entonces solo uno se registra y el otro recibe un mensaje de conflicto; no se sobrescribe el primero.
10. **CA-HU-13-10 — Discrepancia con el Revisor (caso límite):** Dado que el Editor decide algo distinto de la recomendación del Revisor, cuando registra el veredicto, entonces debe ingresar una justificación y la recomendación original permanece en el historial.
11. **CA-HU-13-11 — Manuscrito dado de baja (error):** Dado un manuscrito con baja lógica, cuando el Editor intenta registrar un veredicto, entonces el sistema bloquea la acción.
12. **CA-HU-13-12 — Veredicto inmutable (caso límite):** Dado un veredicto ya registrado, cuando alguien intenta modificarlo o eliminarlo, entonces el sistema lo impide; si existe un error, solo un Administrador puede habilitar una nueva decisión, conservando ambas en el historial y en la auditoría.
13. **CA-HU-13-13 — Registro de auditoría (éxito):** Dado un veredicto, cuando se registra, entonces el sistema conserva actor, fecha, resultado, versión afectada, justificación u observaciones y deja evidencia en la auditoría.

---

### Módulo 4: Panel del Revisor (Evaluación Doble Ciego)

#### HU-14 — Consultar asignaciones pendientes y plazos

**Prioridad:** P1  
**Trazabilidad:** RF-04, RF-18; RN-04, RN-05, RN-20.

**Como** Revisor, **quiero** consultar únicamente mis asignaciones pendientes y sus plazos, **para** organizar mi trabajo y evaluar dentro del tiempo establecido.

**Criterios de aceptación**

1. **CA-HU-14-01 — Bandeja propia (éxito):** Dado un Revisor autenticado, cuando consulta su panel, entonces ve solo sus asignaciones activas con código, título, área, ronda, versión, fecha de asignación, fecha límite y estado.
2. **CA-HU-14-02 — Estados de la asignación (éxito):** Dado un conjunto de asignaciones, cuando el Revisor las consulta, entonces distingue claramente entre pendiente, en plazo, vencida, evaluada y revocada.
3. **CA-HU-14-03 — Detalle anonimizado (éxito):** Dado una asignación, cuando el Revisor la abre, entonces accede al manuscrito y al formulario sin ningún dato de identidad del Autor.
4. **CA-HU-14-04 — Filtros y orden (éxito):** Dado un conjunto de asignaciones, cuando el Revisor filtra por estado u ordena por fecha límite, entonces obtiene la vista solicitada.
5. **CA-HU-14-05 — Sin asignaciones (error):** Dado un Revisor sin asignaciones, cuando consulta su panel, entonces ve un estado vacío con un mensaje claro.
6. **CA-HU-14-06 — Manuscrito no asignado (error):** Dado un Revisor, cuando intenta abrir un manuscrito que no le fue asignado, entonces el sistema deniega el acceso sin revelar su existencia.
7. **CA-HU-14-07 — Asignación revocada (caso límite):** Dado una asignación revocada, cuando el Revisor consulta su bandeja, entonces deja de aparecer entre las pendientes y figura en su historial como revocada.
8. **CA-HU-14-08 — Plazo vencido (caso límite):** Dado una asignación cuyo plazo venció, cuando el Revisor la abre, entonces ve el estado "vencida", el formulario cerrado y la indicación de que el Editor decidirá la reasignación.
9. **CA-HU-14-09 — Reasignación (caso límite):** Dado un manuscrito reasignado a otra persona, cuando el Revisor anterior intenta acceder, entonces el sistema le deniega el acceso y conserva su registro histórico.
10. **CA-HU-14-10 — Manuscrito dado de baja (caso límite):** Dado un manuscrito con baja lógica, cuando el Revisor consulta su bandeja, entonces la asignación se cancela y no permite evaluar.

---

#### HU-15 — Completar formulario de evaluación estructurado

**Prioridad:** P1  
**Trazabilidad:** RF-04, RF-18; RN-05, RN-12.

**Como** Revisor, **quiero** completar un formulario de evaluación estructurado para mis asignaciones pendientes, **para** emitir una recomendación técnica fundamentada y verificable.

**Criterios de aceptación**

1. **CA-HU-15-01 — Formulario completo (éxito):** Dado una asignación pendiente, cuando el Revisor abre el formulario, entonces encuentra criterios de originalidad y contribución, rigor metodológico, claridad, relevancia y cumplimiento ético, cada uno con su valoración.
2. **CA-HU-15-02 — Recomendación obligatoria (éxito):** Dado el formulario, cuando el Revisor lo completa, entonces debe seleccionar una recomendación general: Aceptar, Requiere Correcciones o Rechazar.
3. **CA-HU-15-03 — Comentarios (éxito):** Dado el formulario, cuando el Revisor lo completa, entonces debe ingresar observaciones para el Autor y puede ingresar observaciones confidenciales para el Editor.
4. **CA-HU-15-04 — Declaración de conflicto (éxito):** Dado el formulario, cuando el Revisor lo inicia, entonces debe declarar si tiene o no un conflicto de interés.
5. **CA-HU-15-05 — Borrador privado (éxito):** Dado un formulario incompleto, cuando el Revisor guarda, entonces el sistema conserva un borrador privado que solo él puede consultar antes del envío final.
6. **CA-HU-15-06 — Envío final (éxito):** Dado un formulario completo, cuando el Revisor confirma el envío final, entonces el sistema registra una única evaluación vinculada al Revisor, al manuscrito, a la versión y a la ronda, y la deja disponible para el Editor.
7. **CA-HU-15-07 — Campos faltantes (error):** Dado un formulario con campos obligatorios incompletos, cuando el Revisor intenta enviarlo, entonces el sistema impide el envío y resalta cada campo faltante.
8. **CA-HU-15-08 — Envío fuera de plazo (error):** Dado un formulario abierto, cuando el Revisor intenta enviarlo después del instante exacto de vencimiento, entonces el sistema bloquea el envío final, conserva el borrador y muestra que el plazo venció.
9. **CA-HU-15-09 — Envío duplicado (caso límite):** Dado un Revisor que ya envió su evaluación final, cuando intenta enviar otra, entonces el sistema impide la duplicación y muestra la evaluación registrada en modo de solo lectura.
10. **CA-HU-15-10 — Conflicto declarado (caso límite):** Dado un Revisor que declara un conflicto de interés, cuando intenta continuar con la evaluación, entonces el sistema bloquea el envío, notifica al Editor y solicita la reasignación.
11. **CA-HU-15-11 — Interrupción (caso límite):** Dado un envío final interrumpido, cuando el Revisor vuelve a ingresar, entonces no existe una evaluación parcial y el borrador se conserva.
12. **CA-HU-15-12 — Registro de auditoría (éxito):** Dado un envío final, cuando se completa, entonces el sistema registra la evaluación, la fecha y el resultado en la auditoría, sin incluir el texto completo de los comentarios.

---

#### HU-16 — Evaluar bajo doble ciego

**Prioridad:** P1  
**Trazabilidad:** RF-04, RF-18; RN-06, RN-20.

**Como** Revisor, **quiero** acceder al manuscrito y evaluarlo sin conocer la identidad ni los metadatos personales del Autor, **para** emitir un juicio imparcial.

**Criterios de aceptación**

1. **CA-HU-16-01 — Vista anonimizada (éxito):** Dado una asignación, cuando el Revisor accede al manuscrito, entonces ve código, título, resumen, palabras clave, área, ronda, versión, PDF sanitizado y formulario, sin nombres, filiaciones, contactos, identificadores personales ni agradecimientos.
2. **CA-HU-16-02 — PDF sanitizado (éxito):** Dado el PDF disponible para el Revisor, cuando lo consulta o descarga, entonces el archivo no revela el nombre del Autor, su filiación, sus datos de contacto, el nombre original del archivo ni propiedades personales del documento.
3. **CA-HU-16-03 — Notificaciones y mensajes (éxito):** Dado cualquier aviso dirigido al Revisor, cuando se muestra, entonces no contiene datos de identidad del Autor; y cualquier aviso dirigido al Autor no contiene datos de identidad del Revisor.
4. **CA-HU-16-04 — Identidad del Revisor (éxito):** Dado una evaluación registrada, cuando el Autor consulta las observaciones, entonces ve los comentarios sin el nombre ni los datos del Revisor, y no accede a los comentarios confidenciales.
5. **CA-HU-16-05 — Intento de acceso (error):** Dado un Revisor, cuando intenta consultar datos de autoría, evaluaciones de otros o información no asignada, entonces el sistema deniega el acceso sin revelar la existencia del recurso y registra el intento.
6. **CA-HU-16-06 — Fuga en el contenido (caso límite):** Dado un manuscrito cuyo texto revela la identidad del Autor, cuando el Revisor lo detecta, entonces el sistema le permite reportarlo por el canal confidencial, registra el reporte y el Editor decide si solicita una versión anonimizada o reasigna la evaluación.
7. **CA-HU-16-07 — Conflicto de autoría (caso límite):** Dado que el Revisor es autor o coautor del manuscrito, cuando intenta acceder o evaluar, entonces el sistema bloquea la acción por conflicto de interés.
8. **CA-HU-16-08 — Descarga auditada (éxito):** Dado el acceso o descarga del PDF por parte del Revisor, cuando se produce, entonces el sistema registra el evento en la auditoría sin exponer datos del Autor.
9. **CA-HU-16-09 — Error del sistema (error):** Dado un error al mostrar información, cuando el sistema genera el mensaje, entonces no incluye datos de identidad del Autor ni del Revisor y presenta un mensaje genérico.
10. **CA-HU-16-10 — Reasignación (caso límite):** Dado un manuscrito reasignado, cuando el nuevo Revisor accede, entonces solo ve la versión actual y no accede a evaluaciones ni a la identidad de Revisores anteriores.

---

#### HU-17 — Consultar historial de evaluaciones propias

**Prioridad:** P2  
**Trazabilidad:** RF-09; RN-06, RN-20.

**Como** Revisor, **quiero** consultar el historial de las evaluaciones que he registrado, **para** dar seguimiento a mi trabajo sin acceder a información de otros revisores ni a la identidad de los autores.

**Criterios de aceptación**

1. **CA-HU-17-01 — Historial propio (éxito):** Dado un Revisor autenticado, cuando consulta su historial, entonces ve únicamente sus evaluaciones con código del manuscrito, título anonimizado, ronda, versión, fecha, recomendación y estado.
2. **CA-HU-17-02 — Consulta de solo lectura (éxito):** Dado una evaluación ya enviada, cuando el Revisor la abre, entonces puede consultar su contenido en modo de solo lectura, sin poder modificarlo.
3. **CA-HU-17-03 — Resultado del proceso (éxito):** Dado una evaluación propia, cuando el Editor ya registró el veredicto, entonces el Revisor ve el resultado del manuscrito sin datos de identidad del Autor.
4. **CA-HU-17-04 — Evaluaciones ajenas (error):** Dado un Revisor, cuando intenta consultar evaluaciones de otra persona, entonces el sistema deniega el acceso sin revelar su contenido.
5. **CA-HU-17-05 — Identidad del Autor (error):** Dado el historial del Revisor, cuando se muestra cualquier registro, entonces no aparecen nombres, contactos ni filiaciones del Autor.
6. **CA-HU-17-06 — Asignación revocada (caso límite):** Dado una asignación revocada sin evaluación, cuando el Revisor consulta su historial, entonces ve el registro como "revocada" y no como evaluación.
7. **CA-HU-17-07 — Reasignación (caso límite):** Dado un manuscrito que fue reasignado, cuando el Revisor anterior consulta su historial, entonces conserva su registro y no ve la evaluación del nuevo Revisor.
8. **CA-HU-17-08 — Manuscrito dado de baja (caso límite):** Dado un manuscrito con baja lógica, cuando el Revisor consulta su historial, entonces la evaluación permanece con la etiqueta "Dado de baja" y sin identidad del Autor.
9. **CA-HU-17-09 — Corrección de errores (caso límite):** Dado una evaluación final con un error, cuando el Revisor solicita corregirla, entonces el sistema no la sobrescribe; el Editor decide si habilita una nueva versión de la evaluación y conserva la anterior.
10. **CA-HU-17-10 — Búsqueda y filtros (éxito):** Dado un historial amplio, cuando el Revisor filtra por fecha, estado o recomendación, entonces obtiene los registros coincidentes.

---

### Módulo 5: Catálogo y Auditoría

#### HU-18 — Buscar y filtrar artículos aceptados en el catálogo público

**Prioridad:** P2  
**Trazabilidad:** RF-13; RN-14, RN-20.

**Como** miembro del público, **quiero** buscar y filtrar los artículos aceptados, **para** encontrar publicaciones relevantes sin necesidad de iniciar sesión.

**Criterios de aceptación**

1. **CA-HU-18-01 — Acceso público (éxito):** Dado cualquier miembro del público, cuando accede al catálogo, entonces puede consultarlo sin iniciar sesión y solo ve manuscritos en estado Aceptado y no dados de baja.
2. **CA-HU-18-02 — Búsqueda (éxito):** Dado el catálogo, cuando la persona busca por título, autor, palabra clave, área o resumen, entonces obtiene los artículos que coinciden.
3. **CA-HU-18-03 — Filtros combinados (éxito):** Dado el catálogo, cuando la persona combina filtros de área, fecha y palabra clave, entonces obtiene únicamente los artículos que cumplen todos los criterios seleccionados.
4. **CA-HU-18-04 — Resultados (éxito):** Dado un conjunto de resultados, cuando se muestran, entonces incluyen título, autores, área, fecha de publicación y palabras clave, organizados de forma paginada.
5. **CA-HU-18-05 — Sin coincidencias (error):** Dado una búsqueda sin resultados, cuando se muestra la respuesta, entonces aparece un estado vacío con un mensaje claro y la opción de limpiar los filtros.
6. **CA-HU-18-06 — Información interna (error):** Dado el catálogo, cuando se muestran resultados, entonces no aparecen evaluaciones, identidades de revisores, historial, auditoría, manuscritos en revisión, rechazados ni dados de baja.
7. **CA-HU-18-07 — Filtro inválido (error):** Dado un rango de fechas inválido, cuando la persona consulta, entonces el sistema muestra un mensaje de validación y no ejecuta la búsqueda.
8. **CA-HU-18-08 — Aceptación reciente (caso límite):** Dado un manuscrito recién aceptado, cuando transcurren cinco minutos, entonces ya aparece en el catálogo.
9. **CA-HU-18-09 — Baja posterior (caso límite):** Dado un artículo aceptado que luego se da de baja, cuando transcurren cinco minutos, entonces deja de aparecer en el catálogo.
10. **CA-HU-18-10 — Búsqueda amplia (caso límite):** Dado un criterio muy amplio, cuando se consulta, entonces los resultados se paginan y no se expone información fuera del catálogo.

---

#### HU-19 — Consultar ficha pública de un artículo aceptado

**Prioridad:** P3  
**Trazabilidad:** RF-13; RN-14, RN-20.

**Como** miembro del público, **quiero** consultar la ficha de un artículo aceptado y acceder a su documento aprobado, **para** comprender su contenido y utilizarlo como referencia académica.

**Criterios de aceptación**

1. **CA-HU-19-01 — Ficha pública (éxito):** Dado un artículo aceptado, cuando la persona abre su ficha, entonces ve título, autores, filiaciones, resumen, palabras clave, área, fecha de publicación y versión aceptada.
2. **CA-HU-19-02 — Documento aprobado (éxito):** Dado un artículo aceptado, cuando la persona consulta o descarga el documento, entonces recibe el PDF de la versión aceptada.
3. **CA-HU-19-03 — Solo artículos aceptados (error):** Dado un manuscrito en Borrador, Enviado, En Revisión, Rechazado o dado de baja, cuando se intenta acceder a su ficha pública, entonces el sistema no lo muestra e informa que no está disponible.
4. **CA-HU-19-04 — Información interna (error):** Dado la ficha pública, cuando se muestra, entonces no incluye evaluaciones, comentarios de revisores, identidades de revisores, historial de versiones ni datos de auditoría.
5. **CA-HU-19-05 — Baja posterior (caso límite):** Dado un artículo aceptado que luego se da de baja, cuando la persona intenta abrir su ficha, entonces el sistema informa que ya no está disponible.
6. **CA-HU-19-06 — Documento no disponible (error):** Dado un artículo aceptado cuyo PDF no puede recuperarse, cuando la persona consulta la ficha, entonces el sistema muestra los metadatos públicos, informa que el documento no está disponible temporalmente y registra el incidente.
7. **CA-HU-19-07 — Acceso directo (caso límite):** Dado un identificador de artículo no aceptado, cuando la persona intenta acceder directamente, entonces el sistema no revela información interna ni la existencia del manuscrito.
8. **CA-HU-19-08 — Sin inicio de sesión (éxito):** Dado cualquier miembro del público, cuando consulta la ficha, entonces no se le exige autenticarse.

---

#### HU-20 — Registrar auditoría inmutable de acciones críticas

**Prioridad:** P1  
**Trazabilidad:** RF-08; RN-13, RN-18.

**Como** Administrador, **quiero** que el sistema registre automáticamente las acciones críticas en un registro inmutable, **para** disponer de evidencia verificable y detectar incidentes.

**Criterios de aceptación**

1. **CA-HU-20-01 — Registro automático (éxito):** Dado un inicio de sesión exitoso o fallido, un cambio de estado, una asignación, una revocación, una evaluación, un veredicto, una solicitud de correcciones, una carga o descarga de versión, una edición de metadatos en Requiere Correcciones, una baja lógica o una publicación en catálogo, cuando ocurre, entonces el sistema crea un registro de auditoría.
2. **CA-HU-20-02 — Contenido del registro (éxito):** Dado un evento crítico, cuando se registra, entonces incluye identificador único, fecha y hora, actor, rol, acción, entidad afectada, resultado y motivo cuando corresponda.
3. **CA-HU-20-03 — Inmutabilidad (éxito):** Dado un registro de auditoría existente, cuando cualquier persona intenta modificarlo o eliminarlo, entonces el sistema deniega la operación y registra el intento.
4. **CA-HU-20-04 — Falla de auditoría (error):** Dado un evento crítico, cuando no es posible registrar su auditoría, entonces la acción no se completa y el usuario recibe un mensaje claro; no se produce un cambio parcial.
5. **CA-HU-20-05 — Sin contenido sensible (éxito):** Dado un registro de auditoría, cuando se consulta, entonces no contiene el contenido del manuscrito, comentarios completos de evaluación ni datos personales innecesarios.
6. **CA-HU-20-06 — Acceso indebido (error):** Dado un usuario que no es Administrador, cuando intenta consultar o alterar la auditoría, entonces el sistema deniega el acceso y registra el intento.
7. **CA-HU-20-07 — Auditoría no disponible (error):** Dado que el registro de auditoría no está disponible, cuando se intenta una acción crítica, entonces el sistema la bloquea con un mensaje claro y no pierde el evento de forma silenciosa.
8. **CA-HU-20-08 — Intento fallido de acceso (caso límite):** Dado un inicio de sesión fallido, cuando se registra, entonces se conserva el identificador intentado y el resultado, pero nunca la contraseña.
9. **CA-HU-20-09 — Consulta de auditoría (caso límite):** Dado un acceso al registro de auditoría, cuando se realiza, entonces el propio acceso queda registrado.
10. **CA-HU-20-10 — Conservación (caso límite):** Dado un registro de auditoría, cuando transcurre el periodo de conservación institucional, entonces se aplica la política definida y no se elimina durante la operación normal.

---

#### HU-21 — Consultar el registro de auditoría global

**Prioridad:** P2  
**Trazabilidad:** RF-11; RN-13, RN-20.

**Como** Administrador, **quiero** consultar y filtrar el registro global de auditoría, **para** verificar el cumplimiento del proceso e investigar incidentes.

**Criterios de aceptación**

1. **CA-HU-21-01 — Acceso autorizado (éxito):** Dado un Administrador autenticado, cuando consulta la auditoría, entonces ve los registros ordenados cronológicamente.
2. **CA-HU-21-02 — Filtros (éxito):** Dado el registro global, cuando el Administrador filtra por fecha, actor, acción, manuscrito o resultado, entonces obtiene únicamente los eventos que cumplen los criterios.
3. **CA-HU-21-03 — Detalle (éxito):** Dado un evento, cuando el Administrador lo abre, entonces ve actor, rol, fecha, acción, entidad afectada, resultado y motivo, sin el contenido del manuscrito.
4. **CA-HU-21-04 — Solo lectura (éxito):** Dado un registro de auditoría, cuando el Administrador lo consulta, entonces no puede editarlo ni eliminarlo.
5. **CA-HU-21-05 — Acceso registrado (éxito):** Dado un acceso a la auditoría, cuando se produce, entonces queda registrado como evento.
6. **CA-HU-21-06 — Usuario no autorizado (error):** Dado un usuario sin rol de Administrador, cuando intenta consultar la auditoría, entonces el sistema deniega el acceso y registra el intento.
7. **CA-HU-21-07 — Filtro inválido (error):** Dado un filtro mal formado, cuando el Administrador consulta, entonces el sistema muestra un mensaje de validación y no expone datos.
8. **CA-HU-21-08 — Sin resultados (caso límite):** Dado un filtro sin coincidencias, cuando se consulta, entonces aparece un estado vacío con un mensaje claro.
9. **CA-HU-21-09 — Volumen alto (caso límite):** Dado un conjunto amplio de registros, cuando se consulta, entonces los resultados se presentan paginados y ordenados.
10. **CA-HU-21-10 — Integridad (caso límite):** Dado un registro mostrado, cuando se compara con el evento original, entonces la información coincide y no ha sido alterada.

---

### Módulo 6: Trazabilidad e Historial (Versionado Completo)

#### HU-22 — Visualizar el contador de rondas de corrección

**Prioridad:** P2  
**Trazabilidad:** RF-05, RF-06, RF-10; RN-15.

**Como** Autor, Revisor o Editor con acceso a un manuscrito, **quiero** ver el contador de rondas de corrección y la versión actual, **para** entender en qué punto del proceso está el documento.

**Criterios de aceptación**

1. **CA-HU-22-01 — Visibilidad (éxito):** Dado un manuscrito, cuando el Autor, el Revisor asignado o el Editor consulta su detalle, entonces ve el contador de rondas de corrección y la versión actual.
2. **CA-HU-22-02 — Envío inicial (éxito):** Dado un manuscrito con su primera versión, cuando se consulta el contador, entonces muestra "Ronda 0" y "Versión v1".
3. **CA-HU-22-03 — Incremento (éxito):** Dado un veredicto "Requiere Correcciones", cuando se registra, entonces el contador de rondas aumenta en uno y la ronda queda abierta; cuando el Autor envíe la nueva versión, esta se asocia a esa ronda.
4. **CA-HU-22-04 — Contadores separados (éxito):** Dado el detalle del manuscrito, cuando se muestra, entonces el número de rondas y el número de versión aparecen como datos distintos y no se confunden.
5. **CA-HU-22-05 — Revisor (éxito):** Dado un Revisor asignado, cuando consulta el manuscrito, entonces ve la ronda y la versión que debe evaluar, sin datos de identidad del Autor.
6. **CA-HU-22-06 — Sin acceso (error):** Dado un usuario sin relación con el manuscrito, cuando intenta consultar el contador, entonces el sistema deniega el acceso.
7. **CA-HU-22-07 — Varias correcciones (caso límite):** Dado un manuscrito con varias correcciones, cuando se consulta, entonces el contador refleja la secuencia 1, 2, 3 y siguientes sin reiniciarse.
8. **CA-HU-22-08 — Reasignación (caso límite):** Dado un cambio de Revisor, cuando se realiza, entonces la ronda y la versión no cambian.
9. **CA-HU-22-09 — Edición de metadatos (caso límite):** Dado un cambio exclusivo de metadatos, cuando se guarda, entonces el contador de rondas y el de versiones no cambian.
10. **CA-HU-22-10 — Baja lógica (caso límite):** Dado un manuscrito dado de baja, cuando se consulta su historial, entonces el contador conserva el último valor registrado.

---

#### HU-23 — Consultar el historial inmutable de iteraciones

**Prioridad:** P2  
**Trazabilidad:** RF-10, RF-06, RF-21; RN-10, RN-15, RN-20.

**Como** Autor, Revisor o Editor con acceso a un manuscrito, **quiero** consultar un historial inmutable de cada iteración, incluyendo el PDF exacto y los metadatos tal como se enviaron, **para** auditar la evolución y resolver disputas.

**Criterios de aceptación**

1. **CA-HU-23-01 — Historial cronológico (éxito):** Dado un manuscrito, cuando un actor autorizado consulta su historial, entonces ve en orden cronológico las versiones, rondas, estados, asignaciones, evaluaciones y veredictos.
2. **CA-HU-23-02 — Instantánea por iteración (éxito):** Dado un envío formal, cuando se registra, entonces el historial conserva un registro inmutable con el PDF exacto, su sello de integridad y una copia de todos los metadatos tal como se enviaron en esa ronda.
3. **CA-HU-23-03 — Consulta del PDF (éxito):** Dado un registro de iteración, cuando un actor autorizado lo abre, entonces puede consultar o descargar el PDF exacto conservado.
4. **CA-HU-23-04 — Inmutabilidad (éxito):** Dado un registro histórico, cuando se realiza una edición o un nuevo envío, entonces el registro anterior no cambia y se agrega uno nuevo.
5. **CA-HU-23-05 — Acceso por rol (éxito):** Dado el historial, cuando lo consulta el Autor, entonces ve solo sus manuscritos; cuando lo consulta el Editor, entonces ve su ámbito; cuando lo consulta el Revisor, entonces ve solo la versión asignada y sin identidad del Autor.
6. **CA-HU-23-06 — Acceso no autorizado (error):** Dado un usuario sin permiso, cuando intenta consultar el historial, entonces el sistema deniega el acceso sin revelar la existencia del manuscrito.
7. **CA-HU-23-07 — Intento de alteración (error):** Dado un registro histórico, cuando alguien intenta editarlo o eliminarlo, entonces el sistema lo impide y registra el intento.
8. **CA-HU-23-08 — PDF no disponible (error):** Dado un registro cuyo PDF no puede recuperarse, cuando se consulta, entonces el sistema conserva el registro, muestra una alerta y no permite reemplazar el archivo.
9. **CA-HU-23-09 — Edición posterior (caso límite):** Dado un cambio de metadatos en Requiere Correcciones, cuando se guarda, entonces la instantánea anterior permanece intacta y la nueva se crea solo al enviar la siguiente versión.
10. **CA-HU-23-10 — Envío interrumpido (caso límite):** Dado un envío interrumpido, cuando se consulta el historial, entonces no aparece una iteración parcial.
11. **CA-HU-23-11 — Misma información, distinto PDF (caso límite):** Dado dos versiones con metadatos iguales pero PDF distinto, cuando se consulta el historial, entonces cada una conserva su propio PDF y su propio registro.
12. **CA-HU-23-12 — Baja lógica (caso límite):** Dado un manuscrito dado de baja, cuando un actor autorizado consulta su historial, entonces el historial y las iteraciones siguen disponibles, aunque el manuscrito no aparezca en los listados activos ni en el catálogo.

---

### Módulo Transversal: Notificaciones

#### HU-24 — Recibir notificaciones de eventos clave

**Prioridad:** P2  
**Trazabilidad:** RF-20; RN-16, RN-06, RN-20.

**Como** usuario institucional, **quiero** recibir avisos oportunos sobre los eventos que afectan mis manuscritos o evaluaciones, **para** actuar a tiempo sin revisar manualmente todos los expedientes.

**Criterios de aceptación**

1. **CA-HU-24-01 — Eventos notificados (éxito):** Dado un envío o reenvío, una asignación, una evaluación, un veredicto, una solicitud de correcciones, un vencimiento de plazo, una revocación, una reasignación o una baja lógica, cuando ocurre, entonces el sistema notifica a las personas afectadas.
2. **CA-HU-24-02 — Canales (éxito):** Dado un evento notificable, cuando se genera el aviso, entonces se envía por el canal institucional configurado y queda visible en el panel de la persona.
3. **CA-HU-24-03 — Contenido útil (éxito):** Dado un aviso, cuando se muestra, entonces incluye el evento, el código y título del manuscrito, la acción esperada, el plazo cuando corresponda y un acceso directo a la sección relacionada.
4. **CA-HU-24-04 — Doble ciego (éxito):** Dado un aviso dirigido al Revisor, cuando se muestra, entonces no contiene identidad del Autor; dado un aviso dirigido al Autor, entonces no contiene identidad del Revisor.
5. **CA-HU-24-05 — Falla de entrega (error):** Dado un fallo en el canal de notificación, cuando ocurre, entonces la acción de negocio no se revierte, el fallo se registra y el aviso queda disponible en el panel para reintento.
6. **CA-HU-24-06 — Duplicados (caso límite):** Dado un mismo evento y una misma persona, cuando se genera la notificación, entonces se produce un solo aviso, salvo que existan roles distintos que requieran acciones distintas.
7. **CA-HU-24-07 — Destinatario sin acceso (error):** Dado un destinatario que ya no tiene relación con el manuscrito, cuando se genera el aviso, entonces el sistema no le envía información interna.
8. **CA-HU-24-08 — Contenido sensible (error):** Dado un aviso, cuando se prepara, entonces no incluye comentarios confidenciales, evaluaciones completas ni datos personales innecesarios.
9. **CA-HU-24-09 — Plazo de 20 días (caso límite):** Dado un Revisor asignado, cuando recibe el aviso, entonces ve la fecha límite; dado el vencimiento, cuando se cumple, entonces el Editor recibe el aviso correspondiente.
10. **CA-HU-24-10 — Historial de avisos (éxito):** Dado un usuario, cuando consulta su panel, entonces puede ver sus avisos con estado de leído o no leído y su fecha.

---

## 10. Casos límite transversales

Además de los criterios de cada historia, el sistema debe resolver de forma consistente estos escenarios:

- **Credenciales inválidas o cuenta inactiva:** mensaje genérico, sin revelar la existencia de la cuenta, con registro del intento.
- **Bloqueo por intentos fallidos:** aviso con el tiempo de espera y registro del bloqueo.
- **Persona con varios roles:** todas las secciones visibles a la vez, sin selección de rol, con datos separados por apartado.
- **Conflicto entre roles:** si la persona es Autora y Revisora del mismo manuscrito, prevalece la prohibición de evaluarlo o decidir sobre él.
- **Rol retirado durante la sesión:** la siguiente acción se bloquea y el panel se actualiza.
- **PDF con extensión engañosa:** se valida el contenido, no solo el nombre del archivo.
- **PDF dañado, vacío, protegido o con contenido no permitido:** se rechaza sin crear versión.
- **Carga interrumpida:** no se crea una versión ni una evaluación parcial; se conserva lo anterior.
- **Envío duplicado:** solo se registra una versión o una evaluación; la segunda se rechaza como duplicada.
- **Edición concurrente de metadatos:** se detecta el conflicto y no se sobrescribe silenciosamente.
- **Edición en estado no permitido:** se bloquea y se explica el estado actual.
- **Baja lógica durante una revisión:** se cancela la asignación activa y se notifica al Revisor y al Editor.
- **Baja lógica de un artículo aceptado:** se retira del catálogo, pero el historial y la auditoría se conservan.
- **Intento de borrado físico:** se bloquea; la baja es siempre lógica.
- **Segundo Revisor:** se bloquea si ya existe uno activo; primero debe revocarse la asignación.
- **Revisor no elegible:** se bloquea por conflicto, inactividad, falta de experiencia o asignación duplicada.
- **Sin Revisor elegible:** el manuscrito queda pendiente de asignación y no admite veredicto.
- **Vencimiento de los 20 días:** se marca el plazo, se cierra el envío final y se habilita la revocación; no hay revocación automática.
- **Reasignación:** se conserva la asignación anterior y se inicia un nuevo plazo para el nuevo Revisor.
- **Veredicto sin evaluación:** se bloquea.
- **Veredicto concurrente:** solo uno se registra; el otro recibe un conflicto.
- **Veredicto ya registrado:** no se sobrescribe; cualquier cambio requiere una nueva decisión auditada.
- **Falla de auditoría:** la acción crítica no se completa.
- **Intento de alterar auditoría o historial:** se bloquea y se registra.
- **Fuga de identidad en una vista, aviso o descarga:** se bloquea o se sanitiza, se registra el incidente y se protege a la persona afectada.
- **Manuscrito con baja lógica:** desaparece de listados activos y catálogo, pero su historial sigue disponible para roles autorizados.
- **Catálogo sin resultados:** estado vacío con opción de limpiar filtros.
- **Artículo aceptado recién publicado:** aparece en el catálogo en un máximo de cinco minutos.
- **Artículo aceptado que se da de baja:** desaparece del catálogo en un máximo de cinco minutos.
- **Falla de notificación:** no revierte la acción; el aviso queda en el panel y se reintenta.
- **Acceso público a información interna:** se bloquea y se redirige al catálogo o al inicio de sesión.

---

## 11. Cobertura de requisitos funcionales (RF-01 a RF-22)

| RF | Requisito funcional | Historias que lo cubren | Estado |
|---|---|---|---|
| **RF-01** | Autenticación mediante credenciales institucionales. | HU-01 | Cubierto |
| **RF-02** | Registro de manuscrito con metadatos obligatorios y PDF adjunto. | HU-04 | Cubierto |
| **RF-03** | Asignación de Revisor autorizado por parte del Editor. | HU-11, HU-12 | Cubierto con la regla vigente de **un único Revisor activo**. |
| **RF-04** | Registro de evaluación con observaciones y recomendación. | HU-14, HU-15, HU-16 | Cubierto |
| **RF-05** | Consulta de estado de manuscritos y tareas pendientes por parte del Autor. | HU-06, HU-22 | Cubierto |
| **RF-06** | Envío de nueva versión únicamente en estado Requiere Correcciones. | HU-09, HU-22, HU-23 | Cubierto |
| **RF-07** | Cierre del proceso y emisión de veredicto por parte del Editor. | HU-13 | Cubierto |
| **RF-08** | Generación automática de registros de auditoría para acciones críticas. | HU-20 | Cubierto |
| **RF-09** | Consulta de evaluaciones registradas por parte del Revisor. | HU-17 | Cubierto |
| **RF-10** | Consulta del historial de revisiones, estados y decisiones por parte del Editor. | HU-22, HU-23 | Cubierto |
| **RF-11** | Consulta del registro de auditoría global por parte del Administrador. | HU-21 | Cubierto |
| **RF-12** | Selección de perfil para docentes autenticados. | HU-02 | Cubierto mediante **panel unificado sin selección inicial**: la persona ve simultáneamente sus perfiles. |
| **RF-13** | Búsqueda y consulta de artículos en el catálogo mediante filtros. | HU-18, HU-19 | Cubierto con catálogo **público**. |
| **RF-14** | Restricción estricta de formato de archivo adjunto únicamente a PDF. | HU-05 | Cubierto |
| **RF-15** | Solicitud formal de correcciones y envío de observaciones al Autor. | HU-13 | Cubierto |
| **RF-16** | Control de acceso y restricciones de operación por rol. | HU-03, HU-01, HU-02 | Cubierto |
| **RF-17** | Visualización de nuevos envíos y cambio de estado a En Revisión. | HU-10 | Cubierto |
| **RF-18** | Formulario de evaluación estructurado para la recomendación del Revisor. | HU-14, HU-15 | Cubierto |
| **RF-19** | Registro de veredicto final: Aceptado, Rechazado o Requiere Correcciones. | HU-13 | Cubierto |
| **RF-20** | Notificaciones automáticas ante eventos clave. | HU-24 | Cubierto |
| **RF-21** | Edición de metadatos por el Autor en Borrador o Requiere Correcciones. | HU-07, HU-23 | Cubierto |
| **RF-22** | Eliminación lógica del manuscrito mediante la marca "Dado de baja". | HU-08 | Cubierto |

**Resultado de cobertura:** 22 de 22 requisitos funcionales cubiertos por al menos una historia de usuario con criterios de aceptación verificables.

---

## 12. Criterios de éxito medibles

| Código | Resultado esperado | Verificación |
|---|---|---|
| **SC-01** | El 100% de las personas con más de un perfil ve todos sus apartados inmediatamente después de iniciar sesión, sin un paso obligatorio de selección de rol. | Prueba de aceptación con usuarios Autor/Revisor y Autor/Revisor/Editor. |
| **SC-02** | Al menos el 95% de los Autores completa un envío válido en menos de 10 minutos en su primer intento. | Prueba de usabilidad con usuarios representativos. |
| **SC-03** | El 100% de los archivos inválidos se rechaza antes de crear una versión. | Batería de archivos inválidos: formato, contenido, tamaño, protección y daño. |
| **SC-04** | El 100% de los artículos aceptados aparece en el catálogo público en un máximo de cinco minutos; ningún manuscrito no aceptado es visible. | Revisión del catálogo después de cada veredicto y muestreo de estados. |
| **SC-05** | El 100% de las vistas, avisos y descargas dirigidas al Revisor contiene cero datos de identidad del Autor. | Prueba de doble ciego sobre todos los canales. |
| **SC-06** | El 100% de los manuscritos tiene como máximo un Revisor activo; se registran cero asignaciones paralelas. | Revisión de asignaciones y prueba de intento de segundo Revisor. |
| **SC-07** | El 100% de las asignaciones se marca como vencida exactamente a los 20 días; se registran cero revocaciones automáticas. | Prueba con fechas controladas y revisión de registros. |
| **SC-08** | El 100% de los veredictos cuenta con una evaluación final; se registran cero veredictos sin evaluación. | Prueba de intento de veredicto sin evaluación. |
| **SC-09** | El 100% de las versiones e iteraciones conserva el PDF exacto y los metadatos originales; se registran cero sobrescrituras. | Comparación de PDF y metadatos antes y después de nuevas iteraciones. |
| **SC-10** | El 100% de las acciones críticas genera un registro de auditoría en menos de cinco segundos; se registran cero modificaciones o eliminaciones exitosas. | Prueba de acciones críticas e intentos de alteración. |
| **SC-11** | Al menos el 95% de las búsquedas del catálogo responde en menos de dos segundos con 50 personas concurrentes. | Prueba de carga controlada. |
| **SC-12** | Al menos el 90% de los Revisores completa el formulario de evaluación en menos de 15 minutos. | Prueba de usabilidad con revisores. |
| **SC-13** | El 100% de los manuscritos muestra un contador de rondas coherente con su historial y su número de versión. | Revisión de expedientes con 0, 1, 2 y más correcciones. |
| **SC-14** | El 100% de las notificaciones de eventos clave se entrega o queda visible en el panel en menos de cinco minutos; se registran cero fugas de identidad. | Prueba de eventos y revisión de contenido de avisos. |
| **SC-15** | El 100% de los intentos de acceso no autorizado se deniega y se registra. | Prueba de acceso por rol y por objeto. |

---

## 13. Supuestos

1. **Cuentas institucionales:** las cuentas son creadas y administradas por la institución. No existe autorregistro ni recuperación de acceso dentro de esta especificación.
2. **Roles:** los roles Autor, Revisor, Editor y Administrador son asignados por la institución. La gestión del ciclo de vida de las cuentas y de los roles se asume como una función administrativa existente.
3. **Multirrol:** una misma persona puede tener varios roles. Los permisos son aditivos y el panel unificado los muestra simultáneamente.
4. **Revisores:** el registro institucional de Revisores incluye sus áreas de experiencia y su estado activo o inactivo.
5. **Metadatos mínimos:** título, resumen, palabras clave, área de conocimiento, idioma, autores con filiación y contacto del autor responsable.
6. **Tamaño máximo de PDF:** se define por la institución y se muestra antes de la carga. Se propone un valor inicial de 50 MB, ajustable.
7. **Plazo de evaluación:** 20 días calendario continuos, contados desde el instante de la asignación, en la zona horaria institucional. Al cumplirse el instante exacto, el envío final de la evaluación se cierra y el Editor puede revocar y reasignar; no existe revocación automática.
8. **Un solo Revisor:** no se permiten evaluaciones paralelas ni paneles de varios revisores en esta versión.
9. **Aceptación y catálogo:** el estado Aceptado habilita directamente la aparición en el catálogo público; no existe un paso separado de publicación.
10. **Catálogo público:** no exige inicio de sesión. Solo muestra artículos aceptados y no dados de baja.
11. **Notificaciones:** se utiliza el canal institucional configurado (correo institucional) y un panel de avisos. No se incluyen otros canales.
12. **Sesión:** el tiempo de inactividad y el límite de intentos fallidos son parámetros institucionales. Se propone que, tras cinco intentos fallidos en una ventana de quince minutos, el acceso se bloquee durante quince minutos.
13. **Evaluación:** la recomendación del Revisor es técnica y no vinculante; el Editor decide y debe justificar cuando se aparta de ella.
14. **Baja lógica:** un artículo aceptado dado de baja se retira del catálogo, pero no se borra de la historia institucional.
15. **Conservación:** las versiones, el historial y la auditoría se conservan según la política institucional y no se eliminan durante la operación normal.
16. **Autores:** el Autor que registra debe figurar como autor o coautor del manuscrito.
17. **Experiencia del Revisor:** la correspondencia entre el área del manuscrito y la experiencia del Revisor se valida con la información declarada en su perfil institucional.
18. **Idioma:** la interfaz y los mensajes se presentan en español institucional.

---

## 14. Fuera de alcance

- Ranking automatizado de Revisores y penalizaciones automáticas por incumplimiento (se propone para Fase 2).
- Evaluación por más de un Revisor o evaluación paralela.
- Selección de rol inicial o cambio de rol dentro de una misma sesión.
- Acceso público a manuscritos no aceptados, evaluaciones, historial o auditoría.
- Edición o eliminación de versiones, del historial o de la auditoría.
- Borrado físico de manuscritos.
- Restauración de manuscritos dados de baja.
- Retractación formal, apelaciones o sanciones distintas de la baja lógica.
- Integración con índices académicos, repositorios externos, identificadores persistentes, servicios de similitud o pagos.
- Gestión avanzada de coautoría, invitaciones, firma de autoría o conflictos de autoría distintos de la validación básica.
- Paneles analíticos, reportes estadísticos avanzados o exportaciones masivas.
- Notificaciones por canales distintos al institucional.
- Automatización de la revocación o reasignación: siempre requiere decisión del Editor.

---

## 15. Dependencias

- **Validación de identidad institucional:** mecanismo institucional que confirma que las credenciales pertenecen a una cuenta activa.
- **Canal institucional de notificaciones:** medio oficial para enviar los avisos y registrar su entrega o fallo.
- **Registro institucional de Revisores:** información actualizada sobre áreas de experiencia y estado de cada Revisor.
- **Políticas institucionales:** roles, metadatos obligatorios, tamaño máximo de PDF, tiempos de sesión, conservación documental y zona horaria.
- **Disponibilidad de Editores y Revisores:** el flujo requiere personas autorizadas para operar cada etapa.
- **Capacidad de conservación:** espacio y mecanismos institucionales para preservar todas las versiones, el historial y la auditoría sin sobrescritura.
- **Definición de la política de baja lógica:** criterios institucionales para el retiro de artículos aceptados y su comunicación.

---

## 16. Sección Especial: Recomendaciones a Futuro (Fase 2)

### 16.1 Contexto

En la Fase 1, el incumplimiento del plazo de 20 días se registra y el Editor decide si revoca y reasigna. No existe una sanción automática ni un ranking de Revisores. La Fase 2 propone incorporar un **Sistema automatizado de ranking de Revisores** que reconozca el cumplimiento y penalice la visibilidad de quienes ignoran reiteradamente el plazo, sin afectar la imparcialidad del proceso ni la dignidad de las personas.

### 16.2 Objetivos de la propuesta

1. Incentivar la evaluación oportuna.
2. Ayudar al Editor a elegir Revisores confiables.
3. Reconocer a quienes cumplen con calidad y puntualidad.
4. Reducir los cuellos de botella por inactividad.
5. Mantener decisiones humanas y mecanismos de apelación.

### 16.3 Modelo propuesto

El ranking podría construirse con estos componentes, siempre configurables por la institución:

- **Cumplimiento:** proporción de evaluaciones entregadas dentro de los 20 días.
- **Puntualidad:** tiempo medio de respuesta.
- **Calidad:** valoración del Editor sobre la utilidad y profundidad de la evaluación.
- **Disponibilidad:** respuesta a las asignaciones y declaración oportuna de conflictos.
- **Historial:** número de asignaciones revocadas por inactividad.
- **Excepciones justificadas:** ausencias institucionales, salud, fuerza mayor u otras causas aprobadas.

**Efecto de la penalización:** reducir la visibilidad y la prioridad del Revisor en las listas de sugerencias del Editor. No implica eliminar la cuenta, ocultar su identidad públicamente ni impedirle evaluar. El Editor conserva la posibilidad de asignarle un manuscrito con justificación.

**Salvaguardas:** transparencia del cálculo, acceso del Revisor a su propia puntuación y motivos, apelación, revisión humana, recálculo periódico y exclusión de causas justificadas.

### 16.4 Historia de usuario futura (no implementar en Fase 1)

**Prioridad:** Fase 2 — fuera del alcance actual  
**Trazabilidad:** propuesta de evolución de RN-05 y RF-03.

**Como** Editor, **quiero** disponer en una fase futura de un ranking automatizado de Revisores que refleje su cumplimiento y calidad, **para** priorizar a quienes evalúan a tiempo y desalentar el incumplimiento reiterado del plazo de 20 días.

**Criterios de aceptación futuros (sujetos a validación institucional)**

1. **CA-F2-01 — Cálculo transparente:** Dado un conjunto de asignaciones y evaluaciones, cuando se calcula el ranking, entonces cada Revisor recibe una puntuación con dimensiones de cumplimiento, puntualidad, calidad y disponibilidad, y puede consultar los motivos.
2. **CA-F2-02 — Penalización de visibilidad:** Dado un Revisor con incumplimientos reiterados del plazo de 20 días, cuando el Editor consulta las sugerencias, entonces el Revisor aparece con menor prioridad, sin que su cuenta sea eliminada ni su identidad expuesta públicamente.
3. **CA-F2-03 — Excepciones justificadas:** Dado un incumplimiento con causa institucional justificada, cuando se registra y aprueba, entonces no afecta la puntuación del Revisor.
4. **CA-F2-04 — Decisión humana:** Dado un ranking, cuando el Editor asigna un manuscrito, entonces puede elegir a otra persona con una justificación registrada; el ranking no decide automáticamente.
5. **CA-F2-05 — Apelación:** Dado un Revisor que considera incorrecta su puntuación, cuando solicita revisión, entonces puede presentar una apelación y obtener una respuesta trazable.
6. **CA-F2-06 — Sin efecto sobre Autores:** Dado un ranking de Revisores, cuando se calcula, entonces no altera el estado, la visibilidad ni la evaluación de los manuscritos de los Autores.
7. **CA-F2-07 — Privacidad:** Dado el ranking, cuando se consulta, entonces solo el Editor y el propio Revisor acceden a la puntuación detallada; el público no lo ve.
8. **CA-F2-08 — Recálculo y auditoría:** Dado un periodo definido, cuando se actualiza el ranking, entonces el recálculo queda registrado y no modifica retroactivamente las evaluaciones históricas.

### 16.5 Condiciones para iniciar la Fase 2

- Validación del modelo con la institución y con los Revisores.
- Definición de pesos, periodicidad y causas justificadas.
- Mecanismo de apelación y revisión humana.
- Evaluación de impacto sobre la carga de trabajo y la equidad.
- Aprobación formal antes de cualquier implementación.

---

## 17. Aprobación y siguiente paso

| Rol | Nombre | Aprobación | Fecha |
|---|---|---|---|
| Responsable funcional |  |  |  |
| Representante de Autores |  |  |  |
| Representante de Revisores |  |  |  |
| Representante de Editores |  |  |  |
| Administrador del sistema |  |  |  |

**Estado de la especificación:** completa para los 22 requisitos funcionales, con historias de usuario y criterios de aceptación verificables.  
**Siguiente paso metodológico:** revisión de claridad con los actores y elaboración del plan de implementación.  
**Nota:** este documento no define tecnologías, productos, arquitecturas ni mecanismos de implementación; cualquier decisión de ese tipo corresponde a la etapa de planificación.

