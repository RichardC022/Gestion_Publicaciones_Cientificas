import { HttpParams } from '@angular/common/http';

/**
 * Query params de un filtro de listado: solo viajan los que tienen valor.
 * Un parámetro vacío, nulo o `false` no se envía.
 */
export function toHttpParams(params: object): HttpParams {
  let httpParams = new HttpParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '' || value === false) {
      continue;
    }
    httpParams = httpParams.set(key, String(value));
  }
  return httpParams;
}
