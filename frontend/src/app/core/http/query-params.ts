import { HttpParams } from '@angular/common/http';
import { ParamMap } from '@angular/router';

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

/** Página de la URL; un valor que no es un entero mayor que 1 se ignora. */
export function toPage(params: ParamMap): number {
  const page = Number.parseInt(params.get('page') ?? '', 10);
  return Number.isInteger(page) && page > 1 ? page : 1;
}
