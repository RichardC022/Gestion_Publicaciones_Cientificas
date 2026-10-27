import { Manuscript, ManuscriptAuthor } from '../../../core/models/manuscript.model';
import { Paginated } from '../../../core/models/paginated.model';

/** Datos de ejemplo del módulo Autor para las pruebas. */
export const AUTHOR_ANA: ManuscriptAuthor = {
  full_name: 'Ana López',
  email: 'a.lopez@unl.edu.ec',
  affiliation: 'Universidad Nacional de Loja',
  is_corresponding: true,
  author_order: 1,
};

export const AUTHOR_LUIS: ManuscriptAuthor = {
  full_name: 'Luis Pérez',
  email: 'luis@otra.edu',
  affiliation: 'Otra Universidad',
  is_corresponding: false,
  author_order: 2,
};

export function buildManuscript(overrides: Partial<Manuscript> = {}): Manuscript {
  return {
    id: 'm-1',
    code: 'GPC-2026-000001',
    title: 'Efecto del clima en cultivos andinos',
    abstract: 'Resumen del estudio de campo.',
    keywords: ['clima', 'cultivos'],
    area: 'Agronomía',
    language: 'es',
    status: 'DRAFT',
    current_round: 0,
    current_version: 0,
    is_active: true,
    withdrawn_at: null,
    withdrawal_reason: null,
    authors: [{ ...AUTHOR_ANA }],
    draft_file: null,
    created_at: '2026-10-20T15:30:00Z',
    updated_at: '2026-10-21T01:45:00Z',
    ...overrides,
  };
}

export function buildPage(
  results: Manuscript[],
  count: number = results.length,
): Paginated<Manuscript> {
  return { count, next: null, previous: null, results };
}

/** Envelope de error del backend (plan sección 2.1). */
export function errorEnvelope(code: string, message: string, details: unknown = {}) {
  return { error: { code, message, details, request_id: 'rid-1' } };
}
