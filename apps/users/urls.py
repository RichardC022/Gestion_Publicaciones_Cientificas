"""URL configuration for the users app.

Exposes session-based authentication (login/logout) and the authenticated
dashboard. REST endpoints for role switching are specified in a later feature.
"""

from django.urls import path

from apps.users import views

app_name = "users"

urlpatterns = [
    path("login/", views.AccountLoginView.as_view(), name="login"),
    path("logout/", views.AccountLogoutView.as_view(), name="logout"),
    path("dashboard/", views.DashboardView.as_view(), name="dashboard"),
]
