import {
  Assignment,
  EditorEvaluation,
  EligibleReviewer,
  SubmissionDetail,
  SubmissionRow,
  Verdict,
  VerdictResult,
} from '../../../core/models/editor.model';
import { Paginated } from '../../../core/models/paginated.model';

/** Datos de ejemplo del módulo Editor para las pruebas. */
export function buildSubmissionRow(overrides: Partial<SubmissionRow> = {}): SubmissionRow {
  return {
    id: 's-1',
    code: 'GPC-2026-000001',
    title: 'Efecto del clima en cultivos andinos',
    area: 'Agronomía',
    language: 'es',
    status: 'SUBMITTED',
    current_round: 0,
    current_version: 1,
    corresponding_author: 'Ana López',
    submitted_at: '2026-10-21T15:30:00Z',
    created_at: '2026-10-20T15:30:00Z',
    ...overrides,
  };
}

export function buildSubmissionPage(
  results: SubmissionRow[],
  count: number = results.length,
): Paginated<SubmissionRow> {
  return { count, next: null, previous: null, results };
}

export function buildSubmissionDetail(
  overrides: Partial<SubmissionDetail> = {},
): SubmissionDetail {
  return {
    id: 's-1',
    code: 'GPC-2026-000001',
    title: 'Efecto del clima en cultivos andinos',
    abstract: 'Resumen del estudio de campo.',
    keywords: ['clima', 'cultivos'],
    area: 'Agronomía',
    language: 'es',
    status: 'SUBMITTED',
    current_round: 0,
    current_version: 1,
    is_active: true,
    withdrawn_at: null,
    withdrawal_reason: null,
    authors: [
      {
        full_name: 'Ana López',
        email: 'a.lopez@unl.edu.ec',
        affiliation: 'Universidad Nacional de Loja',
        is_corresponding: true,
        author_order: 1,
      },
      {
        full_name: 'Luis Pérez',
        email: 'luis@otra.edu',
        affiliation: 'Otra Universidad',
        is_corresponding: false,
        author_order: 2,
      },
    ],
    versions: [
      {
        id: 'v-1',
        version_number: 1,
        round_number: 0,
        original_filename: 'articulo.pdf',
        original_size_bytes: 2048,
        original_sha256: 'a'.repeat(64),
        submitted_at: '2026-10-21T15:30:00Z',
        file_url: '/api/manuscripts/s-1/versions/v-1/file/',
      },
    ],
    history: [
      {
        type: 'CREATED',
        occurred_at: '2026-10-20T15:30:00Z',
        from_status: null,
        to_status: 'DRAFT',
        reason: null,
        version_number: null,
        round_number: null,
      },
      {
        type: 'VERSION_SUBMITTED',
        occurred_at: '2026-10-21T15:30:00Z',
        version_id: 'v-1',
        version_number: 1,
        round_number: 0,
        original_filename: 'articulo.pdf',
        original_size_bytes: 2048,
        integrity_seal: `sha256:${'a'.repeat(64)}`,
        metadata_sha256: 'b'.repeat(64),
      },
    ],
    open_assignment: null,
    created_at: '2026-10-20T15:30:00Z',
    updated_at: '2026-10-21T15:30:00Z',
    ...overrides,
  };
}

export function buildAssignment(overrides: Partial<Assignment> = {}): Assignment {
  return {
    id: 'a-1',
    manuscript: 's-1',
    manuscript_code: 'GPC-2026-000001',
    manuscript_title: 'Efecto del clima en cultivos andinos',
    version_number: 1,
    status: 'ACTIVE',
    assigned_at: '2026-10-22T15:00:00Z',
    due_at: '2026-11-11T15:00:00Z',
    is_overdue: false,
    reviewer: { id: 'r-1', full_name: 'Marta Ruiz', email: 'marta@unl.edu.ec' },
    assigned_by: { id: 'e-1', full_name: 'Edgar Mora', email: 'edgar@unl.edu.ec' },
    completed_at: null,
    revoked_at: null,
    revoked_by: null,
    revocation_reason: null,
    ...overrides,
  };
}

export function buildReviewer(overrides: Partial<EligibleReviewer> = {}): EligibleReviewer {
  return {
    id: 'r-1',
    institutional_id: 'INST-0001',
    full_name: 'Marta Ruiz',
    email: 'marta@unl.edu.ec',
    expertise_areas: ['Agronomía'],
    max_active_assignments: 3,
    active_assignments: 1,
    ...overrides,
  };
}

export function buildEvaluation(overrides: Partial<EditorEvaluation> = {}): EditorEvaluation {
  return {
    id: 'ev-1',
    assignment: 'a-1',
    version_number: 1,
    reviewer: { id: 'r-1', full_name: 'Marta Ruiz', email: 'marta@unl.edu.ec' },
    status: 'FINAL',
    originality_score: 4,
    methodology_score: 3,
    clarity_score: 5,
    relevance_score: 4,
    ethics_score: 5,
    recommendation: 'ACCEPT',
    comments_for_author: 'Buen trabajo; falta detallar el muestreo.',
    confidential_comments: 'Solo para el Editor: sospecho autocitas.',
    conflict_declared: false,
    submitted_at: '2026-11-05T15:00:00Z',
    ...overrides,
  };
}

export function buildVerdict(overrides: Partial<Verdict> = {}): Verdict {
  return {
    id: 'vd-1',
    decision: 'ACCEPTED',
    justification: null,
    observations: null,
    version_number: 1,
    evaluation: 'ev-1',
    editor: { id: 'e-1', full_name: 'Edgar Mora', email: 'edgar@unl.edu.ec' },
    previous_verdict: null,
    created_at: '2026-11-06T15:00:00Z',
    ...overrides,
  };
}

export function buildVerdictResult(overrides: Partial<VerdictResult> = {}): VerdictResult {
  const verdict = overrides.verdict ?? buildVerdict();
  return {
    verdict,
    manuscript: {
      id: 's-1',
      code: 'GPC-2026-000001',
      status: 'ACCEPTED',
      current_round: 0,
      current_version: 1,
    },
    catalog_entry: { id: 'c-1', published_at: '2026-11-06T15:00:00Z' },
    opened_round: null,
    history: [verdict],
    ...overrides,
  };
}
