workspace "Sistema de Gestión de Publicaciones Científicas" "Modelo C4 (niveles 1 a 3) del sistema editorial de la UNL." {

    !impliedRelationships false

    model {
        autor = person "Autor" "Registra, envía y corrige manuscritos."
        revisor = person "Revisor" "Evalúa a ciegas el manuscrito que se le asigna."
        editor = person "Editor" "Coordina el proceso, asigna al Revisor y registra el veredicto."
        admin = person "Administrador" "Consulta la auditoría y habilita correcciones de veredicto."
        publico = person "Público" "Consulta el catálogo de artículos aceptados sin iniciar sesión."

        smtp = softwareSystem "Servidor de correo institucional" "Entrega los avisos por correo electrónico." "Externo"

        gpc = softwareSystem "Sistema de Gestión de Publicaciones Científicas" "Centraliza el ciclo editorial de los manuscritos: envío, revisión doble ciego, veredicto, catálogo público y auditoría." {

            spa = container "SPA" "Interfaz web por rol: Autor, Revisor, Editor, Administrador y catálogo público." "Angular, TypeScript" "Navegador"

            web = container "Nginx" "Termina TLS, sirve la SPA, reenvía /api/, limita la carga a 60 MB y entrega los PDF por ubicaciones internas." "Nginx 1.27"

            api = container "API" "Reglas editoriales, autorización por rol y objeto, auditoría y orquestación del almacenamiento." "Python 3.12, Django 5.2, DRF, Gunicorn" {
                middleware = component "Identificador de solicitud" "Asigna X-Request-ID y lo propaga al log y a la respuesta." "Middleware de Django"
                contrato = component "Contrato JSON" "Envuelve toda respuesta en success, message, data, errors y meta; normaliza los errores." "Renderer y manejador de excepciones de DRF"
                usuarios = component "Cuentas y sesión" "Credenciales institucionales, JWT, renovación en cookie, roles y tablero." "App users"
                publicaciones = component "Manuscritos y catálogo" "Borradores, envío formal, versiones inmutables, veredictos y catálogo público." "App publications"
                revisiones = component "Revisión doble ciego" "Asignaciones, evaluaciones, conflictos de interés e incidentes confidenciales." "App reviews"
                auditoria = component "Auditoría encadenada" "Eventos inmutables con huella SHA-256 encadenada." "App audit"
                avisos = component "Avisos" "Notificaciones en el panel y por correo, con reintentos." "App notifications"
                openapi = component "Documentación OpenAPI" "Schema OpenAPI 3 y Swagger UI." "drf-spectacular"
            }

            bd = container "Base de datos" "Estado editorial, metadatos, versiones, asignaciones, evaluaciones, veredictos, auditoría y avisos." "PostgreSQL 16" "Base de datos"

            volumen = container "Volumen de PDF" "PDF originales, copias sanitizadas y copias públicas del catálogo." "Volumen Docker media_data" "Almacén"

            tareas = container "Tareas programadas" "Marca plazos vencidos, reintenta avisos, respalda y verifica la integridad." "cron del host y comandos de gestión de Django"
        }

        # Personas y sistemas externos
        autor -> spa "Registra y corrige manuscritos"
        revisor -> spa "Evalúa manuscritos asignados"
        editor -> spa "Coordina y decide"
        admin -> spa "Consulta la auditoría"
        publico -> spa "Busca y lee artículos"
        autor -> gpc "Registra y corrige manuscritos"
        revisor -> gpc "Evalúa manuscritos asignados"
        editor -> gpc "Coordina y decide"
        admin -> gpc "Consulta la auditoría"
        publico -> gpc "Busca y lee artículos"
        gpc -> smtp "Envía avisos" "SMTP"

        # Contenedores
        web -> spa "Sirve los archivos compilados" "HTTPS"
        spa -> web "Llama a la API" "HTTPS, JSON"
        web -> api "Reenvía /api/" "HTTP"
        web -> volumen "Entrega PDF ya autorizados" "X-Accel-Redirect"
        api -> bd "Lee y escribe" "SQL"
        api -> volumen "Lee y escribe PDF" "Sistema de archivos"
        api -> smtp "Envía avisos" "SMTP"
        tareas -> api "Ejecuta comandos de gestión" "manage.py"
        tareas -> bd "Respalda" "pg_dump"
        tareas -> volumen "Respalda" "tar"

        # Componentes de la API
        web -> middleware "Reenvía /api/" "HTTP"
        middleware -> contrato "Pasa la solicitud"
        contrato -> usuarios "Despacha"
        contrato -> publicaciones "Despacha"
        contrato -> revisiones "Despacha"
        contrato -> openapi "Sirve la documentación"
        usuarios -> auditoria "Audita sesiones"
        publicaciones -> auditoria "Audita acciones críticas"
        revisiones -> auditoria "Audita acciones críticas"
        revisiones -> publicaciones "Lee manuscritos y versiones"
        publicaciones -> avisos "Emite eventos"
        revisiones -> avisos "Emite eventos"
        avisos -> smtp "Envía correo" "SMTP"
        usuarios -> bd "Lee y escribe" "SQL"
        publicaciones -> bd "Lee y escribe" "SQL"
        revisiones -> bd "Lee y escribe" "SQL"
        auditoria -> bd "Escribe la cadena" "SQL"
        avisos -> bd "Lee y escribe" "SQL"
        publicaciones -> volumen "Guarda y lee PDF" "Sistema de archivos"
    }

    views {
        systemContext gpc "c1-contexto" "C1 · Contexto del sistema" {
            include *
            autolayout lr
        }

        container gpc "c2-contenedores" "C2 · Contenedores" {
            include *
            autolayout lr
        }

        component api "c3-backend" "C3 · Componentes del backend" {
            include *
            autolayout lr
        }

        styles {
            element "Person" {
                shape person
                background #08427b
                color #ffffff
            }
            element "Software System" {
                background #1168bd
                color #ffffff
            }
            element "Externo" {
                background #8a8a8a
                color #ffffff
            }
            element "Container" {
                background #438dd5
                color #ffffff
            }
            element "Component" {
                background #85bbf0
                color #000000
            }
            element "Navegador" {
                shape webbrowser
            }
            element "Base de datos" {
                shape cylinder
            }
            element "Almacén" {
                shape folder
            }
        }
    }
}
