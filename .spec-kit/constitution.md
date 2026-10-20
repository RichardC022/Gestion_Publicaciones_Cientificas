<!-- Sync Impact Report
Versión: 0.0.0 -> 1.0.0
Fecha de Ratificación: 2026-10-15
Última Enmienda: 2026-10-15
Resumen de Cambios:
- Redacción inicial y ratificación formal de la Constitución de ScientificPub UNL bajo el estándar GitHub Spec Kit en idioma español.
- Establecimiento de directrices estrictas: evaluación a doble ciego, desarrollo guiado por especificaciones (SDD), calidad de software y flujo 100% containerizado.
-->

# Constitución de ScientificPub UNL

## Principios Fundamentales

### I. Propósito Académico e Integridad Institucional
ScientificPub UNL es la plataforma oficial de gestión de manuscritos y publicaciones científicas de la Universidad Nacional de Loja (UNL). Toda decisión de diseño arquitectónico, modelado de datos y flujo de usuario DEBE salvaguardar la credibilidad institucional, el cumplimiento de derechos de autor y el rigor científico. El sistema opera como el registro fidedigno de la producción intelectual de los docentes de la universidad.

### II. Confidencialidad y Evaluación a Doble Ciego (NO NEGOCIABLE)
El anonimato durante el proceso de revisión por pares es absoluto e inquebrantable. La plataforma DEBE desacoplar de forma sistemática la identidad de los autores respecto a los manuscritos postulados, matrices de evaluación, dictámenes y registros del sistema accesibles por los revisores. Los borradores en formato PDF DEBEN someterse a una sanitización automatizada de metadatos (propiedades de autor, firmas del software de creación y datos de afiliación institucional) antes de ser asignados a los revisores. Cualquier vulneración del protocolo de anonimato constituye una falla crítica del sistema.

### III. Desarrollo Guiado por Especificaciones (SDD) y Trazabilidad
Ninguna implementación de código podrá preceder a una especificación formal y ratificada. Todo incremento funcional, modificación de esquemas de datos o ajuste de flujos de trabajo DEBE originarse a partir de especificaciones estructuradas bajo el marco de Spec Kit (`.specify/`). Todas las iteraciones de borradores académicos, rondas de evaluación y resoluciones editoriales DEBEN ser inmutables en su versionado y contar con auditoría integral.

### IV. Calidad de Código y Verificación Continua
El código se escribe una vez y se mantiene a lo largo de múltiples ciclos académicos. Cada contribución a la base de código DEBE superar estrictos controles de calidad: cero advertencias de linters, conformidad en análisis estático, pruebas automatizadas deterministas y cobertura completa de anotaciones de tipos. Los casos límite no validados o estados de error ambiguos en evaluaciones académicas son inaceptables.

### V. Enfoque Container-First y Paridad Absoluta de Entornos
El entorno de desarrollo local, los flujos de integración continua (CI) y los despliegues en servidores institucionales DEBEN ejecutarse bajo especificaciones de contenedor idénticas. Las divergencias causadas por configuraciones locales en los equipos de los desarrolladores no serán toleradas; Docker constituye la única fuente de verdad para la ejecución del sistema.

---

## Arquitectura y Stack Tecnológico

### 1. Matriz de Tecnologías
- **Entorno de Ejecución:** Python 3.11+
- **Framework Backend:** Django (Patrón MVT con arquitectura extensible a API REST)
- **Base de Datos Principal:** PostgreSQL 15+
- **Contenedores y Orquestación:** Docker Engine y Docker Compose
- **Control de Versiones:** Git / GitHub
- **Almacenamiento de Archivos:** Django Staticfiles y Almacenamiento Protegido de Medios (`media/`) para manuscritos académicos

### 2. Estructura Modular del Proyecto
El repositorio implementa una arquitectura modular desacoplada. Se prohíben estrictamente las dependencias circulares y el acoplamiento cruzado entre aplicaciones.

```text
/
├── config/                  # Configuración central del proyecto Django
│   ├── __init__.py
│   ├── asgi.py              # Punto de entrada ASGI (procesos asíncronos)
│   ├── settings.py          # Configuración basada en variables de entorno
│   ├── urls.py              # Enrutador principal de URLs
│   └── wsgi.py              # Punto de entrada WSGI
├── apps/                    # Módulos de dominio de negocio
│   ├── users/               # Autenticación, roles institucionales y RBAC
│   ├── publications/        # Postulación, versionado de borradores y catálogo
│   └── reviews/             # Evaluación a doble ciego, asignación y dictámenes
├── media/                   # Almacenamiento protegido (manuscritos PDF)
├── static/                  # Recursos estáticos institucionales (CSS, JS, imágenes)
├── .spec-kit/               # Configuración del espacio de trabajo de Spec Kit
├── .specify/                # Especificaciones y memoria viva de SDD
├── Dockerfile               # Definición multi-etapa del contenedor de la aplicación
├── docker-compose.yml       # Orquestación de servicios (web, db)
├── requirements.txt         # Dependencias fijadas del proyecto
└── manage.py                # Interfaz CLI de Django
```

---

## Estándares y Convenciones de Código

### 1. Idioma y Nomenclatura
- **Idioma del Código:** Todos los artefactos técnicos—variables, funciones, clases, tablas de base de datos, comentarios de código, mensajes de commit y títulos de Pull Requests—DEBEN redactarse en **inglés**.
- **Vocabulario Institucional:** Aunque los conceptos del dominio de la UNL se documenten en español, los modelos de datos y código técnico se mantienen en inglés (ejemplo: `Manuscript`, `ReviewAssignment`, `EvaluationRubric`, `FacultyMember`).
- **Convenciones de Nombres:**
  - Clases y Modelos: `PascalCase` (ejemplo: `ManuscriptVersion`, `ReviewVerdict`).
  - Funciones, Métodos y Variables: `snake_case` (ejemplo: `assign_blind_reviewer`, `is_metadata_scrubbed`).
  - Constantes: `UPPER_SNAKE_CASE` (ejemplo: `MAX_UPLOAD_SIZE_MB`, `BLIND_REVIEW_WINDOW_DAYS`).

### 2. Formato y Análisis Estático
- **Formateador de Código:** `black` obligatorio (longitud máxima de línea: 88 caracteres). La ejecución previa al commit es mandatoria.
- **Orden de Importaciones:** `isort` obligatorio con perfil `profile = "black"`. Los bloques de importación deben respetar estrictamente el estándar PEP 8: Librería estándar, librerías de terceros, aplicaciones locales de Django.
- **Linters:** Se exige cero advertencias bajo `flake8` o `ruff`.

### 3. Documentación y Tipado
- **Docstrings:** Todos los módulos, clases y métodos públicos DEBEN incluir docstrings bajo la especificación PEP 257 (estilo Google o Sphinx), detallando parámetros, tipos de retorno y excepciones de negocio.
- **Type Hints:** Toda firma de función o método DEBE declarar anotaciones de tipos de Python (`Optional`, `Union`, `List`, `Dict`, o sintaxis de unión `A | B`).

---

## Flujo de Trabajo en Git y Estrategia de Ramas

### 1. Topología de Ramas
- **`main`:** Rama de producción. Contiene únicamente código estable, auditado y desplegado. El push directo está estrictamente bloqueado. Cada entrega se etiqueta mediante versionado semántico (`vMAJOR.MINOR.PATCH`).
- **`develop`:** Rama de integración continua. Punto de convergencia de todas las funcionalidades aprobadas. El push directo está bloqueado.
- **`feature/<issue-id>-<short-description>`:** Ramas para nuevas funcionalidades, creadas exclusivamente a partir de `develop`.
- **`fix/<issue-id>-<short-description>`:** Ramas para corrección de errores, originadas desde `develop`.
- **`hotfix/<issue-id>-<short-description>`:** Parches de emergencia para producción, creados directamente desde `main` y fusionados posteriormente tanto en `main` como en `develop`.

### 2. Pull Requests (PR) y Controles de Calidad
1. **Alcance:** Cada PR debe abordar una sola historia de usuario o corrección de fallo. Se rechazarán PRs masivos o no focalizados.
2. **Revisión de Código Obligatoria:** Se requiere la aprobación explícita de al menos **un revisor técnico** (Tech Lead o par asignado) previo a la integración.
3. **Validación Automática:** Toda comprobación de CI (construcción de imagen Docker, dry-run de migraciones, suite de tests, `black`, `isort`, linters) DEBE estar en verde.
4. **Estrategia de Integración:** Se aplicará `Squash and Merge` para ramas `feature/` y `fix/`, preservando un historial limpio y lineal en `develop`.

---

## Entorno de Desarrollo (Estándares Docker)

### 1. Política Estricta de Aislamiento
- **Prohibición en Host:** Queda **ESTRICTAMENTE PROHIBIDO** instalar paquetes, ejecutar pruebas o correr comandos de base de datos directamente en el sistema operativo del host de desarrollo.
- Todo el ciclo de desarrollo DEBE ejecutarse dentro de los contenedores gestionados por Docker Compose.

### 2. Comandos Operativos Estándar
- **Levantar el entorno completo:**
  ```bash
  docker compose up --build -d
  ```
- **Monitorear registros de la aplicación:**
  ```bash
  docker compose logs -f web
  ```
- **Ejecutar comandos de Django:**
  ```bash
  docker compose exec web python manage.py <comando>
  ```
- **Correr suite de pruebas automatizadas:**
  ```bash
  docker compose exec web python manage.py test
  ```
- **Detener el entorno:**
  ```bash
  docker compose down
  ```

---

## Gestión de Base de Datos y Protocolo de Migraciones

### 1. Estándares para el Diseño de Modelos
- **Identificadores Únicos:** Uso explícito de `BigAutoField` o `UUIDField` para todas las entidades primarias.
- **Campos de Auditoría:** Todo modelo de negocio DEBE heredar de un modelo base abstracto con:
  - `created_at = models.DateTimeField(auto_now_add=True)`
  - `updated_at = models.DateTimeField(auto_now=True)`
- **Integridad Referencial:** Se restringe el uso de `models.CASCADE` en entidades críticas (manuscritos, revisiones, evaluaciones y registros de auditoría). Se exige el uso de `models.PROTECT` o `models.SET_NULL` para prevenir eliminaciones accidentales en cascada.
- **Nombres de Tabla e Índices:** Es obligatorio definir `db_table` explícito e índices en campos clave de búsqueda y filtros frecuentes (estado de postulación, fechas, llaves foráneas).

### 2. Generación y Aplicación de Migraciones
- **Generación en Contenedor:** Las migraciones DEBEN generarse exclusivamente desde el contenedor:
  ```bash
  docker compose exec web python manage.py makemigrations
  ```
- **Aplicación de Migraciones:**
  ```bash
  docker compose exec web python manage.py migrate
  ```
- **Inmutabilidad:** Una vez que un archivo de migración ha sido fusionado en `develop` o `main`, adquiere carácter de **INMUTABLE**. Jamás se debe editar, eliminar o regenerar retroactivamente.
- **Resolución de Conflictos:** Ante colisiones de ramas en migraciones, se debe ejecutar:
  ```bash
  docker compose exec web python manage.py makemigrations --merge
  ```
  La migración de resolución debe verificarse en el contenedor antes de solicitar el merge.

---

## Seguridad, Privacidad y Cumplimiento

### 1. Gestión de Secretos y Variables de Entorno
- **Segregación de Credenciales:** Prohibido almacenar contraseñas, credenciales de PostgreSQL, tokens de servicios o la clave `SECRET_KEY` en el control de versiones.
- **Carga vía `.env`:** Todas las variables sensibles se gestionarán a través de archivos `.env`, los cuales deben estar permanentemente ignorados en `.gitignore`.
- **Plantilla Base:** Debe mantenerse actualizado el archivo `.env.example` en la raíz del repositorio, conteniendo todas las variables necesarias con valores de ejemplo seguros o vacíos.

### 2. Blindaje de la Evaluación a Doble Ciego
- **Sanitización de Documentos:** Los archivos PDF subidos por los docentes deben ser despojados de metadatos de autoría y software antes de persistir en el almacenamiento permanente.
- **Protección de Datos en Vistas:** Las vistas, serializadores y plantillas del módulo `apps/reviews/` tienen estrictamente prohibido exponer identificadores o nombres de autores a los revisores.
- **Control de Acceso Basado en Roles (RBAC):** Se deben implementar validadores de permisos y decoradores que garanticen la separación tajante de privilegios entre `Docente` (Autor), `Coordinador` (Administrador/Editor) y `Revisor` (Evaluador).

---

## Gobernanza

1. **Supremacía Constitucional:** La presente Constitución prevalece sobre cualquier acuerdo verbal, convención informal o atajo técnico. Todo Pull Request que infrinja estas cláusulas será rechazado de forma concluyente.
2. **Procedimiento de Enmiendas:** Cualquier modificación a este documento requerirá la apertura de un Issue formal que justifique la necesidad técnica o institucional, seguido de un Pull Request con la aprobación del Tech Lead y del Comité Académico correspondiente.
3. **Versionado Semántico de la Constitución:**
   - **MAJOR:** Eliminación o rediseño estructural de principios fundamentales.
   - **MINOR:** Inclusión de nuevas secciones operativas, tecnologías o directrices de cumplimiento.
   - **PATCH:** Corrección de estilo, aclaraciones textuales o ajustes ortográficos.

---

**Versión**: 1.0.0 | **Ratificada**: 2026-10-15 | **Última Enmienda**: 2026-10-15
 ScientificPub