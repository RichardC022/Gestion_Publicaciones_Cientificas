import { ApiEnvelope } from '../models/api-envelope.model';

/**
 * Cuerpos con el contrato universal del backend para `request.flush(...)`.
 *
 * `toApiError` elige el mensaje por el `code` de `errors[0]`, no por el estado
 * HTTP, así que una respuesta sin sobre se vería como `SERVER_ERROR`.
 */

/** Error del backend: una entrada en `errors` con el `details` original. */
export function errorEnvelope(
  code: string,
  message: string,
  details: unknown = {},
  requestId: string | null = 'rid-1',
): ApiEnvelope<null> {
  return {
    success: false,
    message,
    data: null,
    errors: [{ code, message, field: null, details }],
    meta: { request_id: requestId },
  };
}

/** Error de validación: una entrada por campo, como lo emite el backend. */
export function validationEnvelope(
  fields: Record<string, unknown>,
  message = 'Los datos enviados no son válidos.',
  requestId: string | null = 'rid-1',
): ApiEnvelope<null> {
  return {
    success: false,
    message,
    data: null,
    errors: Object.entries(fields).map(([field, details]) => ({
      code: 'VALIDATION_ERROR',
      message: firstMessage(details) || message,
      field,
      details,
    })),
    meta: { request_id: requestId },
  };
}

/** Éxito del backend con la carga en `data`. */
export function successEnvelope<T>(data: T, meta: ApiEnvelope['meta'] = {}): ApiEnvelope<T> {
  return {
    success: true,
    message: 'Operación exitosa.',
    data,
    errors: [],
    meta: { request_id: 'rid-1', ...meta },
  };
}

function firstMessage(value: unknown): string {
  if (typeof value === 'string') {
    return value;
  }
  if (Array.isArray(value)) {
    return value.map(firstMessage).find((text) => text) ?? '';
  }
  if (typeof value === 'object' && value !== null) {
    return Object.values(value).map(firstMessage).find((text) => text) ?? '';
  }
  return '';
}
