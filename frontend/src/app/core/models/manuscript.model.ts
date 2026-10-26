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
