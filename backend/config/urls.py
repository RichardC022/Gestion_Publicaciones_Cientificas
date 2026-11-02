"""Root URL configuration for the Django project."""

from django.conf import settings
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("api/", include("config.api")),
]

# D-31: el Django Admin solo se monta cuando el entorno lo habilita (desarrollo). En producción
# `/admin/` no existe: Django responde 404, igual que Nginx, que ni siquiera lo reenvía.
if settings.ADMIN_ENABLED:
    urlpatterns.insert(0, path("admin/", admin.site.urls))
