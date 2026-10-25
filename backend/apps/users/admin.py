"""Django Admin integration for the users domain.

Django Admin remains an operational support tool: it is used for
institutional provisioning (accounts and roles), never for the editorial
workflow.
"""

from __future__ import annotations

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from apps.users.models import LoginAttempt, ReviewerProfile, Role, User, UserRole


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    """Operative view of institutional accounts."""

    list_display = (
        "institutional_id",
        "username",
        "email",
        "first_name",
        "last_name",
        "is_active",
        "is_staff",
    )
    list_filter = ("is_active", "is_staff")
    search_fields = ("institutional_id", "username", "email", "first_name", "last_name")
    ordering = ("institutional_id",)
    fieldsets = (
        (None, {"fields": ("institutional_id", "username", "password")}),
        ("Información personal", {"fields": ("first_name", "last_name", "email")}),
        (
            "Permisos",
            {"fields": ("is_active", "is_staff", "is_superuser", "groups")},
        ),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("institutional_id", "username", "email", "password1", "password2"),
            },
        ),
    )


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "name")


@admin.register(UserRole)
class UserRoleAdmin(admin.ModelAdmin):
    """Historical role assignments, managed for provisioning only."""

    list_display = ("user", "role", "is_active", "assigned_at", "revoked_at")
    list_filter = ("is_active", "role")
    search_fields = ("user__username", "user__institutional_id", "role__code")
    autocomplete_fields = ("user", "role", "assigned_by", "revoked_by")


@admin.register(ReviewerProfile)
class ReviewerProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "is_available", "max_active_assignments")
    list_filter = ("is_available",)
    search_fields = ("user__username", "user__institutional_id")
    autocomplete_fields = ("user",)


@admin.register(LoginAttempt)
class LoginAttemptAdmin(admin.ModelAdmin):
    """Read-only support view: identifiers are kept, passwords never."""

    list_display = ("identifier", "successful", "attempted_at", "ip_address")
    list_filter = ("successful",)
    search_fields = ("identifier",)
    date_hierarchy = "attempted_at"

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False
