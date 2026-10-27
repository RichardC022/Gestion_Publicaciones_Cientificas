import { HttpClient, HttpResponse } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, catchError, map, throwError } from 'rxjs';

import { API_BASE_URL } from '../http/api-base-url.token';
import { toHttpParams } from '../http/query-params';
import {
  StartReviewResult,
  SubmissionDetail,
  SubmissionListParams,
  SubmissionRow,
  SubmissionSnapshot,
} from '../models/editor.model';
import { toApiError } from '../models/api-error.model';
import { Paginated } from '../models/paginated.model';

/**
 * Módulo Editor (plan secciones 2.4 y 3.6): bandeja de nuevos envíos,
 * detalle editorial y paso a revisión.
 *
 * La descarga del PDF de una versión no vive aquí: el Editor usa el mismo
 * endpoint autorizado que el Autor (`ManuscriptService.downloadVersion`).
 * Las demás operaciones del módulo (asignación, veredicto) se añaden con
 * las pantallas que las usan.
 */
@Injectable({ providedIn: 'root' })
export class EditorService {
  private readonly http = inject(HttpClient);
  private readonly baseUrl = inject(API_BASE_URL);

  private get url(): string {
    return `${this.baseUrl}editor/`;
  }

  /** Bandeja de manuscritos `SUBMITTED` del ámbito del Editor. */
  listSubmissions(params: SubmissionListParams = {}): Observable<Paginated<SubmissionRow>> {
    return this.http
      .get<Paginated<SubmissionRow>>(`${this.url}submissions/`, { params: toHttpParams(params) })
      .pipe(catchError((error) => throwError(() => toApiError(error))));
  }

  getSubmission(id: string): Observable<SubmissionSnapshot> {
    return this.http
      .get<SubmissionDetail>(`${this.url}submissions/${id}/`, { observe: 'response' })
      .pipe(
        map(toSnapshot),
        catchError((error) => throwError(() => toApiError(error))),
      );
  }

  /**
   * Pasa el envío a `UNDER_REVIEW` (`POST .../start-review/`). El manuscrito
   * queda en revisión pendiente de asignar al Revisor.
   */
  startReview(id: string): Observable<StartReviewResult> {
    return this.http
      .post<StartReviewResult>(`${this.url}submissions/${id}/start-review/`, {})
      .pipe(catchError((error) => throwError(() => toApiError(error))));
  }
}

function toSnapshot(response: HttpResponse<SubmissionDetail>): SubmissionSnapshot {
  return { submission: response.body as SubmissionDetail, etag: response.headers.get('ETag') };
}
