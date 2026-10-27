/**
 * Modelos del módulo Editor (plan secciones 2.4 y 3.5).
 *
 * Reflejan `SubmissionListSerializer` y `SubmissionDetailSerializer` del
 * backend. El Editor es el único rol que ve los datos de contacto de los
 * autores y la identidad del Revisor asignado.
 */
import { HistoryEntry, ManuscriptAuthor, ManuscriptStatus, VersionSummary } from './manuscript.model';

/** Fila de la bandeja de nuevos envíos (`GET /api/editor/submissions/`). */
export interface SubmissionRow {
  id: string;
  code: string;
  title: string;
  area: string;
  language: string;
  status: ManuscriptStatus;
  current_round: number;
  current_version: number;
  /** Nombre del autor de correspondencia; el detalle trae el resto. */
  corresponding_author: string | null;
  /** Fecha del último envío formal (versión vigente). */
  submitted_at: string | null;
  created_at: string;
}

/** Órdenes que ofrece la bandeja (valores del parámetro `ordering`). */
export const SUBMISSION_ORDERINGS = [
  { value: '-updated_at', label: 'Más recientes' },
  { value: 'updated_at', label: 'Más antiguos' },
  { value: 'code', label: 'Código' },
  { value: 'title', label: 'Título' },
] as const;

export type SubmissionOrdering = (typeof SUBMISSION_ORDERINGS)[number]['value'];

export const DEFAULT_SUBMISSION_ORDERING: SubmissionOrdering = '-updated_at';

/** Filtros de la bandeja; la API solo devuelve manuscritos `SUBMITTED`. */
export interface SubmissionListParams {
  search?: string;
  area?: string;
  date_from?: string;
  date_to?: string;
  ordering?: SubmissionOrdering;
  page?: number;
  page_size?: number;
}

/** Versión formal con la ruta de la API de su PDF (nunca una ruta del volumen). */
export interface SubmissionVersion extends VersionSummary {
  file_url: string;
}

/** Persona asignada o que asigna: nombre y contacto. */
export interface PersonSummary {
  id: string;
  full_name: string;
  email: string;
}

/** Asignación activa o vencida que espera la decisión del Editor. */
export interface OpenAssignment {
  id: string;
  status: string;
  assigned_at: string;
  due_at: string;
  is_overdue: boolean;
  reviewer: PersonSummary;
}

/** Detalle editorial de un envío (`GET /api/editor/submissions/{id}/`). */
export interface SubmissionDetail {
  id: string;
  code: string;
  title: string;
  abstract: string;
  keywords: string[];
  area: string;
  language: string;
  status: ManuscriptStatus;
  current_round: number;
  current_version: number;
  is_active: boolean;
  withdrawn_at: string | null;
  withdrawal_reason: string | null;
  authors: ManuscriptAuthor[];
  versions: SubmissionVersion[];
  history: HistoryEntry[];
  open_assignment: OpenAssignment | null;
  created_at: string;
  updated_at: string;
}

/** Un detalle junto con su `ETag` vigente (bloqueo optimista). */
export interface SubmissionSnapshot {
  submission: SubmissionDetail;
  etag: string | null;
}

/** Respuesta de `POST .../start-review/`. */
export interface StartReviewResult {
  id: string;
  code: string;
  status: ManuscriptStatus;
  assignment: OpenAssignment | null;
}
