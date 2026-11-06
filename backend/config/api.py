"""Rutas de la API REST (todo lo que cuelga de ``/api/v1/``).

Aquí se montan las rutas de cada módulo (``users``, ``publications``, ``reviews``, ``audit`` y
``notifications``) y, solo si el entorno lo habilita (``API_DOCS_ENABLED``), la documentación
OpenAPI y Swagger UI.
"""

from django.conf import settings
from django.urls import include, path
from drf_spectacular.utils import extend_schema, extend_schema_view, inline_serializer
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerSplitView,
    SpectacularYAMLAPIView,
)
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.users.views import DashboardView
# Import por efecto secundario: al cargarse, ``config.openapi`` registra la extensión que
# documenta la autenticación Bearer JWT en el schema. Es redundante hoy (las vistas también
# importan ``config.openapi``) pero se deja explícito: no quitarlo sin revisar test_openapi.
from config import openapi as _openapi  # noqa: F401
from config.health import HealthView


@extend_schema_view(
    get=extend_schema(
        tags=["Sistema"],
        operation_id="api_root",
        summary="Descriptor del servicio",
        responses={
            200: inline_serializer(
                "ApiRoot",
                {
                    "service": serializers.CharField(read_only=True),
                    "api": serializers.CharField(read_only=True),
                },
            )
        },
        auth=[],
    ),
)
class ApiRootView(APIView):
    """Descriptor mínimo del servicio (nombre y versión de la API).

    Es público y no consulta la base de datos; sirve para comprobar que la API responde.
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        return Response(
            {
                "service": "gestion-publicaciones-cientificas",
                "api": "v1",
            }
        )


urlpatterns = [
    # Sistema: descriptor del servicio y estado de salud (públicos).
    path("", ApiRootView.as_view(), name="api-root"),
    path("health/", HealthView.as_view(), name="health"),
    # Sesión y tablero de cualquier usuario autenticado.
    path("auth/", include("apps.users.urls")),
    path("dashboard/", DashboardView.as_view(), name="dashboard"),
    # Autor: manuscritos propios. Público: catálogo de artículos aceptados.
    path("manuscripts/", include("apps.publications.urls")),
    path("catalog/", include("apps.publications.catalog_urls")),
    # Un prefijo por rol: Editor y Revisor.
    path("editor/", include("apps.reviews.urls")),
    path("reviewer/", include("apps.reviews.reviewer_urls")),
    # Administrador: auditoría y habilitación de correcciones de veredicto.
    path("admin/audit/", include("apps.audit.urls")),
    path("admin/verdicts/", include("apps.publications.admin_urls")),
    # Avisos del usuario autenticado.
    path("notifications/", include("apps.notifications.urls")),
]

# Documentación interactiva: solo cuando el entorno la habilita (`API_DOCS_ENABLED`). Apagada,
# estas rutas no existen y responden 404. Son públicas: describen la API, no exponen datos.
if settings.API_DOCS_ENABLED:
    urlpatterns += [
        path("schema/", SpectacularYAMLAPIView.as_view(), name="api-schema"),
        path("schema.json", SpectacularAPIView.as_view(), name="api-schema-json"),
        # La variante «split» sirve el HTML y el JS por separado: no hay `<script>` en línea
        # y la CSP `script-src 'self'` de Nginx se mantiene sin excepciones.
        path(
            "docs/",
            SpectacularSwaggerSplitView.as_view(url_name="api-schema"),
            name="api-docs",
        ),
    ]
