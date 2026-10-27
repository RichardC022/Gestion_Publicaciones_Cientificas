import { ApiError } from '../../core/models/api-error.model';
import {
  SUBMISSION_FIELD_LABELS,
  missingSubmissionFields,
  submissionErrorMessage,
} from './submission-messages';

const apiError = (overrides: Partial<ApiError>): ApiError => ({
  status: 400,
  code: 'VALIDATION_ERROR',
  message: 'Mensaje del servidor.',
  userMessage: 'Mensaje accionable.',
  details: {},
  requestId: 'rid-1',
  retryAfterSeconds: null,
  ...overrides,
});

describe('missingSubmissionFields', () => {
  it('traduce los campos señalados por el servidor, en el orden del formulario', () => {
    const details = { authors: ['x'], title: ['x'], draft_file: ['x'], keywords: ['x'] };

    expect(missingSubmissionFields(details)).toEqual([
      'Título',
      'Palabras clave',
      'Autores',
      'PDF del manuscrito',
    ]);
  });

  it('ignora claves que no son campos del envío', () => {
    expect(missingSubmissionFields({ changes: ['sin cambios'], otro: ['x'] })).toEqual([]);
  });

  it.each([[null], [undefined], ['texto'], [42], [[]]])('con %j no hay campos', (details) => {
    expect(missingSubmissionFields(details)).toEqual([]);
  });

  it('cubre todos los metadatos obligatorios de CA-HU-04-02', () => {
    expect(Object.keys(SUBMISSION_FIELD_LABELS)).toEqual([
      'title',
      'abstract',
      'keywords',
      'area',
      'language',
      'authors',
      'draft_file',
    ]);
  });
});

describe('submissionErrorMessage', () => {
  it('un 400 de validación usa el texto del servidor y añade lo que falta', () => {
    const message = submissionErrorMessage(
      apiError({
        message: 'Complete los campos obligatorios antes de enviar el manuscrito.',
        details: { title: ['x'], area: ['x'] },
      }),
    );

    expect(message).toBe(
      'Complete los campos obligatorios antes de enviar el manuscrito. Falta: Título, Área de conocimiento.',
    );
  });

  it('«sin cambios» se muestra tal cual, sin lista de faltantes', () => {
    const message = submissionErrorMessage(
      apiError({
        message:
          'La nueva versión no cambia ni el PDF ni los metadatos; debe existir al menos una corrección.',
        details: { changes: ['x'] },
      }),
    );

    expect(message).toBe(
      'La nueva versión no cambia ni el PDF ni los metadatos; debe existir al menos una corrección.',
    );
  });

  it('un PDF inválido muestra el motivo exacto del servidor', () => {
    expect(
      submissionErrorMessage(
        apiError({ code: 'PDF_INVALID', message: 'El PDF está protegido o cifrado.' }),
      ),
    ).toBe('El PDF está protegido o cifrado.');
  });

  it.each([
    [{ status: 503, code: 'AUDIT_UNAVAILABLE' }],
    [{ status: 413, code: 'PDF_TOO_LARGE' }],
    [{ status: 409, code: 'STATE_CONFLICT' }],
    [{ status: 0, code: 'NETWORK_ERROR' }],
  ])('%j usa el mensaje accionable', (overrides) => {
    expect(submissionErrorMessage(apiError(overrides))).toBe('Mensaje accionable.');
  });
});
