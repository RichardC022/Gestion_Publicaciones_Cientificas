"""Root URL configuration for the REST API."""

from django.http import HttpRequest, JsonResponse
from django.urls import include, path

from config.health import HealthView


def api_root(request: HttpRequest) -> JsonResponse:
    """Return a minimal service descriptor for the API root."""
    return JsonResponse(
        {
            "service": "gestion-publicaciones-cientificas",
            "api": "v1",
        }
    )


urlpatterns = [
    path("", api_root, name="api-root"),
    path("health/", HealthView.as_view(), name="health"),
    path("auth/", include("apps.users.urls")),
]
