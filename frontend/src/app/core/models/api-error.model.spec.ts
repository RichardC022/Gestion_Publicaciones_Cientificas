import { HttpErrorResponse } from '@angular/common/http';

import { ApiError, isApiError, toApiError } from './api-error.model';

const ENVELOPE_401 = {
  error: {
    code: 'AUTH_INVALID',
    message: 'Credenciales institucionales inválidas.',
    details: {},
    request_id: 'rid-1',
  },
};

describe('toApiError', () => {
  it('un 401 del backend conserva el mensaje genérico del envelope', () => {
    const error = new HttpErrorResponse({
      status: 401,
      statusText: 'Unauthorized',
      url: '/api/auth/login/',
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

  it('la falla de red sigue siendo el mensaje de conexión', () => {
    const apiError = toApiError(new Error('simulated network failure'));

    expect(apiError.status).toBe(0);
    expect(apiError.userMessage).toContain('No fue posible conectar');
  });
});
