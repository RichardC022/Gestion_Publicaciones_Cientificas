"""Admin registration for the users app."""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from apps.users.models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    """Admin view exposing the project's custom user fields."""

    list_display = (
        "username",
        "email",
        "active_role",
        "is_reviewer_enabled",
        "is_editor_enabled",
        "is_active",
    )
    list_filter = (
        "active_role",
        "is_reviewer_enabled",
        "is_editor_enabled",
        "is_admin_enabled",
        "is_active",
    )
    fieldsets = DjangoUserAdmin.fieldsets + (
        (
            "Institutional roles",
            {
                "fields": (
                    "document_id",
                    "active_role",
                    "is_author_enabled",
                    "is_reviewer_enabled",
                    "is_editor_enabled",
                    "is_admin_enabled",
                )
            },
        ),
    )
