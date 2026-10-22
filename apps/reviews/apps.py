"""Application configuration for the reviews app."""

from django.apps import AppConfig


class ReviewsConfig(AppConfig):
    """Configuration for blind peer review and editorial verdicts."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.reviews"
    verbose_name = "Reviews"
