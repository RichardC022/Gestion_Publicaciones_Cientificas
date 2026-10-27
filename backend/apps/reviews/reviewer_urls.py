"""URL configuration of the reviewer endpoints (plan section 2.5)."""

from django.urls import path

from apps.reviews.views import (
    ReviewerAssignmentDetailView,
    ReviewerAssignmentDocumentView,
    ReviewerAssignmentListView,
)

urlpatterns = [
    path(
        "assignments/",
        ReviewerAssignmentListView.as_view(),
        name="reviewer-assignment-list",
    ),
    path(
        "assignments/<uuid:pk>/",
        ReviewerAssignmentDetailView.as_view(),
        name="reviewer-assignment-detail",
    ),
    path(
        "assignments/<uuid:pk>/document/",
        ReviewerAssignmentDocumentView.as_view(),
        name="reviewer-assignment-document",
    ),
]
