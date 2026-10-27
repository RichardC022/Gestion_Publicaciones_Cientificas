"""URL configuration of the editor endpoints (plan section 2.4)."""

from django.urls import path

from apps.reviews.views import (
    AssignmentRevokeView,
    EligibleReviewersView,
    ExpiredAssignmentsView,
    ManuscriptAssignmentsView,
    StartReviewView,
    SubmissionDetailView,
    SubmissionListView,
)

urlpatterns = [
    path("submissions/", SubmissionListView.as_view(), name="editor-submission-list"),
    path(
        "submissions/<uuid:pk>/",
        SubmissionDetailView.as_view(),
        name="editor-submission-detail",
    ),
    path(
        "submissions/<uuid:pk>/start-review/",
        StartReviewView.as_view(),
        name="editor-start-review",
    ),
    path("reviewers/", EligibleReviewersView.as_view(), name="editor-reviewers"),
    path(
        "manuscripts/<uuid:pk>/assignments/",
        ManuscriptAssignmentsView.as_view(),
        name="editor-manuscript-assignments",
    ),
    path(
        "assignments/expired/",
        ExpiredAssignmentsView.as_view(),
        name="editor-assignments-expired",
    ),
    path(
        "assignments/<uuid:pk>/revoke/",
        AssignmentRevokeView.as_view(),
        name="editor-assignment-revoke",
    ),
]
