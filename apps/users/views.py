"""Authentication and account views for the users app.

The feature exposes session-based authentication (login, logout) and a landing
dashboard restricted to authenticated members. The login flow reuses Django's
built-in ``LoginView`` while the template renders the institutional look and
progressive role-switching surface (FR-001..FR-002).
"""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView, LogoutView
from django.urls import reverse_lazy
from django.views.generic import TemplateView


class AccountLoginView(LoginView):
    """Render the institutional login form and authenticate the member."""

    template_name = "registration/login.html"
    redirect_authenticated_user = True


class AccountLogoutView(LogoutView):
    """Close the authenticated session and return to the login screen."""

    next_page = reverse_lazy("users:login")


class DashboardView(LoginRequiredMixin, TemplateView):
    """Show the role-aware landing dashboard for authenticated members."""

    template_name = "users/dashboard.html"
