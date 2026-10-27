import { SubmissionDetail, SubmissionRow } from '../../../core/models/editor.model';
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
