# Sistema de Gestión de Publicaciones Científicas (ScientificPub UNL)

## 1. Descripción del Proyecto

La Universidad Nacional de Loja (UNL) carece de un sistema centralizado para registrar, categorizar y gestionar los artículos científicos de estudiantes que ya han sido publicados. Este proyecto busca desarrollar una plataforma que permita el registro de estas publicaciones finalizadas, la validación de sus metadatos por parte de gestores y un catálogo de búsqueda unificado, evitando la pérdida de trazabilidad y facilitando la búsqueda de antecedentes académicos.

### Propósito
Este proyecto busca proporcionar una solución ágil y moderna, orientada a coordinar y automatizar el ciclo de vida de publicaciones digitales, facilitando la colaboración entre redactores, revisores y editores mediante la trazabilidad integral de cambios y la gestión centralizada de perfiles de autor.

### Problema Resuelto
- **Desafío:** Los flujos editoriales tradicionales presentan cuellos de botella por la falta de visibilidad en el estado de los borradores, revisiones concurrentes sobre un mismo documento sin control de cambios adecuado y pérdida de autoría original tras múltiples correcciones.
- **Solución:** Implementación de un motor de flujo editorial con estados de aprobación definidos (Borrador, En Revisión, Aprobado, Publicado), auditoría de cambios por versión y asignación transparente de roles y atributos de autores para cada publicación.

## 2. Equipo de Trabajo y Roles
Este proyecto es desarrollado por los siguientes estudiantes de la Carrera de Computación:

* **Jostin Vasquez:** Coordinadora del grupo y Lógica del servidor (Backend).
* **Richard Cajas:** Encargado del repositorio (Git) y configuración del entorno.
* **Gyna Yupangi:** Encargado de las vistas y diseño de pantallas (Frontend).
* **Miguel Veintimilla:** Responsable de la Base de Datos y pruebas de funcionamiento.
* **Ismael Gonzalez:** Responsable de documentación SDD (Spec-Kit) y apoyo en programación.

## 3. Tecnologías utilizadas

- **Backend:** Python 3.11+, Django 5.1.15
- **Base de Datos:** MySQL
- **Contenedores y DevOps:** Docker, Docker Compose
- **Documentación & Especificaciones:** Spec Kit (Metodología SDD)
- **Otras Herramientas:** Git, VS Code

## 4. Instalación

### Requisitos previos
- Python (3.10+)
- Git
- Docker con Docker Compose habilitado

### Instalación y Ejecución

1. **Clonar el repositorio:**
   ```bash
   git clone https://github.com/RichardC022/Gestion_Publicaciones_Cientificas.git
   cd Gestion_Publicaciones_Cientificas
   ```

2. **Configurar variables de entorno:**
   Copia la plantilla y ajusta los valores (contraseñas y `SECRET_KEY`):
   ```bash
   cp .env.example .env
   ```
   En Windows (PowerShell): `Copy-Item .env.example .env`.

3. **Desplegar los contenedores:**
   ```bash
   docker compose up -d --build
   ```

## 5. Uso

### Comandos de ejecución principal

1. **Levantar los servicios en segundo plano:**
   ```bash
   docker compose up -d
   ```

2. **Ejecutar migraciones de la BD:**
   ```bash
   docker compose exec web python manage.py migrate
   ```

3. **Crear un superusuario (Admin):**
   ```bash
   docker compose exec web python manage.py createsuperuser
   ```

4. **Detener los servicios:**
   ```bash
   docker compose down
   ```

### Acceso a las plataformas

1. **Panel de Django:** http://localhost:8000/admin
2. **App Web:** http://localhost:8000/

## 6. Estructura del proyecto

```bash
Proyecto_GPC/
├── .spec-kit/
│   ├── constitution.md
│   ├── specify.md
│   ├── clarify.md
│   └── plan.md
├── config/
│   ├── __init__.py
│   ├── asgi.py
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── apps/
│   ├── __init__.py
│   ├── users/
│   │   ├── migrations/
│   │   │   └── __init__.py
│   │   ├── __init__.py
│   │   ├── admin.py
│   │   ├── apps.py
│   │   ├── models.py
│   │   ├── serializers.py
│   │   ├── urls.py
│   │   └── views.py
│   ├── publications/
│   │   ├── migrations/
│   │   │   └── __init__.py
│   │   ├── __init__.py
│   │   ├── admin.py
│   │   ├── apps.py
│   │   ├── models.py
│   │   ├── serializers.py
│   │   ├── urls.py
│   │   └── views.py
│   └── reviews/
│       ├── migrations/
│       │   └── __init__.py
│       ├── __init__.py
│       ├── admin.py
│       ├── apps.py
│       ├── models.py
│       ├── serializers.py
│       ├── urls.py
│       └── views.py
├── dossier/
│   ├── dossier_requisitos.md
│   └── Requisitos.pdf
├── media/
├── static/
├── .dockerignore
├── .gitignore
├── docker-compose.yml
├── Dockerfile
├── manage.py
├── requirements.txt
└── README.md
```

## 7. Información adicional

1. **Metodología de Desarrollo:**
   Specification-Driven Development (SDD) utilizando la estructura de Spec Kit.

2. **Estrategia de ramas en Git:**
   - **main:** Producción
   - **develop:** Rama de integración principal
   - **dev/'integrante'-setup:** Ramas de características para desarrollo de nuevas funcionalidades por cada integrante.
