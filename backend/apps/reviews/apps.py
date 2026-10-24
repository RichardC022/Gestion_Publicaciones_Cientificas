"""Reviews application configuration."""

from django.apps import AppConfig


class ReviewsConfig(AppConfig):
    """Reviewer assignments, evaluations, and confidential incidents domain."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.reviews"
    label = "reviews"
    verbose_name = "Reviews"
