/**
 * Modelos del módulo Revisor (plan secciones 2.5 y 2.9).
 *
 * Reflejan los serializadores de lista blanca del backend
 * (`ReviewerAssignmentSerializer` y `ReviewerAssignmentDetailSerializer`).
 * Por el doble ciego estos tipos **no declaran** autores, filiaciones,
 * contacto, nombre original del archivo ni ruta alguna: lo que el tipo no
 * declara, la interfaz no lo puede renderizar.
 */

/** Estado de la asignación en la bandeja (derivado en el servidor, HU-14). */
export type InboxState = 'PENDING' | 'ON_TIME' | 'OVERDUE' | 'EVALUATED' | 'REVOKED';

export const INBOX_STATE_LABELS: Readonly<Record<InboxState, string>> = {
  PENDING: 'Pendiente',
  ON_TIME: 'En plazo',
  OVERDUE: 'Vencida',
  EVALUATED: 'Evaluada',
  REVOKED: 'Revocada',
};

/** Estado almacenado de la asignación. */
export type AssignmentStatus = 'ACTIVE' | 'COMPLETED' | 'REVOKED' | 'EXPIRED';

/** Fila de la bandeja (`GET /api/reviewer/assignments/`). */
export interface ReviewerAssignmentRow {
  id: string;
  manuscript_code: string;
  manuscript_title: string;
  area: string;
  version_number: number;
  round_number: number;
  assigned_at: string;
  /** Fecha límite fijada por el servidor; el navegador no la calcula. */
  due_at: string;
  status: AssignmentStatus;
  state: InboxState;
  /** Vencida según el reloj del servidor en el momento de la lectura. */
  is_overdue: boolean;
  completed_at: string | null;
}

/** Manuscrito tal como lo ve su Revisor: contenido, nunca autoría. */
export interface ReviewerManuscript {
  id: string;
  code: string;
  title: string;
  abstract: string;
  keywords: string[];
  area: string;
  language: string;
  current_round: number;
  current_version: number;
}

/** Versión asignada: solo números y fecha. */
export interface ReviewerVersion {
  version_number: number;
  round_number: number;
  submitted_at: string;
}

/** Detalle anonimizado (`GET /api/reviewer/assignments/{id}/`). */
export interface ReviewerAssignmentDetail extends ReviewerAssignmentRow {
  manuscript: ReviewerManuscript;
  version: ReviewerVersion;
  /** Ruta de la API del PDF sanitizado; `null` salvo con la asignación `ACTIVE`. */
  document_url: string | null;
}

/**
 * Un detalle junto con la diferencia entre el reloj del servidor y el del
 * navegador, para que el contador cuente contra la hora del backend.
 */
export interface AssignmentSnapshot {
  assignment: ReviewerAssignmentDetail;
  /** `hora del servidor − hora del navegador` en milisegundos (`0` si no se conoce). */
  serverOffsetMs: number;
}

/** Solo estas asignaciones tienen detalle: las demás responden `404`. */
export function hasDetail(row: Pick<ReviewerAssignmentRow, 'status'>): boolean {
  return row.status === 'ACTIVE' || row.status === 'COMPLETED';
}

/** Nombre genérico del PDF sanitizado: nunca el del archivo original del Autor. */
export function genericDocumentName(code: string, versionNumber: number): string {
  return `manuscript-${code}-v${versionNumber}.pdf`;
}
