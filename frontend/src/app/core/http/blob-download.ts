import { HttpErrorResponse } from '@angular/common/http';
import { Observable, from, map, switchMap, throwError } from 'rxjs';

import { toApiError } from '../models/api-error.model';

/** Nombre de archivo de `Content-Disposition`; nunca una ruta. */
export function filenameFrom(header: string | null): string | null {
  const match = header?.match(/filename\*?=(?:UTF-8'')?"?([^";]+)"?/i);
  if (!match) {
    return null;
  }
  const raw = match[1].trim();
  let name = raw;
  try {
    name = decodeURIComponent(raw);
  } catch {
    // Se conserva tal cual si no es una codificación válida.
  }
  name = name.split(/[\\/]/).pop() ?? '';
  return name || null;
}

/** Texto de un `Blob` sin depender de `Blob.text()` (no está en todos los entornos). */
function blobText(blob: Blob): Promise<string> {
  if (typeof blob.text === 'function') {
    return blob.text();
  }
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error);
    reader.readAsText(blob);
  });
}

/** Un error con cuerpo `Blob` se lee como JSON para recuperar el envelope. */
export function blobErrorToApiError(error: unknown): Observable<never> {
  if (error instanceof HttpErrorResponse && error.error instanceof Blob) {
    return from(blobText(error.error)).pipe(
      map((text) => {
        try {
          return JSON.parse(text) as unknown;
        } catch {
          return null;
        }
      }),
      switchMap((body) =>
        throwError(() =>
          toApiError(
            new HttpErrorResponse({
              status: error.status,
              statusText: error.statusText,
              headers: error.headers,
              url: error.url ?? undefined,
              error: body,
            }),
          ),
        ),
      ),
    );
  }
  return throwError(() => toApiError(error));
}
