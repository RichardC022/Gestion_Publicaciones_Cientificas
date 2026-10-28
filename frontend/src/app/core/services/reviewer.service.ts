import { HttpClient, HttpResponse } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, catchError, map, throwError } from 'rxjs';

import { API_BASE_URL } from '../http/api-base-url.token';
import { blobErrorToApiError } from '../http/blob-download';
import { toHttpParams } from '../http/query-params';
import { toApiError } from '../models/api-error.model';
import { Paginated } from '../models/paginated.model';
import {
  AssignmentSnapshot,
  EvaluationDraft,
  EvaluationSnapshot,
  ReviewerAssignmentDetail,
  ReviewerAssignmentRow,
  ReviewerEvaluation,
  genericDocumentName,
} from '../models/reviewer.model';

/** PDF sanitizado descargado, con el nombre genérico con el que se guarda. */
export interface ReviewerDocument {
  blob: Blob;
  filename: string;
}

/**
 * Módulo Revisor (plan secciones 2.5 y 3.6): bandeja de asignaciones,
 * detalle anonimizado y descarga del PDF sanitizado.
 *
 * Todo lo que llega de estos endpoints ya está anonimizado por el
 * backend. El nombre del archivo descargado se construye aquí a partir
 * del código del manuscrito: el `Content-Disposition` del servidor no se
 * usa, de modo que ningún nombre original puede llegar al disco del Revisor.
 */
@Injectable({ providedIn: 'root' })
export class ReviewerService {
  private readonly http = inject(HttpClient);
  private readonly baseUrl = inject(API_BASE_URL);

  private get url(): string {
    return `${this.baseUrl}reviewer/`;
  }

  /** Bandeja del Revisor: solo sus propias asignaciones. */
  listAssignments(page = 1, pageSize = 20): Observable<Paginated<ReviewerAssignmentRow>> {
    return this.http
      .get<Paginated<ReviewerAssignmentRow>>(`${this.url}assignments/`, {
        params: toHttpParams({ page: page > 1 ? page : undefined, page_size: pageSize }),
      })
      .pipe(catchError((error) => throwError(() => toApiError(error))));
  }

  /**
   * Detalle anonimizado. Junto con la asignación devuelve la diferencia
   * entre el reloj del servidor (cabecera `Date`) y el del navegador.
   */
  getAssignment(id: string): Observable<AssignmentSnapshot> {
    return this.http
      .get<ReviewerAssignmentDetail>(`${this.url}assignments/${id}/`, { observe: 'response' })
      .pipe(
        map(toSnapshot),
        catchError((error) => throwError(() => toApiError(error))),
      );
  }

  /**
   * Borrador o evaluación final propia (`GET .../evaluation/`). Antes del
   * primer guardado llega vacía y con `ETag` `"0"`.
   */
  getEvaluation(assignmentId: string): Observable<EvaluationSnapshot> {
    return this.http
      .get<ReviewerEvaluation>(`${this.url}assignments/${assignmentId}/evaluation/`, {
        observe: 'response',
      })
      .pipe(
        map(toEvaluationSnapshot),
        catchError((error) => throwError(() => toApiError(error))),
      );
  }

  /**
   * Guarda el borrador (`PUT .../evaluation/`). `etag` es el de la última
   * lectura (`If-Match`): si otro guardado se adelantó el servidor responde
   * `409`. Con el plazo vencido responde `410` y el borrador previo se conserva.
   */
  saveDraft(
    assignmentId: string,
    draft: EvaluationDraft,
    etag: string,
  ): Observable<EvaluationSnapshot> {
    return this.http
      .put<ReviewerEvaluation>(`${this.url}assignments/${assignmentId}/evaluation/`, draft, {
        observe: 'response',
        headers: { 'If-Match': etag },
      })
      .pipe(
        map(toEvaluationSnapshot),
        catchError((error) => throwError(() => toApiError(error))),
      );
  }

  /**
   * Envío final e irreversible (`POST .../evaluation/submit/`). Exige los
   * cinco puntajes, la recomendación y los comentarios para el Autor ya
   * guardados con ese `ETag`.
   */
  submitEvaluation(assignmentId: string, etag: string): Observable<EvaluationSnapshot> {
    return this.http
      .post<ReviewerEvaluation>(
        `${this.url}assignments/${assignmentId}/evaluation/submit/`,
        {},
        { observe: 'response', headers: { 'If-Match': etag } },
      )
      .pipe(
        map(toEvaluationSnapshot),
        catchError((error) => throwError(() => toApiError(error))),
      );
  }

  /**
   * Descarga el PDF sanitizado (`GET .../document/`). Con una asignación
   * que ya no está `ACTIVE` el servidor responde `410`; el cuerpo del
   * error también llega como `Blob` y se convierte al envelope estándar.
   */
  downloadDocument(
    assignmentId: string,
    manuscriptCode: string,
    versionNumber: number,
  ): Observable<ReviewerDocument> {
    return this.http
      .get(`${this.url}assignments/${assignmentId}/document/`, {
        observe: 'response',
        responseType: 'blob',
      })
      .pipe(
        map((response) => ({
          blob: response.body as Blob,
          filename: genericDocumentName(manuscriptCode, versionNumber),
        })),
        catchError((error) => blobErrorToApiError(error)),
      );
  }
}

function toEvaluationSnapshot(response: HttpResponse<ReviewerEvaluation>): EvaluationSnapshot {
  return { evaluation: response.body as ReviewerEvaluation, etag: response.headers.get('ETag') };
}

function toSnapshot(response: HttpResponse<ReviewerAssignmentDetail>): AssignmentSnapshot {
  return {
    assignment: response.body as ReviewerAssignmentDetail,
    serverOffsetMs: serverOffset(response.headers.get('Date')),
  };
}

/**
 * Diferencia `servidor − navegador` según la cabecera `Date`. La cabecera
 * tiene precisión de segundos y el viaje de la respuesta la retrasa un poco,
 * así que es una referencia, no un cronómetro: el vencimiento real lo
 * decide el servidor (`410`/`409` al enviar). Sin cabecera válida, `0`.
 */
export function serverOffset(header: string | null, now: number = Date.now()): number {
  const server = header ? Date.parse(header) : Number.NaN;
  return Number.isNaN(server) ? 0 : server - now;
}
