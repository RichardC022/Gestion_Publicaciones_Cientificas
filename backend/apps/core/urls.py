"""URL configuration for the shared core app."""

from django.urls import path

from apps.core import views

app_name = "core"

urlpatterns = [
    path("", views.HomeView.as_view(), name="home"),
    path("auditoria/", views.AuditLogView.as_view(), name="audit"),
]
