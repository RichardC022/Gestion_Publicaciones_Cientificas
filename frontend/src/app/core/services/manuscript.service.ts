import {
  HttpClient,
  HttpEvent,
  HttpEventType,
  HttpParams,
  HttpResponse,
} from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, catchError, filter, map, throwError } from 'rxjs';

import { API_BASE_URL } from '../http/api-base-url.token';
import { toApiError } from '../models/api-error.model';
import {
  DraftFileSummary,
  DraftUploadEvent,
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

  /**
   * Adjunta o reemplaza el PDF de borrador (`POST .../draft-file/`).
   *
   * Emite el avance de la carga y, al terminar, el resumen del archivo
   * (`201` primera carga, `200` reemplazo). Cancelar la suscripción
   * aborta la solicitud. No crea versión, ronda ni instantánea.
   *
   * No se fija `Content-Type`: el navegador lo completa con el límite
   * (`boundary`) del `multipart/form-data`.
   */
  uploadDraft(id: string, file: File): Observable<DraftUploadEvent> {
    const body = new FormData();
    body.append('file', file, file.name);
    return this.http
      .post<DraftFileSummary>(`${this.url}${id}/draft-file/`, body, {
        observe: 'events',
        reportProgress: true,
      })
      .pipe(
        map(toUploadEvent),
        filter((event): event is DraftUploadEvent => event !== null),
        catchError((error) => throwError(() => toApiError(error))),
      );
  }
}

/** Solo interesan el avance y la respuesta final; el resto de eventos se descarta. */
function toUploadEvent(event: HttpEvent<DraftFileSummary>): DraftUploadEvent | null {
  if (event.type === HttpEventType.UploadProgress) {
    const percent = event.total
      ? Math.min(100, Math.round((event.loaded / event.total) * 100))
      : null;
    return { kind: 'progress', percent };
  }
  if (event.type === HttpEventType.Response) {
    return { kind: 'done', draft: event.body as DraftFileSummary, replaced: event.status === 200 };
  }
  return null;
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
