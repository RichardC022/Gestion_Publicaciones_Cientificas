import { CatalogArticle } from '../../../core/models/catalog.model';
import { Paginated } from '../../../core/models/paginated.model';

/** Datos de ejemplo del catálogo público para las pruebas. */
export function buildArticle(overrides: Partial<CatalogArticle> = {}): CatalogArticle {
  return {
    code: 'GPC-2026-000001',
    title: 'Glaciares tropicales del Chimborazo',
    authors: [
      { full_name: 'Ana Lucía Torres', affiliation: 'Universidad Nacional de Loja' },
      { full_name: 'Bruno Díaz', affiliation: 'UTPL' },
    ],
    abstract: 'Estudio del retroceso glaciar entre 2000 y 2025.',
    keywords: ['glaciares', 'clima'],
    area: 'Agronomía',
    language: 'es',
    published_at: '2026-10-22T15:00:00Z',
    version_number: 1,
    document_url: '/api/catalog/GPC-2026-000001/document/',
    ...overrides,
  };
}

export function buildArticlePage(
  results: CatalogArticle[],
  count: number = results.length,
): Paginated<CatalogArticle> {
  return { count, next: null, previous: null, results };
}
