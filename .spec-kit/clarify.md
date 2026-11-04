# Clarificación Técnica — Sistema de Gestión de Publicaciones Científicas

**Archivo:** `clarify.md`  
**Metodología:** SpecKit — Fase Clarify  
**Versión:** 1.0  
**Fecha:** 22 de octubre de 2026  
**Entradas analizadas:** `.spec-kit/constitution.md`, `.spec-kit/specify.md`  
**Estado:** Pendiente de respuestas

> **Objetivo:** resolver únicamente las decisiones de infraestructura, almacenamiento físico de PDF, límites de carga y despliegue que bloquean la arquitectura del próximo `plan.md`. No se cuestionan reglas de negocio, roles, estados, transiciones ni el stack tecnológico ya fijado por la constitución.

---

## 1. Decisiones ya fijadas que no se preguntan

| Tema | Decisión vigente | Fuente |
|---|---|---|
| Arquitectura | Cliente-Servidor: SPA + API REST | Constitución §1 |
| Estructura | Directorios raíz `/backend` y `/frontend` | Constitución §1 |
| Orquestación | Docker y `docker-compose` obligatorios | Constitución §1 |
| Stack | Django + Django REST Framework; Angular; PostgreSQL | Constitución §2 |
| Archivos | Solo PDF; validación estricta en Angular y Django | Constitución §5 |
| Versiones | Los PDF anteriores nunca se sobrescriben; historial intacto | Constitución §5 |
| Borrado | Lógico (`is_active = False`), nunca físico | Constitución §5 |
| Tamaño máximo | 50 MB propuesto por la especificación, ajustable por la institución | Specify §13.6 |
| PDF de evaluación | La especificación ya exige una copia sanitizada para la evaluación | Specify HU-16 |
| PDF histórico | La especificación ya exige conservar el PDF exacto y su sello de integridad | Specify HU-23 |
| Conservación | Según la política institucional; sin eliminación durante la operación normal | Specify §13.15 |

**Consecuencia:** las preguntas siguientes no repiten el stack, la arquitectura cliente-servidor, el modelo de estados ni las reglas de doble ciego. Solo resuelven decisiones físicas y operativas que el `plan.md` necesita para dimensionar contenedores, volúmenes, proxy, respaldos y pruebas.

---

## 2. Preguntas de clarificación

### Q1 — ¿Dónde se almacenarán los PDF originales y las copias sanitizadas?

**Por qué importa:** define el volumen persistente, la ruta física de cada versión, la estrategia de respaldo y la forma de servir los archivos sin exponer el almacenamiento.

| Opción | Descripción |
|---|---|
| **A** | **Volumen persistente local:** PDF original inmutable y copia sanitizada inmutable por versión, en rutas separadas dentro del volumen montado en el contenedor del backend. |
| **B** | **Volumen local con sanitización al vuelo:** solo se conserva el PDF original inmutable; la copia sanitizada se genera en cada descarga autorizada. |
| **C** | **Almacenamiento de objetos compatible con S3:** original y copia sanitizada en un servicio de objetos (MinIO local o servicio externo), con versionado y acceso mediante URLs firmadas. |
| **D** | **PostgreSQL:** PDF original y copia sanitizada almacenados como datos binarios en la base de datos; entrega mediante la aplicación. |

**Recomendación:** **A** para el escenario on-premise de un solo servidor. Es la opción más simple compatible con el despliegue Docker Compose, conserva ambas copias de forma inmutable y evita introducir un servicio de objetos adicional. Si Q3 confirma un despliegue en nube, **C** pasa a ser la opción preferente.

**Impacto en `plan.md`:** estructura de volúmenes, rutas por manuscrito/versión, permisos del sistema de archivos, cálculo del sello de integridad, espacio en disco y estrategia de respaldo.

---

### Q2 — ¿Cuál es el límite máximo por archivo PDF y qué margen debe permitir el servidor?

**Por qué importa:** el límite debe ser idéntico en Angular, Django, el proxy inverso y las pruebas de aceptación; un desajuste produce rechazos falsos o cargas parciales.

| Opción | Descripción |
|---|---|
| **A** | **20 MB por PDF**; límite de request de 25 MB en el proxy. |
| **B** | **50 MB por PDF**; límite de request de 60 MB en el proxy. |
| **C** | **100 MB por PDF**; límite de request de 110 MB en el proxy. |
| **D** | **200 MB por PDF**; límite de request de 220 MB en el proxy. |
| **E** | **Otro valor:** indicar el límite por PDF y el margen del proxy. |

*Nota técnica: para esta tabla, 1 MB = 1.048.576 bytes. El margen del proxy cubre las cabeceras y el sobre multipart, no un archivo adicional.*

**Recomendación:** **B**, porque coincide con el valor inicial propuesto en la especificación y es suficiente para manuscritos científicos con figuras, sin exigir infraestructura de almacenamiento innecesaria.

**Impacto en `plan.md`:** `client_max_body_size` del proxy, `DATA_UPLOAD_MAX_MEMORY_SIZE` y `FILE_UPLOAD_MAX_MEMORY_SIZE` de Django, validador de Angular, tiempo máximo de carga, pruebas de límite exacto y dimensionamiento del volumen.

*Si la institución fija además un número máximo de cargas concurrentes o una cuota total de almacenamiento, indicarlo junto con la respuesta; no se asume un valor por defecto.*

---

### Q3 — ¿En qué entorno se desplegará la aplicación en producción?

**Por qué importa:** determina la topología de contenedores, la terminación TLS, la gestión de volúmenes, el dominio, los respaldos y si `docker-compose` sigue siendo el orquestador de producción.

| Opción | Descripción |
|---|---|
| **A** | **Servidor Linux on-premise único** con Docker Compose; Nginx sirve Angular, termina TLS y actúa como proxy hacia Django. |
| **B** | **VM IaaS en nube** con Docker Compose; Nginx con la misma función. |
| **C** | **Servicio gestionado de contenedores** (ECS, Cloud Run o Azure Container Apps) con balanceador gestionado; sin Docker Compose en producción. |
| **D** | **Clúster Kubernetes** con Ingress y almacenamiento persistente gestionado. |

**Recomendación:** **A**, porque es la opción que mejor se alinea con la constitución, con el tamaño esperado del sistema y con un único servidor institucional. Las opciones **C** y **D** contradicen la obligación de `docker-compose` de la Constitución §1; si se eligen, deben registrarse como excepción y actualizar la constitución antes de planificar.

**Impacto en `plan.md`:** servicios del compose, red interna, TLS, DNS, volumen de PostgreSQL, volumen de PDF, usuario de despliegue, actualizaciones y pruebas de humo.

---

### Q4 — ¿Cómo se entregarán los PDF internos y los del catálogo público?

**Por qué importa:** la entrega debe separar los PDF privados (acceso por objeto) de los aceptados (acceso público), sin exponer rutas ni archivos de manuscritos no aceptados.

| Opción | Descripción |
|---|---|
| **A** | **Django/DRF para ambos:** la aplicación valida la autorización de los PDF internos y la elegibilidad de los públicos, y transmite el archivo. |
| **B** | **`X-Accel-Redirect` con Nginx:** Django autoriza los PDF internos o valida la elegibilidad pública, y Nginx entrega desde rutas internas separadas (privada y de catálogo). |
| **C** | **URLs firmadas para internos + URL pública controlada para aceptados:** el almacenamiento de objetos entrega los archivos tras la validación previa. |
| **D** | **Acceso estático directo:** los archivos se sirven desde una única ruta protegida solo por un nombre no adivinable. |

**Recomendación:** **B** si Q1 es A o B, porque separa las rutas internas de privacidad y de catálogo, y mantiene la autorización en Django. **C** si Q1 es C. La opción **D** no se recomienda porque no distingue archivos públicos de privados ni garantiza autorización por objeto.

**Impacto en `plan.md`:** endpoints de descarga interna y pública, permisos, rutas internas de Nginx, cabeceras de seguridad, registro de accesos y pruebas de acceso denegado o no aceptado.

---

### Q5 — ¿Qué esquema de respaldo y restauración se aplicará a PostgreSQL y a los PDF?

**Por qué importa:** el historial, la auditoría y los PDF inmutables son evidencia del proceso; sin una restauración probada, una falla del servidor puede dejar el expediente incompleto.

| Opción | Descripción |
|---|---|
| **A** | **Respaldo diario completo cifrado** de PostgreSQL y del volumen de PDF a almacenamiento externo; retención de 30 días; prueba de restauración mensual. |
| **B** | **Respaldo diario incremental + completo semanal**; retención de 90 días; prueba de restauración trimestral. |
| **C** | **Snapshot diario de la VM o del volumen**; retención de 7 días; restauración solo ante incidente. |
| **D** | **Sin respaldo automatizado:** copias manuales bajo demanda. |

**Recomendación:** **A**, porque el volumen de datos es acotado, la operación es simple y la prueba mensual demuestra que el historial y la auditoría pueden recuperarse. La retención de 30 días aplica solo a las copias de respaldo; los registros vivos se conservan según la política institucional y no se eliminan por esta decisión.

**Impacto en `plan.md`:** tareas programadas, almacenamiento externo, cifrado, credenciales de respaldo, procedimiento de restauración y criterios de aceptación operativa.

---

## 3. Matriz de impacto en el plan

| Pregunta | Decisión que resuelve | Sección del `plan.md` afectada |
|---|---|---|
| Q1 | Ubicación física y copia sanitizada | Technical Context, Project Structure, Data Model |
| Q2 | Límite de carga y configuración del proxy | Technical Context, Constraints, Testing |
| Q3 | Topología de despliegue y TLS | Technical Context, Deployment, Quickstart |
| Q4 | Entrega de PDF internos y públicos | API Contracts, Security, Performance |
| Q5 | Respaldo y restauración | Deployment, Operations, Quickstart |

---

## 4. Formato de respuesta

Responder con el código de cada pregunta y la letra elegida:

```text
Q1 = A
Q2 = B
Q3 = A
Q4 = B
Q5 = A
```

Si se elige la opción **E** de Q2, indicar el valor exacto. Si se elige **C** o **D** en Q3, indicar si se acepta la actualización de la constitución.

**Criterio de cierre:** con Q1–Q5 respondidas, el `plan.md` puede definir volúmenes, servicios, límites, entrega de archivos y respaldos sin dejar decisiones de infraestructura abiertas.
