/**
 * Modelos del módulo Editor (plan secciones 2.4 y 3.5).
 *
 * Reflejan `SubmissionListSerializer` y `SubmissionDetailSerializer` del
 * backend. El Editor es el único rol que ve los datos de contacto de los
 * autores y la identidad del Revisor asignado.
 */
import { HistoryEntry, ManuscriptAuthor, ManuscriptStatus, VersionSummary } from './manuscript.model';
import { Paginated } from './paginated.model';

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

/** Asignación completa tal como la ve el Editor (`AssignmentSerializer`). */
export interface Assignment extends OpenAssignment {
  manuscript: string;
  manuscript_code: string;
  manuscript_title: string;
  version_number: number;
  assigned_by: PersonSummary;
  completed_at: string | null;
  revoked_at: string | null;
  revoked_by: PersonSummary | null;
  revocation_reason: string | null;
}

/** Una asignación sin resolver: vigente o vencida y aún sin revocar. */
export function isOpenAssignment(assignment: Pick<OpenAssignment, 'status'>): boolean {
  return assignment.status === 'ACTIVE' || assignment.status === 'EXPIRED';
}

/** Vencida: ya marcada `EXPIRED` o `ACTIVE` pasada su fecha límite (reloj del servidor). */
export function isOverdue(assignment: Pick<OpenAssignment, 'status' | 'is_overdue'>): boolean {
  return assignment.status === 'EXPIRED' || assignment.is_overdue;
}

/** Revisor candidato con su pericia y su carga actual. */
export interface EligibleReviewer {
  id: string;
  institutional_id: string;
  full_name: string;
  email: string;
  expertise_areas: string[];
  max_active_assignments: number;
  active_assignments: number;
}

/** Con la carga completa la API rechazaría la asignación con `409`. */
export function isAtCapacity(reviewer: EligibleReviewer): boolean {
  return reviewer.active_assignments >= reviewer.max_active_assignments;
}

/**
 * Por qué una lista de candidatos quedó vacía: cuántas cuentas de Revisor
 * hay y cuántas excluye cada regla (exclusivas, suman `reviewers`).
 */
export interface EligibilityDiagnosis {
  reviewers: number;
  conflict: number;
  no_profile: number;
  unavailable: number;
  other_area: number;
}

/** Página de candidatos; `diagnosis` solo llega cuando está vacía. */
export interface EligibleReviewersPage extends Paginated<EligibleReviewer> {
  diagnosis?: EligibilityDiagnosis;
}

export type RevocationCause =
  'CONFLICT_OF_INTEREST' | 'ASSIGNMENT_ERROR' | 'ACCOUNT_DISABLED' | 'OVERDUE';

/**
 * Causas de revocación. Con el plazo vigente solo valen las tres
 * «tempranas»; `OVERDUE` exige que la asignación haya vencido.
 */
export const REVOCATION_CAUSES: readonly {
  value: RevocationCause;
  label: string;
  hint: string;
  early: boolean;
}[] = [
  {
    value: 'CONFLICT_OF_INTEREST',
    label: 'Conflicto de interés',
    hint: 'El Revisor tiene un vínculo con el manuscrito o sus autores.',
    early: true,
  },
  {
    value: 'ASSIGNMENT_ERROR',
    label: 'Error de asignación',
    hint: 'Se asignó a la persona equivocada o al manuscrito equivocado.',
    early: true,
  },
  {
    value: 'ACCOUNT_DISABLED',
    label: 'Cuenta inhabilitada',
    hint: 'La cuenta del Revisor ya no puede acceder al sistema.',
    early: true,
  },
  {
    value: 'OVERDUE',
    label: 'Plazo vencido',
    hint: 'El Revisor no evaluó dentro de los 20 días.',
    early: false,
  },
];

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
  open_assignment: Assignment | null;
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

/** Decisiones del Editor sobre un manuscrito evaluado. */
export type VerdictDecision = 'ACCEPTED' | 'REJECTED' | 'REQUIRES_CORRECTIONS';

/** Recomendación que el Revisor escribe en su evaluación final. */
export type Recommendation = 'ACCEPT' | 'REQUIRES_CORRECTIONS' | 'REJECT';

export const RECOMMENDATION_LABELS: Readonly<Record<Recommendation, string>> = {
  ACCEPT: 'Aceptar',
  REQUIRES_CORRECTIONS: 'Requiere correcciones',
  REJECT: 'Rechazar',
};

/** La decisión que equivale a seguir la recomendación del Revisor. */
export const DECISION_BY_RECOMMENDATION: Readonly<Record<Recommendation, VerdictDecision>> = {
  ACCEPT: 'ACCEPTED',
  REQUIRES_CORRECTIONS: 'REQUIRES_CORRECTIONS',
  REJECT: 'REJECTED',
};

/** Verdadero si la decisión del Editor se aparta de la recomendación del Revisor. */
export function departsFromRecommendation(
  decision: VerdictDecision,
  recommendation: Recommendation,
): boolean {
  return DECISION_BY_RECOMMENDATION[recommendation] !== decision;
}

/**
 * Evaluación final tal como la lee el Editor (`EditorEvaluationSerializer`):
 * con la identidad del Revisor y los comentarios confidenciales. Solo el
 * módulo Editor declara estos campos.
 */
export interface EditorEvaluation {
  id: string;
  assignment: string;
  version_number: number;
  reviewer: PersonSummary;
  status: string;
  originality_score: number | null;
  methodology_score: number | null;
  clarity_score: number | null;
  relevance_score: number | null;
  ethics_score: number | null;
  recommendation: Recommendation | null;
  comments_for_author: string | null;
  confidential_comments: string | null;
  conflict_declared: boolean;
  submitted_at: string | null;
}

/** Veredicto registrado; es inmutable, por eso la interfaz solo lo lee. */
export interface Verdict {
  id: string;
  decision: VerdictDecision;
  justification: string | null;
  observations: string | null;
  version_number: number;
  evaluation: string;
  editor: PersonSummary;
  previous_verdict: string | null;
  created_at: string;
}

/** Cuerpo de `POST .../verdicts/`. */
export interface VerdictRequest {
  decision: VerdictDecision;
  justification: string | null;
  observations: string | null;
}

/** Respuesta de un veredicto registrado (`201`). */
export interface VerdictResult {
  verdict: Verdict;
  manuscript: {
    id: string;
    code: string;
    status: ManuscriptStatus;
    current_round: number;
    current_version: number;
  };
  catalog_entry: { id: string; published_at: string } | null;
  opened_round: number | null;
  history: Verdict[];
}

/** Un veredicto registrado junto con el `ETag` nuevo del manuscrito. */
export interface VerdictRegistered {
  result: VerdictResult;
  etag: string | null;
}
