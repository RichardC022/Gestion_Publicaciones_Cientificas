"""Admin registration for the reviews app."""

from django.contrib import admin

from apps.reviews.models import Evaluation, ReviewAssignment, ReviewVerdict


class EvaluationInline(admin.StackedInline):
    """Inline exposing the evaluation attached to an assignment."""

    model = Evaluation
    extra = 0


@admin.register(ReviewAssignment)
class ReviewAssignmentAdmin(admin.ModelAdmin):
    """Admin view for review assignments."""

    list_display = ("manuscript", "reviewer", "status", "due_date", "created_at")
    list_filter = ("status",)
    inlines = (EvaluationInline,)


@admin.register(ReviewVerdict)
class ReviewVerdictAdmin(admin.ModelAdmin):
    """Admin view for editorial verdicts."""

    list_display = ("manuscript", "decision", "decided_by", "created_at")
    list_filter = ("decision",)
