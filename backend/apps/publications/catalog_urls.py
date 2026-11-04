"""URL configuration of the public catalog endpoints (plan section 2.6)."""

from django.urls import path

from apps.publications.catalog_views import CatalogDetailView, CatalogDocumentView, CatalogListView

urlpatterns = [
    path("", CatalogListView.as_view(), name="catalog-list"),
    path("<str:code>/", CatalogDetailView.as_view(), name="catalog-detail"),
    path("<str:code>/document/", CatalogDocumentView.as_view(), name="catalog-document"),
]
