import { ParamMap } from '@angular/router';

/**
 * Catálogo público (plan secciones 2.6 y 3.5, HU-18/HU-19).
 *
 * Es una lista blanca de lo que cualquier visitante puede ver de un
 * artículo aceptado: autores con su filiación (sin correo), resumen,
 * palabras clave, área, idioma, fecha de publicación y versión. Nunca
 * hay evaluaciones, revisores, historial ni auditoría.
 */
export interface PublicAuthor {
  full_name: string;
  affiliation: string;
}

export interface CatalogArticle {
  code: string;
  title: string;
  authors: PublicAuthor[];
  abstract: string;
  keywords: string[];
  area: string;
  language: string;
  published_at: string;
  version_number: number;
  /** Ruta de la API del PDF público; la SPA la pide sin credenciales. */
  document_url: string;
}

/** Filtros combinables del catálogo; todos opcionales. */
export interface CatalogFilters {
  search?: string;
  area?: string;
  language?: string;
  keyword?: string;
  date_from?: string;
  date_to?: string;
  ordering?: CatalogOrdering;
}

export const CATALOG_ORDERINGS = [
  { value: '-published_at', label: 'Más recientes' },
  { value: 'published_at', label: 'Más antiguos' },
  { value: 'title', label: 'Título (A-Z)' },
  { value: '-title', label: 'Título (Z-A)' },
] as const;

export type CatalogOrdering = (typeof CATALOG_ORDERINGS)[number]['value'];

export const DEFAULT_CATALOG_ORDERING: CatalogOrdering = '-published_at';

/** Idiomas que ofrece el filtro (código ISO 639-1, como los guarda el backend). */
export const CATALOG_LANGUAGES = [
  { value: 'es', label: 'Español' },
  { value: 'en', label: 'Inglés' },
  { value: 'pt', label: 'Portugués' },
  { value: 'fr', label: 'Francés' },
] as const;

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
const LANGUAGE = /^[a-z]{2}$/;
const TEXT_LIMITS = { search: 200, area: 120, keyword: 100 } as const;

export function languageLabel(code: string): string {
  return CATALOG_LANGUAGES.find((option) => option.value === code)?.label ?? code.toUpperCase();
}

/**
 * Filtros de la URL. Un valor manipulado a mano que el backend rechazaría
 * (`400`) se descarta aquí, de modo que una URL editada nunca rompe la vista.
 */
export function toCatalogFilters(params: ParamMap): CatalogFilters {
  const filters: CatalogFilters = {};
  for (const key of ['search', 'area', 'keyword'] as const) {
    const value = (params.get(key) ?? '').trim();
    if (value && value.length <= TEXT_LIMITS[key]) {
      filters[key] = value;
    }
  }
  const language = params.get('language');
  if (language && LANGUAGE.test(language)) {
    filters.language = language;
  }
  const dateFrom = params.get('date_from');
  const dateTo = params.get('date_to');
  if (dateFrom && ISO_DATE.test(dateFrom)) {
    filters.date_from = dateFrom;
  }
  if (dateTo && ISO_DATE.test(dateTo)) {
    filters.date_to = dateTo;
  }
  if (filters.date_from && filters.date_to && filters.date_from > filters.date_to) {
    delete filters.date_to;
  }
  const ordering = params.get('ordering');
  if (CATALOG_ORDERINGS.some((option) => option.value === ordering) && ordering !== DEFAULT_CATALOG_ORDERING) {
    filters.ordering = ordering as CatalogOrdering;
  }
  return filters;
}

/** Hay algún filtro aplicado (el orden no cuenta como filtro). */
export function hasCatalogFilters(filters: CatalogFilters): boolean {
  return Object.keys(filters).some((key) => key !== 'ordering');
}
