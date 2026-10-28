import { Paginated } from '../../../core/models/paginated.model';
import {
  ReviewerAssignmentDetail,
  ReviewerAssignmentRow,
} from '../../../core/models/reviewer.model';

/** Datos de ejemplo del módulo Revisor para las pruebas. */
export function buildAssignmentRow(
  overrides: Partial<ReviewerAssignmentRow> = {},
): ReviewerAssignmentRow {
  return {
    id: 'a-1',
    manuscript_code: 'GPC-2026-000001',
    manuscript_title: 'Efecto del clima en cultivos andinos',
    area: 'Agronomía',
    version_number: 1,
    round_number: 0,
    assigned_at: '2026-10-21T15:00:00Z',
    due_at: '2026-11-10T15:00:00Z',
    status: 'ACTIVE',
    state: 'PENDING',
    is_overdue: false,
    completed_at: null,
    ...overrides,
  };
}

export function buildAssignmentPage(
  results: ReviewerAssignmentRow[],
  count: number = results.length,
): Paginated<ReviewerAssignmentRow> {
  return { count, next: null, previous: null, results };
}

export function buildAssignmentDetail(
  overrides: Partial<ReviewerAssignmentDetail> = {},
): ReviewerAssignmentDetail {
  return {
    ...buildAssignmentRow(),
    manuscript: {
      id: 's-1',
      code: 'GPC-2026-000001',
      title: 'Efecto del clima en cultivos andinos',
      abstract: 'Resumen del estudio de campo.',
      keywords: ['clima', 'cultivos'],
      area: 'Agronomía',
      language: 'es',
      current_round: 0,
      current_version: 1,
    },
    version: { version_number: 1, round_number: 0, submitted_at: '2026-10-20T15:30:00Z' },
    document_url: '/api/reviewer/assignments/a-1/document/',
    ...overrides,
  };
}
