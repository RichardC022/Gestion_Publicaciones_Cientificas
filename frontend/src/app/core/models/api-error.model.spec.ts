import { HttpErrorResponse } from '@angular/common/http';

import { errorEnvelope, validationEnvelope } from '../testing/api-envelope.fixtures';
import { ApiError, isApiError, toApiError } from './api-error.model';

const ENVELOPE_401 = errorEnvelope('AUTH_INVALID', 'Credenciales institucionales inválidas.');

describe('toApiError', () => {
  it('un 401 del backend conserva el mensaje genérico del envelope', () => {
    const error = new HttpErrorResponse({
      status: 401,
      statusText: 'Unauthorized',
      url: '/api/v1/auth/login/',
      error: ENVELOPE_401,
    });

    const apiError = toApiError(error);

    expect(apiError.status).toBe(401);
    expect(apiError.code).toBe('AUTH_INVALID');
    expect(apiError.message).toBe('Credenciales institucionales inválidas.');
    expect(apiError.requestId).toBe('rid-1');
  });

  it('es idempotente: no degrada un ApiError ya normalizado', () => {
    const original: ApiError = {
      status: 401,
      code: 'AUTH_INVALID',
      message: 'Credenciales institucionales inválidas.',
      userMessage: 'Su sesión no es válida o expiró. Inicie sesión de nuevo.',
      details: {},
      requestId: 'rid-1',
      retryAfterSeconds: null,
    };

    // Regresión TSK-26: el AuthService re-normalizaba el ApiError del
    // interceptor y el login mostraba "no fue posible conectar".
    expect(toApiError(original)).toBe(original);
    expect(isApiError(original)).toBe(true);
  });

  it('una caída de conexión del navegador (HttpErrorResponse con status 0) es un fallo de red, no del servidor', () => {
    const apiError = toApiError(
      new HttpErrorResponse({
        status: 0,
        statusText: 'Unknown Error',
        error: new ProgressEvent('error'),
      }),
    );

    expect(apiError.status).toBe(0);
    expect(apiError.code).toBe('NETWORK_ERROR');
    expect(apiError.userMessage).toContain('No fue posible conectar');
  });

  it('la falla de red sigue siendo el mensaje de conexión', () => {
    const apiError = toApiError(new Error('simulated network failure'));

    expect(apiError.status).toBe(0);
    expect(apiError.userMessage).toContain('No fue posible conectar');
  });
});

describe('toApiError con errores de validación por campo', () => {
  it('reconstruye details como { campo: detalle } desde errors', () => {
    const error = new HttpErrorResponse({
      status: 400,
      statusText: 'Bad Request',
      url: '/api/v1/manuscripts/',
      error: validationEnvelope({
        title: ['Este campo es obligatorio.'],
        authors: [{ name: ['Requerido.'] }],
      }),
    });

    const apiError = toApiError(error);

    expect(apiError.code).toBe('VALIDATION_ERROR');
    expect(apiError.details).toEqual({
      title: ['Este campo es obligatorio.'],
      authors: [{ name: ['Requerido.'] }],
    });
    expect(apiError.requestId).toBe('rid-1');
  });
});
