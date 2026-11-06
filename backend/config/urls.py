"""Root URL configuration for the Django project."""

from django.conf import settings
from django.contrib import admin
from django.urls import include, path

from config.health import UnversionedHealthView

# Respuestas 404 y 500 de la API en JSON con el contrato universal.
handler404 = "config.exceptions.not_found_handler"
handler500 = "config.exceptions.server_error_handler"

urlpatterns = [
    path("api/v1/", include("config.api")),
    # Alias sin versión: lo usan el healthcheck de Docker y los scripts de operación,
    # que no deben cambiar cuando la API cambie de versión.
    path("api/health/", UnversionedHealthView.as_view(), name="health-unversioned"),
]

# D-31: el Django Admin solo se monta cuando el entorno lo habilita (desarrollo). En producción
# `/admin/` no existe: Django responde 404, igual que Nginx, que ni siquiera lo reenvía.
if settings.ADMIN_ENABLED:
    urlpatterns.insert(0, path("admin/", admin.site.urls))
