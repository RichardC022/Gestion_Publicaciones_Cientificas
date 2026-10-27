import {
  HttpClient,
  HttpErrorResponse,
  HttpEvent,
  HttpEventType,
  HttpResponse,
} from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, catchError, filter, from, map, switchMap, throwError } from 'rxjs';

import { API_BASE_URL } from '../http/api-base-url.token';
import { toHttpParams } from '../http/query-params';
import { toApiError } from '../models/api-error.model';
import {
  DraftFileSummary,
  DraftUploadEvent,
  HistoryEntry,
  Manuscript,
  ManuscriptListParams,
  ManuscriptPayload,
  ManuscriptSnapshot,
  SubmissionResult,
  VersionDownload,
  VersionSummary,
  VersionUploadEvent,
} from '../models/manuscript.model';
import { Paginated } from '../models/paginated.model';

/**
 * Manuscritos del Autor (plan secciones 2.3 y 3.6).
 *
 * Cubre todo el módulo Autor: listado, detalle, alta y edición, carga del
 * PDF de borrador, envío formal, nuevas versiones, historial, descarga y
 * baja lógica. Los `POST` que no deben repetirse (envío y nueva versión)
 * llevan `Idempotency-Key`.
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
   * Envío formal (`POST .../submit/`): crea la versión v1 y la ronda 0 con
   * el PDF de borrador y los metadatos actuales. `idempotencyKey`
   * identifica esta intención de envío; reintentarla con la misma clave
   * devuelve el resultado ya registrado en lugar de duplicarlo.
   */
  submit(id: string, idempotencyKey: string): Observable<SubmissionResult> {
    return this.http
      .post<SubmissionResult>(`${this.url}${id}/submit/`, null, {
        headers: { 'Idempotency-Key': idempotencyKey },
      })
      .pipe(catchError((error) => throwError(() => toApiError(error))));
  }

  /** Versiones formales del manuscrito, de la más antigua a la más reciente. */
  listVersions(id: string, page = 1, pageSize = 100): Observable<Paginated<VersionSummary>> {
    return this.http
      .get<Paginated<VersionSummary>>(`${this.url}${id}/versions/`, {
        params: toHttpParams({ page: page > 1 ? page : undefined, page_size: pageSize }),
      })
      .pipe(catchError((error) => throwError(() => toApiError(error))));
  }

  /**
   * Nueva versión en `REQUIRES_CORRECTIONS` (`POST .../versions/`): sube el
   * PDF corregido; los metadatos son los vigentes del manuscrito. Emite el
   * avance y, al terminar, el resultado. Cancelar la suscripción aborta la
   * solicitud. Se reintenta con la MISMA `idempotencyKey`.
   */
  uploadVersion(id: string, file: File, idempotencyKey: string): Observable<VersionUploadEvent> {
    const body = new FormData();
    body.append('file', file, file.name);
    return this.http
      .post<SubmissionResult>(`${this.url}${id}/versions/`, body, {
        headers: { 'Idempotency-Key': idempotencyKey },
        observe: 'events',
        reportProgress: true,
      })
      .pipe(
        map(toVersionUploadEvent),
        filter((event): event is VersionUploadEvent => event !== null),
        catchError((error) => throwError(() => toApiError(error))),
      );
  }

  /**
   * Historial inmutable y cronológico del manuscrito: creación, cada
   * versión formal con el sello de su PDF, rondas, cambios de estado y la
   * baja (`GET .../history/`).
   */
  getHistory(id: string, page = 1, pageSize = 100): Observable<Paginated<HistoryEntry>> {
    return this.http
      .get<Paginated<HistoryEntry>>(`${this.url}${id}/history/`, {
        params: toHttpParams({ page: page > 1 ? page : undefined, page_size: pageSize }),
      })
      .pipe(catchError((error) => throwError(() => toApiError(error))));
  }

  /**
   * Descarga el PDF exacto de una versión (`GET .../versions/{id}/file/`).
   *
   * Pide el cuerpo como `Blob` y no expone rutas internas del volumen:
   * el backend autoriza y Nginx entrega el archivo. Si falla, el cuerpo
   * del error también llega como `Blob`; se lee para conservar el
   * envelope del backend.
   */
  downloadVersion(
    id: string,
    versionId: string,
    fallbackName: string,
  ): Observable<VersionDownload> {
    return this.http
      .get(`${this.url}${id}/versions/${versionId}/file/`, {
        observe: 'response',
        responseType: 'blob',
      })
      .pipe(
        map((response) => ({
          blob: response.body as Blob,
          filename: filenameFrom(response.headers.get('Content-Disposition')) ?? fallbackName,
        })),
        catchError((error) => blobErrorToApiError(error)),
      );
  }

  /**
   * Baja lógica (`POST .../withdraw/`): marca el manuscrito como dado de
   * baja sin borrar nada. El motivo es obligatorio en revisión y aceptado.
   */
  withdraw(id: string, reason: string | null): Observable<ManuscriptSnapshot> {
    return this.http
      .post<Manuscript>(`${this.url}${id}/withdraw/`, reason ? { reason } : {}, {
        observe: 'response',
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
function blobErrorToApiError(error: unknown): Observable<never> {
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

/** Igual que `toUploadEvent`, para la respuesta de una nueva versión. */
function toVersionUploadEvent(event: HttpEvent<SubmissionResult>): VersionUploadEvent | null {
  if (event.type === HttpEventType.UploadProgress) {
    return { kind: 'progress', percent: progressPercent(event.loaded, event.total) };
  }
  if (event.type === HttpEventType.Response) {
    return { kind: 'done', submission: event.body as SubmissionResult };
  }
  return null;
}

function progressPercent(loaded: number, total: number | undefined): number | null {
  return total ? Math.min(100, Math.round((loaded / total) * 100)) : null;
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
