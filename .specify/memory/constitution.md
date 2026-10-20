<!-- Sync Impact Report
Versión: 1.0.0 -> 2.0.0
Fecha de Ratificación: 2026-10-15
Última Enmienda: 2026-10-20
Resumen de Cambios:
- Reenfoque del documento hacia reglas exclusivamente técnicas, de arquitectura y de calidad.
- Se eliminan los principios no técnicos (propósito académico, SDD, container-first como principio)
  y todo contenido de historias de usuario.
- Principios redefinidos:
  * I. Arquitectura MVC sobre Django (nuevo)
  * II. Seguridad, RBAC y Doble Ciego (ampliado a partir del antiguo principio II)
  * III. Manejo de Archivos PDF y Versionamiento Inmutable (nuevo)
  * IV. Auditoría Inmutable (nuevo)
  * V. Calidad de Código, Pruebas y Verificación Continua (renombrado del antiguo IV)
- Se añaden secciones: Restricciones y Supuestos Técnicos, Requisitos No Funcionales, y
  Estándares de Desarrollo y Entrega.
- Se conserva el stack unificado en MySQL 8.0+ y el flujo container-first dentro de los estándares.
-->

# Constitución de ScientificPub UNL

## Core Principles

### I. Arquitectura Modelo-Vista-Controlador sobre Django

El servidor DEBE implementarse en Python con el framework Django, aplicando el patrón
de arquitectura Modelo-Vista-Controlador (MVC) que Django materializa en su esquema
MVT (Model-View-Template con capa de control en el enrutador y la capa de servicios).
Esta arquitectura es la única autorizada para la capa de servidor.

Reglas no negociables:

- **Lenguaje y framework:** Python 3.11+ y Django. Queda prohibido introducir frameworks
  de servidor alternativos (Flask, FastAPI, Node.js) para la lógica de negocio principal.
- **Separación en capas:** La lógica de dominio reside en los modelos y servicios; las
  vistas/serializadores solo orquestan entrada/salida; el enrutador solo despacha.
  Se prohíbe concentrar reglas de negocio en las vistas o en el `urls.py`.
- **Aislamiento de dependencias:** Toda dependencia DEBE declararse en `requirements.txt`
  y resolverse dentro de un entorno virtual reproducible (contenedor Docker).
- **Sin acoplamiento cruzado:** Los módulos de dominio (`apps/users`, `apps/publications`,
  `apps/reviews`) DEBEN ser desacoplados; se prohíben las dependencias circulares.
- **Integración controlada:** Las integraciones externas (almacenamiento de objetos tipo
  AWS S3, resolución de DOI) y las bibliotecas de reportes (Pandas/Matplotlib) se exponen
  a través de interfaces de servicio, nunca incrustadas en modelos o vistas.

**Racional:** Un único patrón de servidor elimina la ambigüedad arquitectónica, facilita
las pruebas automatizadas, el mantenimiento a lo largo de ciclos académicos y la
incorporación de nuevos desarrolladores al equipo.

### II. Seguridad y Control de Acceso: RBAC y Doble Ciego (NO NEGOCIABLE)

Todo acceso a datos y operaciones DEBE estar gobernado por Control de Accesos Basado en
Roles (RBAC). El anonimato de la evaluación por pares a doble ciego es un requisito
absoluto e inquebrantable.

Reglas no negociables:

- **RBAC obligatorio:** Cada operación verificada en el backend DEBE validar el rol del
  usuario. Un acceso no autorizado en un endpoint protegido DEBE responder `403 Forbidden`.
  Se aprovechan de forma nativa el sistema de grupos y permisos de Django.
- **Roles del sistema:** Autor, Revisor, Editor y Administrador. Un docente PUEDE tener
  más de un rol; la resolución de permisos DEBE combinar sus roles sin escalar privilegios.
- **Doble ciego inviolable:** Un usuario con rol Revisor JAMÁS DEBE acceder a los campos de
  identidad de los Autores (nombres, correos, filiación) mientras el manuscrito permanezca
  en evaluación. La restricción DEBE aplicarse en la capa de consulta a la base de datos y
  en los serializadores/plantillas del módulo `apps/reviews/`, no solo en la interfaz.
- **Sanitización de documentos:** Antes de exponer un PDF a un Revisor, el sistema DEBE
  eliminar metadatos de autoría (propiedades de autor, firmas del software de creación y
  afiliación institucional). Cualquier vulneración del anonimato constituye una falla crítica.
- **Transporte y credenciales:** Toda comunicación DEBE usar HTTPS. Las credenciales nunca
  se almacenan ni transmiten en texto plano; los secretos se inyectan por variables de entorno.

**Racional:** La imparcialidad de la revisión por pares depende del anonimato efectivo, y
el control de acceso previene operaciones indebidas. Un fallo aquí compromete la validez
académica de todo el proceso editorial.

### III. Manejo de Archivos PDF y Versionamiento Inmutable (NO NEGOCIABLE)

El sistema acepta única y exclusivamente documentos en formato PDF y conserva cada versión
de forma inmutable.

Reglas no negociables:

- **Formato exclusivo:** El sistema DEBE aceptar única y exclusivamente archivos en formato
  PDF. Cualquier otro tipo (`docx`, `png`, etc.) DEBE rechazarse con `400 Bad Request`.
- **Persistencia con identificador único:** Cada archivo almacenado DEBE poseer un
  identificador único de versión.
- **No sobrescritura:** Una nueva carga del autor JAMÁS DEBE sobrescribir ni alterar un
  archivo de versión anterior. Cada corrección crea un registro nuevo e independiente.
- **Almacenamiento protegido:** Los PDF DEBEN residir en almacenamiento controlado
  (`media/` protegido o almacenamiento de objetos) con acceso restringido por rol, nunca
  expuestos como recursos estáticos públicos sin autorización.

**Racional:** La trazabilidad documental y la integridad de la producción científica exigen
que ninguna versión histórica pueda perderse o ser modificada, y que el formato sea
homogéneo para su validación y sanitización.

### IV. Auditoría Inmutable de Acciones Críticas

Toda acción relevante del sistema DEBE generar un registro de auditoría inalterable.

Reglas no negociables:

- **Eventos auditados:** Al menos las siguientes acciones generan auditoría: inicio de sesión,
  creación y cambio de estado de manuscritos, asignación de revisores, registro de
  evaluaciones, emisión de veredictos y cambios de rol o permisos.
- **Contenido del registro:** Cada registro DEBE incluir como mínimo el usuario responsable,
  la fecha/hora y la acción ejecutada, más la entidad afectada.
- **Inmutabilidad:** Los registros de auditoría DEBEN ser de solo-anexado (append-only). Se
  prohíbe su edición o eliminación por usuarios ordinarios, incluyendo desde el panel de
  administración.
- **Retención:** Los registros DEBEN conservarse íntegros para efectos de trazabilidad y
  cumplimiento.

**Racional:** Sin una bitácora inmutable no es posible reconstruir el historial editorial,
resolver disputas de autoría ni demostrar cumplimiento normativo.

### V. Calidad de Código, Pruebas y Verificación Continua

El código se escribe una vez y se mantiene a lo largo de múltiples ciclos. Cada contribución
DEBE superar controles de calidad estrictos y automatizados.

Reglas no negociables:

- **Formato y estilo:** `black` (línea máxima 88) e `isort` (perfil `black`) son obligatorios.
- **Linting:** Cero advertencias bajo `ruff` o `flake8`.
- **Tipado y documentación:** Toda firma pública DEBE declarar anotaciones de tipo; todo
  módulo, clase y método público DEBE incluir docstring (PEP 257).
- **Pruebas:** Toda funcionalidad DEBE acompañarse de pruebas automatizadas deterministas.
  Los casos límite y los estados de error DEBEN estar cubiertos explícitamente.
- **Verificación continua:** Toda contribución DEBE pasar el pipeline de CI en verde
  (linters, análisis estático, `manage.py check`, migraciones al día y suite de pruebas)
  antes de integrarse.

**Racional:** La calidad sostenida y la verificación automática reducen regresiones y
garantizan que el sistema siga siendo confiable tras cada cambio.

## Restricciones y Supuestos Técnicos

- **Alcance congelado:** El alcance se limita al flujo de revisión y publicación en el
  catálogo interno. La integración con bases externas (Scopus y similares) queda fuera de
  esta iteración.
- **Formato de archivo:** PDF exclusivamente, conforme al Principio III.
- **Privacidad:** Restricción de doble ciego conforme al Principio II.
- **Autenticación:** Uso de correos institucionales de la Universidad Nacional de Loja.
- **Stack base:** Python 3.11+, Django 5.x, MySQL 8.0+, Docker y Docker Compose. Las
  migraciones DEBEN generarse y aplicarse dentro del contenedor; una migración fusionada
  es inmutable.
- **Escalabilidad futura:** La incorporación de bibliotecas científicas (Pandas/Matplotlib)
  para reportes DEBE hacerse mediante servicios desacoplados (Principio I).

## Requisitos No Funcionales de Cumplimiento Obligatorio

- **RNF-01 (Rendimiento):** Soportar 50 usuarios concurrentes con tasa de éxito ≥ 95% y
  tiempo de respuesta < 2 s (percentil 95).
- **RNF-02 (Integridad y control):** El backend DEBE aplicar control de acceso en cada
  operación y apoyarse en restricciones de integridad en la base de datos.
- **RNF-05 (Persistencia documental):** Versiones PDF persistentes con identificador único,
  sin sobrescritura (Principio III).
- **RNF-06 (Cifrado):** Toda comunicación por HTTPS; credenciales nunca en texto plano.
- **RNF-07 (Doble ciego):** Anonimato obligatorio en la API y en la interfaz (Principio II).
- **RNF-08 (Auditoría):** Acciones relevantes generan registros inmutables con usuario,
  fecha y acción (Principio IV).

## Estándares de Desarrollo y Entrega

- **Entorno container-first:** El desarrollo, la integración continua y el despliegue se
  ejecutan bajo especificaciones de contenedor idénticas; Docker es la única fuente de
  verdad de ejecución.
- **Idioma técnico:** Variables, funciones, clases, tablas, comentarios, mensajes de commit
  y títulos de Pull Request en inglés. La documentación de dominio puede redactarse en español.
- **Diseño de datos:** Uso de `BigAutoField`/`UUIDField` como identificador; `created_at` y
  `updated_at` en todo modelo de negocio; `PROTECT`/`SET_NULL` en entidades críticas;
  `db_table` e índices explícitos en campos de filtrado frecuente.
- **Flujo de trabajo Git:** `main` (producción), `develop` (integración) y ramas
  `feature/`, `fix/`, `hotfix/`. Push directo bloqueado en `main` y `develop`; integración
  por Pull Request con `Squash and Merge` y aprobación de al menos un revisor técnico.
- **Comandos operativos:** Las operaciones de Django y las pruebas se ejecutan dentro del
  contenedor (`docker compose exec web ...`), no directamente en el host.

## Governance

- **Supremacía:** Esta Constitución prevalece sobre cualquier acuerdo verbal, convención
  informal o atajo técnico. Todo Pull Request que la infrinja DEBE ser rechazado.
- **Compliance en revisiones:** Toda revisión de PR DEBE verificar el cumplimiento de estos
  principios, en especial los Principios II, III y IV (no negociables).
- **Procedimiento de enmienda:** Cualquier modificación DEBE abrir un Issue que justifique la
  necesidad técnica, seguido de un Pull Request con aprobación del Tech Lead y del Comité
  Académico.
- **Versionado semántico:**
  - **MAJOR:** Eliminación o redefinición incompatible de principios.
  - **MINOR:** Incorporación de nuevos principios, secciones o directrices materiales.
  - **PATCH:** Correcciones de estilo, aclaraciones o ajustes no semánticos.
- **Revisión de cumplimiento:** En cada incremento se DEBE verificar que los requisitos no
  funcionales obligatorios (RNF-01, RNF-02, RNF-05, RNF-06, RNF-07, RNF-08) sigan satisfechos.

**Version**: 2.0.0 | **Ratified**: 2026-10-15 | **Last Amended**: 2026-10-20
