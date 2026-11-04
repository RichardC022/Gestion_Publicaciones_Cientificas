import { Recommendation } from '../../../core/models/editor.model';
import {
  COMMENT_MAX_LENGTH,
  EvaluationDraft,
  MAX_SCORE,
  MIN_SCORE,
  ReviewerEvaluation,
  SCORE_CRITERIA,
  ScoreField,
} from '../../../core/models/reviewer.model';

/** Lo que el Revisor escribe; los comentarios son siempre texto (vacío si no hay). */
export interface EvaluationValues {
  originality_score: number | null;
  methodology_score: number | null;
  clarity_score: number | null;
  relevance_score: number | null;
  ethics_score: number | null;
  recommendation: Recommendation | null;
  comments_for_author: string;
  confidential_comments: string;
}

/** Campos que pueden fallar al enviar (los mismos que el servidor exige). */
export type EvaluationField = ScoreField | 'recommendation' | 'comments_for_author';

export type EvaluationErrors = Partial<Record<EvaluationField | 'declaration', string>>;

export const EMPTY_VALUES: EvaluationValues = {
  originality_score: null,
  methodology_score: null,
  clarity_score: null,
  relevance_score: null,
  ethics_score: null,
  recommendation: null,
  comments_for_author: '',
  confidential_comments: '',
};

/** Valores del formulario a partir de la evaluación del servidor. */
export function toValues(evaluation: ReviewerEvaluation): EvaluationValues {
  return {
    originality_score: evaluation.originality_score,
    methodology_score: evaluation.methodology_score,
    clarity_score: evaluation.clarity_score,
    relevance_score: evaluation.relevance_score,
    ethics_score: evaluation.ethics_score,
    recommendation: evaluation.recommendation,
    comments_for_author: evaluation.comments_for_author ?? '',
    confidential_comments: evaluation.confidential_comments ?? '',
  };
}

/** Cuerpo del borrador: el texto en blanco equivale a no haber escrito nada. */
export function toDraft(values: EvaluationValues): EvaluationDraft {
  return {
    ...values,
    comments_for_author: values.comments_for_author.trim() || null,
    confidential_comments: values.confidential_comments.trim() || null,
  };
}

/** Hay cambios respecto de lo último guardado (el espacio sobrante no cuenta). */
export function isDirty(current: EvaluationValues, saved: EvaluationValues): boolean {
  const a = toDraft(current);
  const b = toDraft(saved);
  return (Object.keys(a) as (keyof EvaluationDraft)[]).some((key) => a[key] !== b[key]);
}

export const SCORE_REQUIRED = `Seleccione una puntuación del ${MIN_SCORE} al ${MAX_SCORE}.`;
export const RECOMMENDATION_REQUIRED = 'Seleccione una recomendación.';
export const COMMENTS_REQUIRED = 'Escriba los comentarios para el Autor.';
export const COMMENTS_TOO_LONG = `Los comentarios admiten hasta ${COMMENT_MAX_LENGTH} caracteres.`;
export const DECLARATION_REQUIRED =
  'Debe declarar que no tiene conflicto de interés para enviar la evaluación.';

/**
 * Lo que impide el envío final: los cinco puntajes, la recomendación, los
 * comentarios para el Autor y la declaración de no tener conflicto de
 * interés. Los comentarios confidenciales son opcionales. El borrador no
 * pasa por aquí: se guarda con huecos.
 */
export function submitErrors(values: EvaluationValues, declared: boolean): EvaluationErrors {
  const errors: EvaluationErrors = {};
  for (const { field } of SCORE_CRITERIA) {
    const score = values[field];
    if (score === null || score < MIN_SCORE || score > MAX_SCORE) {
      errors[field] = SCORE_REQUIRED;
    }
  }
  if (values.recommendation === null) {
    errors.recommendation = RECOMMENDATION_REQUIRED;
  }
  if (values.comments_for_author.trim() === '') {
    errors.comments_for_author = COMMENTS_REQUIRED;
  }
  if (values.comments_for_author.length > COMMENT_MAX_LENGTH) {
    errors.comments_for_author = COMMENTS_TOO_LONG;
  }
  if (!declared) {
    errors.declaration = DECLARATION_REQUIRED;
  }
  return errors;
}

/** Errores por campo del envelope `details` de un `400` (`{campo: [mensajes]}`). */
export function serverFieldErrors(details: unknown): EvaluationErrors {
  const errors: EvaluationErrors = {};
  if (typeof details !== 'object' || details === null) {
    return errors;
  }
  const known = new Set<string>([
    ...SCORE_CRITERIA.map((c) => c.field),
    'recommendation',
    'comments_for_author',
  ]);
  for (const [field, messages] of Object.entries(details)) {
    const first = Array.isArray(messages) ? messages[0] : messages;
    if (known.has(field) && typeof first === 'string') {
      errors[field as EvaluationField] = first;
    }
  }
  return errors;
}
