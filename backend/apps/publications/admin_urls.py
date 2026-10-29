"""URL configuration of the administrator verdict endpoints (plan section 2.7)."""

from django.urls import path

from apps.publications.admin_views import AuthorizeCorrectionView

urlpatterns = [
    path(
        "<uuid:pk>/authorize-correction/",
        AuthorizeCorrectionView.as_view(),
        name="admin-verdict-authorize-correction",
    ),
]
