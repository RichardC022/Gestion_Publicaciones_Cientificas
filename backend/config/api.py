"""Root URL configuration for the REST API."""

from django.http import HttpRequest, JsonResponse
from django.urls import include, path

from apps.users.views import DashboardView
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
    path("dashboard/", DashboardView.as_view(), name="dashboard"),
    path("manuscripts/", include("apps.publications.urls")),
    path("catalog/", include("apps.publications.catalog_urls")),
    path("editor/", include("apps.reviews.urls")),
    path("reviewer/", include("apps.reviews.reviewer_urls")),
    path("admin/audit/", include("apps.audit.urls")),
    path("notifications/", include("apps.notifications.urls")),
]
