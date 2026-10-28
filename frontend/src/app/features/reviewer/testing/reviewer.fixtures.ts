import { Paginated } from '../../../core/models/paginated.model';
import {
  ReviewerAssignmentDetail,
  ReviewerAssignmentRow,
  ReviewerEvaluation,
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

/** Evaluación propia del Revisor; por defecto, el borrador vacío anterior al primer guardado. */
export function buildReviewerEvaluation(
  overrides: Partial<ReviewerEvaluation> = {},
): ReviewerEvaluation {
  return {
    id: null,
    status: 'DRAFT',
    originality_score: null,
    methodology_score: null,
    clarity_score: null,
    relevance_score: null,
    ethics_score: null,
    recommendation: null,
    comments_for_author: null,
    confidential_comments: null,
    conflict_declared: false,
    submitted_at: null,
    ...overrides,
  };
}

/** Borrador con todo lo que exige el envío final. */
export function buildCompleteEvaluation(
  overrides: Partial<ReviewerEvaluation> = {},
): ReviewerEvaluation {
  return buildReviewerEvaluation({
    id: 'ev-1',
    originality_score: 4,
    methodology_score: 3,
    clarity_score: 5,
    relevance_score: 4,
    ethics_score: 5,
    recommendation: 'REQUIRES_CORRECTIONS',
    comments_for_author: 'Aclarar la metodología.',
    confidential_comments: 'Revisar la muestra.',
    ...overrides,
  });
}
