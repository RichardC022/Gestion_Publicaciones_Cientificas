"""URL configuration of the manuscript endpoints (plan section 2.3)."""

from django.urls import path

from apps.publications.views import ManuscriptDetailView, ManuscriptListCreateView

urlpatterns = [
    path("", ManuscriptListCreateView.as_view(), name="manuscript-list"),
    path("<uuid:pk>/", ManuscriptDetailView.as_view(), name="manuscript-detail"),
]
