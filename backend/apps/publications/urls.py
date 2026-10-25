"""URL configuration of the manuscript endpoints (plan section 2.3)."""

from django.urls import path

from apps.publications.views import (
    ManuscriptDetailView,
    ManuscriptDraftFileView,
    ManuscriptListCreateView,
    ManuscriptSubmitView,
)

urlpatterns = [
    path("", ManuscriptListCreateView.as_view(), name="manuscript-list"),
    path("<uuid:pk>/", ManuscriptDetailView.as_view(), name="manuscript-detail"),
    path(
        "<uuid:pk>/draft-file/",
        ManuscriptDraftFileView.as_view(),
        name="manuscript-draft-file",
    ),
    path(
        "<uuid:pk>/submit/",
        ManuscriptSubmitView.as_view(),
        name="manuscript-submit",
    ),
]
