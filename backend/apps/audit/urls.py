"""URL configuration of the administrator audit endpoints (plan section 2.7)."""

from django.urls import path

from apps.audit.views import AuditDetailView, AuditListView

urlpatterns = [
    path("", AuditListView.as_view(), name="admin-audit-list"),
    path("<uuid:pk>/", AuditDetailView.as_view(), name="admin-audit-detail"),
]
