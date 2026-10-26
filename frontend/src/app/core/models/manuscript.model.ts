/**
 * Modelos del módulo Autor (plan secciones 2.3 y 3.6).
 *
 * Reflejan `AuthorManuscriptSerializer` del backend: la vista del Autor
 * nunca incluye la identidad del Revisor, comentarios confidenciales ni
 * puntuaciones internas. `EvaluationFeedback` es la única parte de una
 * evaluación que el Autor puede leer (`AuthorEvaluationFeedbackSerializer`).
 */

export type ManuscriptStatus =
  'DRAFT' | 'SUBMITTED' | 'UNDER_REVIEW' | 'REQUIRES_CORRECTIONS' | 'ACCEPTED' | 'REJECTED';

export const MANUSCRIPT_STATUSES: readonly ManuscriptStatus[] = [
  'DRAFT',
  'SUBMITTED',
  'UNDER_REVIEW',
  'REQUIRES_CORRECTIONS',
  'ACCEPTED',
  'REJECTED',
];

/** Estados en los que el Autor puede editar los metadatos (RN, HU-07). */
export const EDITABLE_STATUSES: readonly ManuscriptStatus[] = ['DRAFT', 'REQUIRES_CORRECTIONS'];

export interface ManuscriptAuthor {
  full_name: string;
  email: string;
  affiliation: string;
  is_corresponding: boolean;
  author_order?: number;
}

/** PDF de borrador adjunto: solo nombre, tamaño y fecha, nunca la ruta. */
export interface DraftFileSummary {
  filename: string;
  size_bytes: number;
  uploaded_at: string;
}

/**
 * Lo único que el Autor lee de una evaluación: los comentarios escritos
 * para él, la decisión del Editor y sus observaciones. La interfaz no
 * declara (ni renderiza) el revisor, los comentarios confidenciales ni
 * las puntuaciones.
 */
export interface EvaluationFeedback {
  comments_for_author: string;
  decision: string;
  observations: string | null;
}

export interface Manuscript {
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
  draft_file: DraftFileSummary | null;
  /** Presente cuando existe una evaluación y un veredicto (TSK-50/52). */
  feedback?: EvaluationFeedback | null;
  created_at: string;
  updated_at: string;
}

/**
 * Eventos de la carga del PDF de borrador: el avance (`percent` es
 * `null` si el navegador no conoce el total) y el resultado final.
 * `replaced` es verdadero cuando sustituyó a un borrador anterior (`200`)
 * y falso en la primera carga (`201`).
 */
export type DraftUploadEvent =
  | { kind: 'progress'; percent: number | null }
  | { kind: 'done'; draft: DraftFileSummary; replaced: boolean };

/**
 * Resultado de un envío formal o de una nueva versión
 * (`POST .../submit/` y `POST .../versions/`): el código de seguimiento,
 * la versión y la ronda creadas, la fecha y el sello de integridad
 * `sha256:<hex>` del PDF exacto.
 */
export interface SubmissionResult {
  code: string;
  status: ManuscriptStatus;
  version_number: number;
  round_number: number;
  submitted_at: string;
  integrity_seal: string;
}

/** Eventos de la carga de una nueva versión: avance y resultado final. */
export type VersionUploadEvent =
  { kind: 'progress'; percent: number | null } | { kind: 'done'; submission: SubmissionResult };

/** Fila de `GET .../versions/`: una iteración con el sello de su PDF. */
export interface VersionSummary {
  id: string;
  version_number: number;
  round_number: number;
  original_filename: string;
  original_size_bytes: number;
  original_sha256: string;
  submitted_at: string;
}

/** Entradas del historial inmutable (`GET .../history/`, HU-23). */
export interface StatusHistoryEntry {
  type: 'CREATED' | 'STATUS_CHANGED' | 'WITHDRAWN';
  occurred_at: string;
  from_status: string | null;
  to_status: string;
  reason: string | null;
  version_number: number | null;
  round_number: number | null;
}

/** Una iteración formal: el PDF exacto y los sellos de integridad. */
export interface VersionHistoryEntry {
  type: 'VERSION_SUBMITTED';
  occurred_at: string;
  version_id: string;
  version_number: number;
  round_number: number;
  original_filename: string;
  original_size_bytes: number;
  /** `sha256:<hex>` del PDF original. */
  integrity_seal: string;
  metadata_sha256: string;
}

export interface RoundHistoryEntry {
  type: 'ROUND_OPENED';
  occurred_at: string;
  round_number: number;
  closed_at: string | null;
  closed_by_version_number: number | null;
}

export type HistoryEntry = StatusHistoryEntry | VersionHistoryEntry | RoundHistoryEntry;

/** PDF descargado: el contenido y el nombre sugerido por el servidor. */
export interface VersionDownload {
  blob: Blob;
  filename: string;
}

/** Estados en los que la baja lógica exige un motivo (CA-HU-08-02). */
export const WITHDRAWAL_REASON_REQUIRED: readonly ManuscriptStatus[] = ['UNDER_REVIEW', 'ACCEPTED'];

export function requiresWithdrawalReason(status: ManuscriptStatus): boolean {
  return WITHDRAWAL_REASON_REQUIRED.includes(status);
}

/** Un manuscrito junto con su `ETag` vigente (bloqueo optimista). */
export interface ManuscriptSnapshot {
  manuscript: Manuscript;
  etag: string | null;
}

export interface AuthorPayload {
  full_name: string;
  email: string;
  affiliation: string;
  is_corresponding: boolean;
}

export interface ManuscriptPayload {
  title: string;
  abstract: string;
  keywords: string[];
  area: string;
  language: string;
  authors: AuthorPayload[];
}

/** Filtros del listado (`GET /api/manuscripts/`, plan sección 2.1). */
export interface ManuscriptListParams {
  status?: ManuscriptStatus;
  date_from?: string;
  date_to?: string;
  /** `true` pide los manuscritos dados de baja (vista de archivados). */
  archived?: boolean;
  page?: number;
  page_size?: number;
}

/** El Autor edita solo en `DRAFT` o `REQUIRES_CORRECTIONS` y si no está dado de baja. */
export function isEditable(manuscript: Pick<Manuscript, 'status' | 'is_active'>): boolean {
  return manuscript.is_active && EDITABLE_STATUSES.includes(manuscript.status);
}

/** Texto breve para el listado y texto completo para el detalle. */
export interface NextAction {
  short: string;
  detail: string;
}

const NEXT_ACTION_BY_STATUS: Record<ManuscriptStatus, NextAction> = {
  DRAFT: {
    short: 'Completar y enviar',
    detail: 'Complete los datos, adjunte el PDF y envíe el manuscrito al Editor.',
  },
  SUBMITTED: {
    short: 'En espera del Editor',
    detail: 'El Editor revisará el envío y lo pasará a revisión. No requiere acción de su parte.',
  },
  UNDER_REVIEW: {
    short: 'En revisión',
    detail: 'El manuscrito está siendo evaluado. No requiere acción de su parte.',
  },
  REQUIRES_CORRECTIONS: {
    short: 'Enviar nueva versión',
    detail:
      'Atienda las observaciones, edite los datos si hace falta y envíe una nueva versión con el PDF corregido.',
  },
  ACCEPTED: {
    short: 'Publicado',
    detail: 'El manuscrito fue aceptado y se publica en el catálogo público.',
  },
  REJECTED: {
    short: 'Sin acciones pendientes',
    detail: 'El manuscrito fue rechazado. Puede archivarlo con la baja lógica.',
  },
};

const NEXT_ACTION_ARCHIVED: NextAction = {
  short: 'Archivado',
  detail:
    'El manuscrito fue dado de baja. Se conserva en modo de solo lectura con todo su historial.',
};

/** Acción pendiente del Autor según el estado y la baja lógica. */
export function nextAction(manuscript: Pick<Manuscript, 'status' | 'is_active'>): NextAction {
  return manuscript.is_active ? NEXT_ACTION_BY_STATUS[manuscript.status] : NEXT_ACTION_ARCHIVED;
}
