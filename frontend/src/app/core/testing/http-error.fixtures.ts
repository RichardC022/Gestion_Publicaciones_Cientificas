/**
 * Errores HTTP con el contrato universal del backend (`{ success, message, data, errors, meta }`).
 *
 * `toApiError` elige el mensaje por el `code` del cuerpo, no por el estado,
 * así que una respuesta sin sobre se vería como `SERVER_ERROR`. Estos casos
 * sirven para simular `403`, `404`, `409` y `410` en las pruebas de pantalla.
 */
import { ApiEnvelope } from '../models/api-envelope.model';
import { errorEnvelope } from './api-envelope.fixtures';

export interface HttpErrorCase {
  status: number;
  body: ApiEnvelope<null>;
  /** Fragmento del mensaje que la pantalla debe mostrar al usuario. */
  shown: string;
}

export const HTTP_ERROR_CASES: ReadonlyArray<HttpErrorCase> = [
  {
    status: 403,
    body: errorEnvelope('FORBIDDEN', 'No autorizado.'),
    shown: 'Acceso denegado',
  },
  {
    status: 404,
    body: errorEnvelope('NOT_FOUND', 'No encontrado.'),
    shown: 'no existe',
  },
  {
    status: 409,
    body: errorEnvelope('STATE_CONFLICT', 'Estado en conflicto.'),
    shown: 'no es válida en el estado actual',
  },
  {
    status: 410,
    body: errorEnvelope('GONE', 'El recurso ya no está disponible.'),
    shown: 'ya no está disponible',
  },
];

/** Respuesta de error lista para `request.flush(body, init)`. */
export function errorResponse(
  testCase: HttpErrorCase,
): [HttpErrorCase['body'], { status: number; statusText: string }] {
  return [testCase.body, { status: testCase.status, statusText: 'Error' }];
}
