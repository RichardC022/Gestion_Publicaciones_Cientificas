"""Root URL configuration for the REST API."""

from django.urls import include, path
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.users.views import DashboardView
from config.health import HealthView


class ApiRootView(APIView):
    """Return a minimal service descriptor for the API root."""

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
    path("", ApiRootView.as_view(), name="api-root"),
    path("health/", HealthView.as_view(), name="health"),
    path("auth/", include("apps.users.urls")),
    path("dashboard/", DashboardView.as_view(), name="dashboard"),
    path("manuscripts/", include("apps.publications.urls")),
    path("catalog/", include("apps.publications.catalog_urls")),
    path("editor/", include("apps.reviews.urls")),
    path("reviewer/", include("apps.reviews.reviewer_urls")),
    path("admin/audit/", include("apps.audit.urls")),
    path("admin/verdicts/", include("apps.publications.admin_urls")),
    path("notifications/", include("apps.notifications.urls")),
]
