"""URL configuration of the manuscript endpoints (plan section 2.3)."""

from django.urls import path

from apps.publications.views import (
    ManuscriptDetailView,
    ManuscriptDraftFileView,
    ManuscriptHistoryView,
    ManuscriptListCreateView,
    ManuscriptSubmitView,
    ManuscriptVersionFileView,
    ManuscriptVersionsView,
    ManuscriptWithdrawView,
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
    path(
        "<uuid:pk>/versions/",
        ManuscriptVersionsView.as_view(),
        name="manuscript-versions",
    ),
    path(
        "<uuid:pk>/versions/<uuid:version_id>/file/",
        ManuscriptVersionFileView.as_view(),
        name="manuscript-version-file",
    ),
    path(
        "<uuid:pk>/history/",
        ManuscriptHistoryView.as_view(),
        name="manuscript-history",
    ),
    path(
        "<uuid:pk>/withdraw/",
        ManuscriptWithdrawView.as_view(),
        name="manuscript-withdraw",
    ),
]
