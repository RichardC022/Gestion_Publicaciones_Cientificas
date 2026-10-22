# CONSTITUCIÓN DEL PROYECTO: Sistema de Gestión de Publicaciones Científicas

## 1. Arquitectura y Estructura del Sistema
*   **Arquitectura:** Cliente-Servidor (SPA + API REST).
*   **Estructura de Carpetas:** El repositorio DEBE mantener un aislamiento estricto con dos directorios en la raíz: `/backend` y `/frontend`.
*   **Contenedorización:** Es OBLIGATORIO que todo el entorno se orqueste mediante Docker y `docker-compose`.

## 2. Stack Tecnológico Restrictivo
*   **Backend:** Python con Django y Django REST Framework (DRF). Ningún otro framework está permitido.
*   **Frontend:** Angular (TypeScript).
*   **Base de Datos:** PostgreSQL. Prohibido usar SQLite, MySQL o MongoDB.

## 3. Principios de Ingeniería y Código (Agentic Guidelines)
*   **Idioma:** Todo el código fuente (clases, variables, endpoints) DEBE estar en Inglés. Los comentarios, documentación y *commits* DEBEN estar en Español.
*   **Calidad de Código:** El agente debe aplicar estrictamente los principios SOLID, KISS (mantenerlo simple), DRY (no repetir código) y YAGNI (no implementar funciones futuras no solicitadas).
*   **Documentación:** El proyecto debe incluir un `README.md` exhaustivo que explique paso a paso cómo levantar los contenedores de Docker, realizar las migraciones y ejecutar el sistema.

## 4. Interfaz de Usuario (UI/UX)
*   **Diseño:** Las vistas en Angular deben ser limpias, intuitivas y con una paleta de colores cómoda para lectura prolongada.
*   **Semántica Visual:** 
    *   Verde: Acciones exitosas o de guardado.
    *   Amarillo: Advertencias.
    *   Rojo: Acciones destructivas (rechazar, eliminar).
    *   Azul/Gris: Acciones neutras o de navegación.

## 5. Reglas de Negocio Inquebrantables (Core)
*   **Privacidad "Doble Ciego":** REGLA ESTRICTA. A nivel de DRF (Serializadores y Vistas), si el token JWT pertenece a un "Revisor", el JSON de respuesta NUNCA debe incluir nombres, correos o filiación del "Autor".
*   **Manejo de Archivos:** Validación estricta en Angular y Django para aceptar ÚNICAMENTE archivos `.pdf`.
*   **Control de Versiones (Versioning):** Las nuevas versiones de un documento subidas por el autor NUNCA deben sobrescribir los PDFs anteriores. El sistema debe mantener el historial intacto.
*   **Integridad de Datos:** Prohibido usar `DELETE` directo en la base de datos para los manuscritos; usar borrado lógico (`is_active = False`).