import { HttpClient, HttpParams, HttpResponse } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, catchError, map, throwError } from 'rxjs';

import { API_BASE_URL } from '../http/api-base-url.token';
import { toApiError } from '../models/api-error.model';
import {
  Manuscript,
  ManuscriptListParams,
  ManuscriptPayload,
  ManuscriptSnapshot,
} from '../models/manuscript.model';
import { Paginated } from '../models/paginated.model';

/**
 * Manuscritos del Autor (plan secciones 2.3 y 3.6).
 *
 * Cubre el listado, el detalle y el alta/edición de metadatos. La carga
 * de PDF, el envío formal, las versiones, la baja y las descargas se
 * agregan en la TSK-44 sobre este mismo servicio.
 *
 * Las lecturas y escrituras de un manuscrito devuelven su `ETag`: el
 * `PATCH` lo reenvía en `If-Match` (bloqueo optimista, plan 2.11).
 */
@Injectable({ providedIn: 'root' })
export class ManuscriptService {
  private readonly http = inject(HttpClient);
  private readonly baseUrl = inject(API_BASE_URL);

  private get url(): string {
    return `${this.baseUrl}manuscripts/`;
  }

  list(params: ManuscriptListParams = {}): Observable<Paginated<Manuscript>> {
    return this.http
      .get<Paginated<Manuscript>>(this.url, { params: toHttpParams(params) })
      .pipe(catchError((error) => throwError(() => toApiError(error))));
  }

  get(id: string): Observable<ManuscriptSnapshot> {
    return this.http.get<Manuscript>(`${this.url}${id}/`, { observe: 'response' }).pipe(
      map(toSnapshot),
      catchError((error) => throwError(() => toApiError(error))),
    );
  }

  create(payload: ManuscriptPayload): Observable<ManuscriptSnapshot> {
    return this.http.post<Manuscript>(this.url, payload, { observe: 'response' }).pipe(
      map(toSnapshot),
      catchError((error) => throwError(() => toApiError(error))),
    );
  }

  /** `etag` es el valor devuelto al leer el manuscrito, comillas incluidas. */
  update(
    id: string,
    payload: Partial<ManuscriptPayload>,
    etag: string,
  ): Observable<ManuscriptSnapshot> {
    return this.http
      .patch<Manuscript>(`${this.url}${id}/`, payload, {
        observe: 'response',
        headers: { 'If-Match': etag },
      })
      .pipe(
        map(toSnapshot),
        catchError((error) => throwError(() => toApiError(error))),
      );
  }
}

function toSnapshot(response: HttpResponse<Manuscript>): ManuscriptSnapshot {
  return { manuscript: response.body as Manuscript, etag: response.headers.get('ETag') };
}

/** Solo viajan los filtros con valor: un parámetro vacío no se envía. */
function toHttpParams(params: ManuscriptListParams): HttpParams {
  let httpParams = new HttpParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '' || value === false) {
      continue;
    }
    httpParams = httpParams.set(key, String(value));
  }
  return httpParams;
}
