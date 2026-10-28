import { COMMENT_MAX_LENGTH } from '../../../core/models/reviewer.model';
import {
  COMMENTS_REQUIRED,
  COMMENTS_TOO_LONG,
  DECLARATION_REQUIRED,
  EMPTY_VALUES,
  EvaluationValues,
  RECOMMENDATION_REQUIRED,
  SCORE_REQUIRED,
  isDirty,
  serverFieldErrors,
  submitErrors,
  toDraft,
  toValues,
} from './evaluation-form.rules';
import { buildCompleteEvaluation, buildReviewerEvaluation } from '../testing/reviewer.fixtures';

const complete = (): EvaluationValues => toValues(buildCompleteEvaluation());

describe('toValues / toDraft', () => {
  it('un borrador vacío del servidor da valores vacíos', () => {
    expect(toValues(buildReviewerEvaluation())).toEqual(EMPTY_VALUES);
  });

  it('el texto en blanco viaja como nulo', () => {
    const draft = toDraft({
      ...EMPTY_VALUES,
      comments_for_author: '   ',
      confidential_comments: '',
    });

    expect(draft.comments_for_author).toBeNull();
    expect(draft.confidential_comments).toBeNull();
  });

  it('el texto se recorta y los puntajes pasan tal cual', () => {
    const draft = toDraft({ ...complete(), comments_for_author: '  Hola  ' });

    expect(draft.comments_for_author).toBe('Hola');
    expect(draft.originality_score).toBe(4);
    expect(draft.recommendation).toBe('REQUIRES_CORRECTIONS');
  });
});

describe('isDirty', () => {
  it('iguales no son cambios', () => {
    expect(isDirty(complete(), complete())).toBe(false);
  });

  it('el espacio sobrante no cuenta como cambio', () => {
    expect(
      isDirty({ ...complete(), comments_for_author: '  Aclarar la metodología.  ' }, complete()),
    ).toBe(false);
  });

  it('un puntaje, la recomendación o un texto distinto sí', () => {
    expect(isDirty({ ...complete(), ethics_score: 2 }, complete())).toBe(true);
    expect(isDirty({ ...complete(), recommendation: 'ACCEPT' }, complete())).toBe(true);
    expect(isDirty({ ...complete(), confidential_comments: 'otro' }, complete())).toBe(true);
  });
});

describe('submitErrors', () => {
  it('una evaluación completa y con la declaración no tiene errores', () => {
    expect(submitErrors(complete(), true)).toEqual({});
  });

  it('exige los cinco puntajes, la recomendación, los comentarios y la declaración', () => {
    const errors = submitErrors(EMPTY_VALUES, false);

    expect(Object.keys(errors).sort()).toEqual(
      [
        'clarity_score',
        'comments_for_author',
        'declaration',
        'ethics_score',
        'methodology_score',
        'originality_score',
        'recommendation',
        'relevance_score',
      ].sort(),
    );
    expect(errors.originality_score).toBe(SCORE_REQUIRED);
    expect(errors.recommendation).toBe(RECOMMENDATION_REQUIRED);
    expect(errors.comments_for_author).toBe(COMMENTS_REQUIRED);
    expect(errors.declaration).toBe(DECLARATION_REQUIRED);
  });

  it('falta un solo puntaje: solo ese campo falla', () => {
    expect(submitErrors({ ...complete(), clarity_score: null }, true)).toEqual({
      clarity_score: SCORE_REQUIRED,
    });
  });

  it.each([0, 6, -1])('el puntaje %i fuera de 1–5 no vale', (score) => {
    expect(submitErrors({ ...complete(), ethics_score: score }, true).ethics_score).toBe(
      SCORE_REQUIRED,
    );
  });

  it('los comentarios solo con espacios no cuentan', () => {
    expect(submitErrors({ ...complete(), comments_for_author: '   \n ' }, true)).toEqual({
      comments_for_author: COMMENTS_REQUIRED,
    });
  });

  it('los comentarios confidenciales son opcionales', () => {
    expect(submitErrors({ ...complete(), confidential_comments: '' }, true)).toEqual({});
  });

  it('los comentarios no pueden superar el máximo', () => {
    const long = 'a'.repeat(COMMENT_MAX_LENGTH + 1);

    expect(submitErrors({ ...complete(), comments_for_author: long }, true)).toEqual({
      comments_for_author: COMMENTS_TOO_LONG,
    });
  });

  it('sin declaración falla aunque todo lo demás esté completo', () => {
    expect(submitErrors(complete(), false)).toEqual({ declaration: DECLARATION_REQUIRED });
  });
});

describe('serverFieldErrors', () => {
  it('toma el primer mensaje de cada campo conocido', () => {
    expect(
      serverFieldErrors({
        clarity_score: ['Este campo es obligatorio para enviar la evaluación.'],
        recommendation: 'Falta.',
      }),
    ).toEqual({
      clarity_score: 'Este campo es obligatorio para enviar la evaluación.',
      recommendation: 'Falta.',
    });
  });

  it('ignora campos desconocidos y detalles que no son un objeto', () => {
    expect(serverFieldErrors({ lock_version: 3, status: ['x'] })).toEqual({});
    expect(serverFieldErrors(null)).toEqual({});
    expect(serverFieldErrors('error')).toEqual({});
  });
});
