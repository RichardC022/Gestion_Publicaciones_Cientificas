"""Presentation views for the shared core app.

These views only assemble demo context for the frontend prototype. They do not
read from or write to the database; the real audit and landing data sources will
replace the demo module once the backend services are connected.
"""

from __future__ import annotations

from typing import Any

from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import render
from django.views.generic import TemplateView

from apps.core import demo_data


class HomeView(TemplateView):
    """Render the public institutional landing page."""

    template_name = "pages/home.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        """Add the landing content and highlighted publications."""
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "stats": demo_data.STATS,
                "areas": demo_data.RESEARCH_AREAS,
                "features": demo_data.FEATURES,
                "workflow_steps": demo_data.WORKFLOW_STEPS,
                "faq": demo_data.FAQ,
                "featured_articles": demo_data.featured_articles(),
            }
        )
        return context


class AuditLogView(LoginRequiredMixin, TemplateView):
    """Render the read-only audit trail prototype."""

    template_name = "core/audit.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        """Expose demo events and the available action filters."""
        context = super().get_context_data(**kwargs)
        actions = sorted(
            {
                (event["action"], event["action_label"])
                for event in demo_data.AUDIT_EVENTS
            }
        )
        context.update(
            {
                "events": demo_data.AUDIT_EVENTS,
                "actions": [label for _, label in actions],
                "stats": [
                    {
                        "value": "128",
                        "label": "Eventos esta semana",
                        "icon": "activity",
                        "tone": "blue",
                    },
                    {
                        "value": "7",
                        "label": "Acciones críticas hoy",
                        "icon": "shield",
                        "tone": "gold",
                    },
                    {
                        "value": "24",
                        "label": "Actores registrados",
                        "icon": "users",
                        "tone": "green",
                    },
                ],
            }
        )
        return context


def error_403(request: Any, exception: Exception) -> Any:
    """Render the friendly forbidden page."""
    return render(request, "errors/403.html", status=403)


def error_404(request: Any, exception: Exception) -> Any:
    """Render the friendly not-found page."""
    return render(request, "errors/404.html", status=404)


def error_500(request: Any) -> Any:
    """Render the friendly server-error page."""
    return render(request, "errors/500.html", status=500)
