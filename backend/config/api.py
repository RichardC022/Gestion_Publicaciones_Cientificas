"""Root URL configuration for the REST API."""

from django.http import HttpRequest, JsonResponse
from django.urls import path


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
]
