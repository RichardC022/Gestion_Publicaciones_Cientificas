"""Admin registration for the publications app."""

from django.contrib import admin

from apps.publications.models import (
    Author,
    Category,
    Manuscript,
    ManuscriptVersion,
    ResearchArea,
)


class ManuscriptVersionInline(admin.TabularInline):
    """Inline listing of the immutable versions of a manuscript."""

    model = ManuscriptVersion
    extra = 0
    readonly_fields = ("created_at", "updated_at")


class AuthorInline(admin.TabularInline):
    """Inline listing of the authorship metadata of a manuscript."""

    model = Author
    extra = 0


@admin.register(Manuscript)
class ManuscriptAdmin(admin.ModelAdmin):
    """Admin view for the manuscript model."""

    list_display = ("title", "author", "status", "research_area", "created_at")
    list_filter = ("status", "research_area", "language")
    search_fields = ("title", "keywords")
    inlines = (ManuscriptVersionInline, AuthorInline)


@admin.register(ResearchArea)
class ResearchAreaAdmin(admin.ModelAdmin):
    """Admin view for research areas."""

    list_display = ("name", "code")
    search_fields = ("name", "code")


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    """Admin view for categories."""

    list_display = ("name", "research_area")
    list_filter = ("research_area",)
