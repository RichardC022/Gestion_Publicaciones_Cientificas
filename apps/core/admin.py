"""Admin registration for the shared core app."""

from django.contrib import admin

from apps.core.models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """Read-only admin view for the immutable audit trail."""

    list_display = ("created_at", "action", "entity_type", "entity_id", "actor")
    list_filter = ("action", "entity_type")
    search_fields = ("entity_id", "description")
    readonly_fields = (
        "actor",
        "action",
        "entity_type",
        "entity_id",
        "description",
        "metadata",
        "created_at",
    )

    def has_add_permission(self, request) -> bool:
        """Disable manual creation of audit entries from the admin."""
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        """Disable editing of audit entries from the admin."""
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        """Disable deletion of audit entries from the admin."""
        return False
