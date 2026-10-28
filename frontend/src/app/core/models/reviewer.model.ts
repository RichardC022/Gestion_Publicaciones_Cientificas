/**
 * Modelos del módulo Revisor (plan secciones 2.5 y 2.9).
 *
 * Reflejan los serializadores de lista blanca del backend
 * (`ReviewerAssignmentSerializer` y `ReviewerAssignmentDetailSerializer`).
 * Por el doble ciego estos tipos **no declaran** autores, filiaciones,
 * contacto, nombre original del archivo ni ruta alguna: lo que el tipo no
 * declara, la interfaz no lo puede renderizar.
 */

import { Recommendation } from './editor.model';

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

/** Puntaje mínimo y máximo de cada criterio (el servidor también lo exige). */
export const MIN_SCORE = 1;
export const MAX_SCORE = 5;

/** Largo máximo de cada comentario (el servidor rechaza más). */
export const COMMENT_MAX_LENGTH = 10000;

export type ScoreField =
  'originality_score' | 'methodology_score' | 'clarity_score' | 'relevance_score' | 'ethics_score';

/** Criterios de la evaluación estructurada, en el orden del formulario. */
export const SCORE_CRITERIA: readonly { field: ScoreField; label: string; hint: string }[] = [
  {
    field: 'originality_score',
    label: 'Originalidad',
    hint: 'Aporte nuevo frente a lo ya publicado.',
  },
  {
    field: 'methodology_score',
    label: 'Metodología',
    hint: 'Rigor y adecuación del método.',
  },
  { field: 'clarity_score', label: 'Claridad', hint: 'Redacción y organización del texto.' },
  {
    field: 'relevance_score',
    label: 'Relevancia',
    hint: 'Importancia para el área de estudio.',
  },
  {
    field: 'ethics_score',
    label: 'Ética',
    hint: 'Cumplimiento de normas éticas de investigación.',
  },
];

/** Opciones de recomendación, en el orden del formulario. */
export const RECOMMENDATION_OPTIONS: readonly { value: Recommendation; label: string }[] = [
  { value: 'ACCEPT', label: 'Aceptar' },
  { value: 'REQUIRES_CORRECTIONS', label: 'Requiere correcciones' },
  { value: 'REJECT', label: 'Rechazar' },
];

/**
 * Evaluación propia del Revisor (`GET .../evaluation/`): el borrador privado
 * o la final. Antes del primer guardado llega vacía, con `id` nulo.
 */
export interface ReviewerEvaluation {
  id: string | null;
  status: 'DRAFT' | 'FINAL';
  originality_score: number | null;
  methodology_score: number | null;
  clarity_score: number | null;
  relevance_score: number | null;
  ethics_score: number | null;
  recommendation: Recommendation | null;
  comments_for_author: string | null;
  confidential_comments: string | null;
  /** El Revisor declaró un conflicto de interés: la evaluación está bloqueada. */
  conflict_declared: boolean;
  submitted_at: string | null;
}

/** Cuerpo de `PUT .../evaluation/`: todos los campos son opcionales en un borrador. */
export interface EvaluationDraft {
  originality_score: number | null;
  methodology_score: number | null;
  clarity_score: number | null;
  relevance_score: number | null;
  ethics_score: number | null;
  recommendation: Recommendation | null;
  comments_for_author: string | null;
  confidential_comments: string | null;
}

/** Una evaluación junto con su `ETag` vigente (bloqueo optimista, `"0"` si aún no existe). */
export interface EvaluationSnapshot {
  evaluation: ReviewerEvaluation;
  etag: string | null;
}

/** Máximo que acepta la API en la descripción de un reporte confidencial. */
export const INCIDENT_DESCRIPTION_MAX_LENGTH = 5000;

/** Máximo del motivo opcional al declarar un conflicto de interés. */
export const CONFLICT_REASON_MAX_LENGTH = 2000;

export type IncidentReportType = 'IDENTITY_LEAK' | 'OTHER';

export const INCIDENT_REPORT_TYPES: readonly {
  value: IncidentReportType;
  label: string;
  hint: string;
}[] = [
  {
    value: 'IDENTITY_LEAK',
    label: 'Posible fuga de identidad',
    hint: 'El texto o el PDF deja ver quién escribió el manuscrito.',
  },
  {
    value: 'OTHER',
    label: 'Otro',
    hint: 'Otro problema que el Editor deba conocer.',
  },
];

/**
 * Acuse de un reporte confidencial (`POST .../identity-leak/`): solo el
 * recibo, nunca el texto ni nada editorial.
 */
export interface IncidentReceipt {
  id: string;
  assignment: string;
  report_type: IncidentReportType;
  status: string;
  created_at: string;
}
