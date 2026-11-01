/**
 * Errores HTTP con el sobre real del backend (`{ error: { code, message } }`).
 *
 * `toApiError` elige el mensaje por el `code` del cuerpo, no por el estado,
 * así que una respuesta sin sobre se vería como `SERVER_ERROR`. Estos casos
 * sirven para simular `403`, `404`, `409` y `410` en las pruebas de pantalla.
 */
export interface HttpErrorCase {
  status: number;
  body: { error: { code: string; message: string } };
  /** Fragmento del mensaje que la pantalla debe mostrar al usuario. */
  shown: string;
}

export const HTTP_ERROR_CASES: ReadonlyArray<HttpErrorCase> = [
  {
    status: 403,
    body: { error: { code: 'FORBIDDEN', message: 'No autorizado.' } },
    shown: 'Acceso denegado',
  },
  {
    status: 404,
    body: { error: { code: 'NOT_FOUND', message: 'No encontrado.' } },
    shown: 'no existe',
  },
  {
    status: 409,
    body: { error: { code: 'STATE_CONFLICT', message: 'Estado en conflicto.' } },
    shown: 'no es válida en el estado actual',
  },
  {
    status: 410,
    body: { error: { code: 'GONE', message: 'El recurso ya no está disponible.' } },
    shown: 'ya no está disponible',
  },
];

/** Respuesta de error lista para `request.flush(body, init)`. */
export function errorResponse(
  testCase: HttpErrorCase,
): [HttpErrorCase['body'], { status: number; statusText: string }] {
  return [testCase.body, { status: testCase.status, statusText: 'Error' }];
}
