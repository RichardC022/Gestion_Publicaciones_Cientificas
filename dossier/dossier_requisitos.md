# Dossier de Requisitos y Matriz de Trazabilidad (AA 2)

**Universidad Nacional de Loja**  
**Facultad de la Energía, las Industrias y los Recursos Naturales No Renovables**  
**Carrera de Computación**  

* **Asignatura:** Desarrollo Basado en Plataformas (Ciclo 5 A)  
* **Docente:** Edison Leonardo Coronel Romero  
* **Proyecto:** Plataforma Web para la Gestión del Flujo Editorial de Artículos Científicos (UNL)  
* **Integrantes:**  
  * Jostin Vasquez (Coordinador)  
  * Richard Cajas (Repositorio y Configuración)  
  * Gyna Yupanqui (Diseño y Vistas)  
  * Miguel Veintimilla (Base de Datos y Pruebas)  
  * Ismael González (Documentación SDD)  
* **Fecha:** Octubre 2026  

---

## 1. Identificación del Proyecto
* **Nombre del Sistema:** Plataforma Web de Flujo Editorial de Artículos Científicos UNL.
* **Módulo / Ámbito:** Gestión integral del ciclo de vida de manuscritos académicos (recepción, evaluación por pares doble ciego, gestión de versiones corregidas, veredicto editorial y catálogo público de consulta).

---

## 2. Síntesis del Problema
Las facultades de la Universidad Nacional de Loja (UNL) carecen de un sistema estandarizado y centralizado para gestionar la revisión y aprobación de artículos científicos elaborados por docentes y estudiantes. Actualmente, las versiones de los borradores, las correcciones dictadas por los evaluadores y las aprobaciones finales se manejan de manera informal mediante correos electrónicos dispersos. 

Esta falta de centralización genera cuellos de botella en la gestión, pérdida del historial de versiones y revisiones, vulneración del anonimato en la evaluación por pares (doble ciego) y dificultades significativas para realizar el seguimiento del estado editorial de los manuscritos. Se requiere una plataforma web moderna e integrada que automatice el flujo editorial, garantice la trazabilidad de las acciones y asegure la calidad necesaria para la publicación académica.

---

## 3. Actores Principales
* **Autor:** Estudiante o docente de la UNL que registra manuscritos, adjunta archivos PDF, sube versiones corregidas y consulta el estado de sus envíos.
* **Revisor (Docente):** Evaluador autorizado que examina anónimamente los manuscritos asignados, completa formularios de evaluación y emite recomendaciones técnicas.
* **Editor:** Responsable de supervisar el flujo editorial, asignar revisores, solicitar correcciones a los autores, cerrar evaluaciones y registrar el veredicto final.
* **Administrador:** Encargado de administrar cuentas, roles y permisos en la plataforma, además de consultar las bitácoras de auditoría de eventos críticos.
* **Público / Usuario General:** Lector que accede al catálogo público de artículos aprobados para realizar búsquedas e investigaciones.

---

## 4. Fuentes Consultadas

### A. Fuentes Técnicas (Estándares)
1. **RFC 9110 — HTTP Semantics:**
   * **Métodos HTTP:** Empleo de `GET` para lectura idempotente del catálogo e historial; `POST` para creación de recursos (inicio de sesión, subida de archivos, creación de borradores); `PUT`/`PATCH` para actualización de datos y versiones; y `DELETE` para eliminación lógica.
   * **Códigos de Estado HTTP:** `200 OK` (operación exitosa), `201 Created` (recurso creado), `400 Bad Request` (petición inválida / formato no PDF), `401 Unauthorized` (fallo de autenticación), `403 Forbidden` (permisos insuficientes por rol), y `500 Internal Server Error` (error interno no expuesto).
   * **Seguridad y Cabeceras:** Uso de la cabecera `Authorization` para transmisión de tokens JWT y `Content-Type` para el manejo de JSON y archivos PDF.

### B. Fuentes del Dominio Institucional
2. **Reglamento de Investigación y Publicaciones de la UNL:** Marco de referencia para el flujo editorial, tiempos de evaluación y protección del proceso de revisión por pares a ciegas.
3. **Especificación del Proyecto (ACD 1 / ACD 2 / APE 2):** Documentación técnica inicial y mapa de actores estructurado previamente por el equipo.

---

## 5. Historias de Usuario Depuradas

### HU-001: Inicio de Sesión
* **Como:** Usuario del sistema (Administrador, Editor, Revisor, Autor).
* **Quiero:** Ingresar mis credenciales institucionales en la pantalla de inicio de sesión.
* **Para:** Acceder de forma segura a las funcionalidades correspondientes a mi rol asignado.

### HU-002: Registro de Manuscrito
* **Como:** Autor.
* **Quiero:** Registrar mi manuscrito ingresando los metadatos obligatorios y adjuntando el documento principal.
* **Para:** Iniciar formalmente el proceso de revisión editorial en la plataforma.

### HU-012: Validación del Archivo PDF
* **Como:** Autor.
* **Quiero:** Que el sistema valide que el archivo adjunto sea exclusivamente en formato PDF y cumpla con las restricciones de tamaño.
* **Para:** Asegurar que el documento cumple con los estándares técnicos antes de enviarlo a revisión.

---

## 6. Requisitos Funcionales (RF)
* **RF-01:** Autenticación de usuarios mediante credenciales institucionales.
* **RF-02:** Registro de manuscrito con metadatos obligatorios y archivo PDF adjunto.
* **RF-03:** Asignación de uno o más revisores autorizados por parte del Editor.
* **RF-04:** Registro de evaluación con observaciones y recomendación por parte del Revisor.
* **RF-05:** Consulta de estado de manuscritos y tareas pendientes por parte del Autor.
* **RF-06:** Subida de nueva versión del manuscrito únicamente en estado "Requiere Correcciones".
* **RF-07:** Cierre del proceso de evaluación y emisión de veredicto por parte del Editor.
* **RF-08:** Generación automática de registros de auditoría para acciones críticas.
* **RF-09:** Consulta de evaluaciones registradas por parte del Revisor.
* **RF-10:** Consulta del historial de revisiones, estados y decisiones por parte del Editor.
* **RF-11:** Consulta del registro de auditoría global por parte del Administrador.
* **RF-12:** Selección de perfil (Autor/Revisor) para docentes autenticados.
* **RF-13:** Búsqueda y consulta de artículos en el catálogo público mediante filtros.
* **RF-14:** Restricción estricta de formato de archivo adjunto únicamente a PDF.
* **RF-15:** Solicitud formal de correcciones y envío de observaciones al Autor por parte del Editor.
* **RF-16:** Control de acceso y restricciones de operación por rol en frontend y backend.
* **RF-17:** Visualización de nuevos envíos y cambio automático de estado a "En Revisión".
* **RF-18:** Formulario de evaluación estructurado para la recomendación del Revisor.
* **RF-19:** Registro de veredicto final (Aceptado, Rechazado o Requiere Correcciones).
* **RF-20:** Envío de notificaciones automáticas por correo electrónico ante eventos clave.
* **RF-21:** Edición de metadatos por el Autor en estados "Borrador" o "Requiere Corrección".
* **RF-22:** Eliminación lógica de manuscritos mediante el cambio de estado a "Dado de baja".

---

## 7. Requisitos No Funcionales (RNF)
* **RNF-01 (Rendimiento):** Soporte de al menos 50 usuarios concurrentes, manteniendo un percentil 95 de tiempo de respuesta $\le$ 2 segundos y tasa de éxito $\ge$ 95%.
* **RNF-02 (Integridad y Seguridad):** Validación de datos de entrada en backend, control de acceso por endpoint y restricciones de integridad en la base de datos.
* **RNF-03 (Compatibilidad):** Interfaz compatible con las dos versiones estables más recientes de Chrome, Firefox y Edge.
* **RNF-04 (Usabilidad):** Identificación visual de campos obligatorios, validación activa y mensajes de error guiados.
* **RNF-05 (Almacenamiento Persistente):** Almacenamiento inalterable de archivos PDF con identificador único de versión, evitando la sobrescritura.
* **RNF-06 (Cifrado de Comunicaciones):** Uso obligatorio de protocolo HTTPS en entornos desplegados y cifrado de credenciales.
* **RNF-07 (Privacidad / Doble Ciego):** Ocultamiento estricto de los datos del Autor en las respuestas de la API destinadas al Revisor.
* **RNF-08 (Inalterabilidad de Auditoría):** Registros de auditoría protegidos contra modificación o eliminación por usuarios ordinarios.
* **RNF-09 (Manejo de Errores):** Respuestas de error estandarizadas en la API utilizando códigos HTTP apropiados sin exponer trazas internas.

---

## 8. Criterios de Aceptación (Formato BDD)

### CA-HU001.1 (Autenticación Exitosa)
* **Dado** que un usuario ingresa sus credenciales institucionales válidas y su cuenta está activa,
* **Cuando** solicita iniciar sesión,
* **Entonces** el sistema valida la información, crea la sesión autenticada y responde HTTP `200 OK` cargando los permisos del rol.

### CA-HU001.2 (Credenciales Inválidas)
* **Dado** que un usuario ingresa credenciales incorrectas o inhabilitadas,
* **Cuando** solicita iniciar sesión,
* **Entonces** el sistema rechaza el acceso, devuelve un código HTTP `401 Unauthorized` y muestra un mensaje de error claro.

### CA-HU012.1 (Validación de Archivo Correcto)
* **Dado** que el Autor selecciona un archivo en formato PDF cuyo tamaño respeta el límite establecido,
* **Cuando** adjunta el documento a la solicitud,
* **Entonces** el sistema lo acepta, habilita la confirmación del envío y permite continuar el registro.

### CA-HU012.2 (Rechazo de Formato Inválido)
* **Dado** que el Autor intenta subir un archivo en un formato distinto a PDF (ej. `.docx`, `.png`),
* **Cuando** ejecuta la carga,
* **Entonces** el sistema rechaza la solicitud con HTTP `400 Bad Request`, informando que solo se admiten archivos PDF.

---

## 9. Matriz de Trazabilidad Inicial

### A. Requisitos Funcionales (RF-01 al RF-22)

| ID | Actor | Necesidad | Historia / Requisito | Criterio de Aceptación (Dado / Cuando / Entonces) | Fuente / Referencia | Estado |
|---|---|---|---|---|---|---|
| **RF-01** | Todos | Acceder de forma segura a la plataforma | RF-01: Autenticación mediante credenciales institucionales | **Dado** credenciales válidas y cuenta activa, **cuando** el usuario inicia sesión, **entonces** el sistema otorga acceso con HTTP `200 OK` y carga sus permisos. | RFC 9110 (Sec. 11) & Reglamento UNL | Validado |
| **RF-02** | Autor | Iniciar el proceso de evaluación de un artículo | RF-02: Registro de manuscrito con metadatos y PDF | **Dado** metadatos obligatorios y un archivo PDF válido, **cuando** el autor envía la solicitud, **entonces** el sistema crea el registro y responde HTTP `201 Created`. | Proceso Editorial UNL & RFC 9110 (Sec. 9.3.4) | Validado |
| **RF-03** | Editor | Asignar evaluadores pares a los artículos | RF-03: Asignación de revisores autorizados | **Dado** un manuscrito en estado "Recibido", **cuando** el editor asigna revisores, **entonces** el sistema guarda las asignaciones con HTTP `200 OK`. | Reglamento de Publicaciones UNL | Validado |
| **RF-04** | Revisor | Registrar el dictamen técnico de un trabajo | RF-04: Registro de evaluación y recomendación | **Dado** un manuscrito asignado, **cuando** el revisor completa la evaluación, **entonces** el sistema guarda el dictamen con HTTP `201 Created`. | Reglamento de Investigaciones UNL | Validado |
| **RF-05** | Autor | Monitorear el progreso de sus envíos | RF-05: Consulta de estado de manuscritos propios | **Dado** un autor autenticado, **cuando** consulta su panel de control, **entonces** el sistema lista sus manuscritos y acciones pendientes con HTTP `200 OK`. | Portal Institucional UNL & RFC 9110 (Sec. 9.3.1) | Validado |
| **RF-06** | Autor | Subir los cambios solicitados por los pares | RF-06: Carga de nueva versión del manuscrito | **Dado** el estado "Requiere Correcciones", **cuando** el autor sube el documento corregido, **entonces** el sistema guarda la nueva versión sin sobrescribir la anterior. | Especificación APE 2 & RFC 9110 (Sec. 9.3.4) | Validado |
| **RF-07** | Editor | Finalizar la fase de evaluación técnica | RF-07: Cierre del proceso y emisión de veredicto | **Dado** al menos una evaluación registrada, **cuando** el editor cierra el proceso, **entonces** el sistema emite el veredicto final con HTTP `200 OK`. | Manual Proceso Editorial UNL | Validado |
| **RF-08** | Administrador | Auditar eventos críticos en la plataforma | RF-08: Registro de auditoría de acciones críticas | **Dado** un evento crítico (inicio de sesión, veredicto, cambio de estado), **cuando** ocurre, **entonces** el sistema crea un registro inalterable. | Estándar de Seguridad IT & RNF-08 | Validado |
| **RF-09** | Revisor | Consultar el historial de dictámenes realizados | RF-09: Consulta de evaluaciones registradas | **Dado** un revisor autenticado, **cuando** accede a su historial, **entonces** el sistema muestra sus evaluaciones enviadas con HTTP `200 OK`. | Reglamento de Publicaciones UNL | Validado |
| **RF-10** | Editor | Analizar la trazabilidad de los artículos | RF-10: Consulta del historial de revisiones y estados | **Dado** un editor con manuscritos asignados, **cuando** consulta el historial de un manuscrito, **entonces** la API retorna el desglose de cambios con HTTP `200 OK`. | Manual Proceso Editorial UNL | Validado |
| **RF-11** | Administrador | Controlar la integridad operacional | RF-11: Consulta del registro de auditoría global | **Dado** un administrador autenticado, **cuando** solicita la bitácora de auditoría, **entonces** el sistema la retorna ordenada cronológicamente con HTTP `200 OK`. | Políticas de Seguridad UNL | Validado |
| **RF-12** | Docente | Desempeñar múltiples perfiles dentro del flujo | RF-12: Selección de rol (Autor / Revisor) para docentes | **Dado** un docente autorizado, **cuando** se autentica y selecciona un rol, **entonces** el sistema habilita las funciones de dicho perfil. | Estatuto Orgánico UNL | Validado |
| **RF-13** | Público | Localizar e investigar manuscritos aprobados | RF-13: Búsqueda y consulta en el catálogo | **Dado** un término de búsqueda o filtro, **cuando** el usuario consulta el catálogo, **entonces** el sistema retorna los artículos coincidentes con HTTP `200 OK`. | Portal de Publicaciones UNL & RFC 9110 (Sec. 9.3.1) | Validado |
| **RF-14** | Autor / Sistema | Asegurar la compatibilidad del formato del archivo | RF-14: Restricción estricta a formato PDF | **Dado** un archivo adjunto, **cuando** el sistema valida que no es formato PDF, **entonces** rechaza el envío con HTTP `400 Bad Request`. | HU-012 & RFC 9110 (Sec. 8.4) | Validado |
| **RF-15** | Editor | Comunicar la retroalimentación al autor | RF-15: Solicitud de correcciones y notificación de observaciones | **Dado** un manuscrito evaluado, **cuando** el editor solicita correcciones, **entonces** el sistema cambia el estado y notifica al autor con el detalle. | Reglamento de Publicaciones UNL | Validado |
| **RF-16** | Sistema / Todos | Prevenir accesos no autorizados | RF-16: Control de acceso por roles en interfaz y backend | **Dado** una solicitud a un endpoint protegido, **cuando** el rol del usuario no tiene permisos, **entonces** el backend responde HTTP `403 Forbidden`. | RFC 9110 (Sec. 11.1) & RNF-02 | Validado |
| **RF-17** | Editor | Distribuir manuscritos nuevos entre docentes | RF-17: Visualización de nuevos envíos y cambio a "En Revisión" | **Dado** un manuscrito en "Recibido", **cuando** el editor asigna revisores, **entonces** el estado cambia automáticamente a "En Revisión". | Manual Proceso Editorial UNL | Validado |
| **RF-18** | Revisor | Estructurar la evaluación técnica | RF-18: Formulario de evaluación y recomendación | **Dado** un revisor asignado, **cuando** completa el formulario de evaluación y emite su recomendación, **entonces** el sistema la registra correctamente. | Reglamento de Publicaciones UNL | Validado |
| **RF-19** | Editor | Formalizar el resultado de la revisión | RF-19: Registro de veredicto final (Aceptado / Rechazado / Req. Corrección) | **Dado** el fin de las evaluaciones, **cuando** el editor selecciona el veredicto final, **entonces** el sistema actualiza el estado definitivo del manuscrito. | Manual Proceso Editorial UNL | Validado |
| **RF-20** | Sistema / Todos | Informar oportunamente los cambios en los manuscritos | RF-20: Notificaciones automáticas por correo electrónico | **Dado** un evento importante (asignación, veredicto, cambio de estado), **cuando** se registra, **entonces** el sistema envía un correo a los implicados. | Requisitos ACD 2 | Validado |
| **RF-21** | Autor | Corregir información descriptiva del manuscrito | RF-21: Edición de metadatos en estado "Borrador" o "Requiere Corrección" | **Dado** un artículo en "Borrador" o "Requiere Corrección", **cuando** el autor modifica metadatos, **entonces** el sistema guarda los cambios con HTTP `200 OK`. | Especificación APE 2 & RFC 9110 (Sec. 9.3.4) | Validado |
| **RF-22** | Autor | Retirar una propuesta de publicación | RF-22: Eliminación lógica del manuscrito ("Dado de baja") | **Dado** un autor con envío activo, **cuando** solicita la eliminación, **entonces** el sistema marca el registro como "Dado de baja" y lo oculta. | Especificación APE 2 & RFC 9110 (Sec. 9.3.5) | Validado |

---

### B. Requisitos No Funcionales (RNF-01 al RNF-09)

| ID | Actor | Necesidad | Historia / Requisito | Criterio de Aceptación (Dado / Cuando / Entonces) | Fuente / Referencia | Estado |
|---|---|---|---|---|---|---|
| **RNF-01** | Todos | Garantizar velocidad y disponibilidad | RNF-01: Soporte de 50 usuarios concurrentes, P95 $\le$ 2s y éxito $\ge$ 95% | **Dado** una carga de 50 usuarios simultáneos, **cuando** realizan consultas, **entonces** la API responde en menos de 2 segundos en el 95% de casos. | Estándar de Calidad de Software | Validado |
| **RNF-02** | Todos | Prevenir corrupción o accesos indebidos | RNF-02: Validación en backend, control de acceso e integridad BD | **Dado** un envío con datos malformados, **cuando** llega al backend, **entonces** la API rechaza la transacción e impide registros inconsistentes. | Estándar OWASP & RFC 9110 | Validado |
| **RNF-03** | Todos | Garantizar acceso multiplataforma web | RNF-03: Compatibilidad con las últimas 2 versiones de Chrome, Firefox y Edge | **Dado** un navegador Chrome, Firefox o Edge actualizado, **cuando** el usuario opera la interfaz, **entonces** todas las funciones responden correctamente. | Estándar Web W3C | Validado |
| **RNF-04** | Todos | Evitar errores del usuario mediante alertas claras | RNF-04: Identificación de campos obligatorios y mensajes de error | **Dado** un formulario con campos inválidos o vacíos, **cuando** el usuario intenta enviar, **entonces** la interfaz resalta el error y la forma de corregirlo. | Principios de Usabilidad UX | Validado |
| **RNF-05** | Sistema | Mantener el historial inalterable de versiones | RNF-05: Almacenamiento persistente de PDF con ID único de versión | **Dado** un nuevo archivo PDF, **cuando** se guarda en el servidor, **entonces** el sistema asigna un ID único e impide sobrescribir la versión anterior. | Políticas de Gestión Documental UNL | Validado |
| **RNF-06** | Todos | Proteger la privacidad de los datos en tránsito | RNF-06: Comunicaciones HTTPS y cifrado de credenciales | **Dado** el intercambio de información cliente-servidor, **cuando** viaja por la red, **entonces** utiliza HTTPS sin credenciales en texto plano. | RFC 9110 (Sec. 11) & OWASP | Validado |
| **RNF-07** | Revisor | Garantizar la imparcialidad en la evaluación por pares | RNF-07: Protección de evaluación doble ciego | **Dado** una consulta enviada por un Revisor, **cuando** la API responde, **entonces** se excluyen los datos de identidad del Autor. | Reglamento de Publicaciones UNL | Validado |
| **RNF-08** | Administrador | Mantener trazabilidad legal inalterable | RNF-08: Bitácoras de auditoría protegidas contra modificación | **Dado** un registro en la bitácora de auditoría, **cuando** un usuario intenta modificarlo, **entonces** el sistema bloquea la acción. | Estándar ISO 27001 | Validado |
| **RNF-09** | Todos | Evitar la fuga de datos técnicos sensibles | RNF-09: Formato estandarizado de errores HTTP sin revelar trazas internas | **Dado** un error en la API, **cuando** genera la respuesta, **entonces** envía un código HTTP adecuado con mensaje genérico seguro. | RFC 9110 (Sec. 15) | Validado |

---

## 10. Observaciones o Decisiones Pendientes
* **Definición del Proveedor de Almacenamiento de Archivos:** Se evaluará en la siguiente iteración el uso de almacenamiento de objetos en la nube (ej. AWS S3 / Google Cloud Storage) frente a volúmenes persistentes locales para la gestión de archivos PDF (RNF-05).
* **Definición del Tamaño Máximo de PDF:** Se establecerá el límite exacto en megabytes (ej. máximo 15 MB) para las validaciones en backend requeridas en el RF-14 y HU-012.

---


Durante la revisión y depuración realizada para la Actividad Autónoma 2 (AA 2), se llevaron a cabo las siguientes acciones de mejora individual:
1. **Fundamentación Técnica en HTTP (RFC 9110):** Se justificaron técnicamente los requisitos asociando las operaciones del flujo editorial con los métodos HTTP correspondientes (`GET`, `POST`, `PUT`, `DELETE`) y definiendo explícitamente las respuestas de códigos de estado (`200 OK`, `201 Created`, `400 Bad Request`, `401 Unauthorized`, `403 Forbidden`).
2. **Depuración y Refinamiento de Historias de Usuario:** Se eliminaron las referencias explícitas a tecnologías concretas de backend o bases de datos en la redacción de las historias, asegurando que expresen la necesidad del actor y el valor de negocio.
3. **Elaboración de la Matriz de Trazabilidad Completa:** Se construyó la matriz integrando secuencialmente el 100% de los Requisitos Funcionales (RF-01 al RF-22) y No Funcionales (RNF-01 al RNF-09), garantizando la trazabilidad entre actores, necesidades, especificaciones, criterios de aceptación BDD y fuentes del dominio.