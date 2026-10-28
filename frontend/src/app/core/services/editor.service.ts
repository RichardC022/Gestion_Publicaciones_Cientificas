import { HttpClient, HttpResponse } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, catchError, map, throwError } from 'rxjs';

import { API_BASE_URL } from '../http/api-base-url.token';
import { toHttpParams } from '../http/query-params';
import {
  Assignment,
  EditorEvaluation,
  EligibleReviewersPage,
  Incident,
  IncidentFilter,
  IncidentResolution,
  RevocationCause,
  StartReviewResult,
  SubmissionDetail,
  SubmissionListParams,
  SubmissionRow,
  SubmissionSnapshot,
  Verdict,
  VerdictRegistered,
  VerdictRequest,
  VerdictResult,
} from '../models/editor.model';
import { toApiError } from '../models/api-error.model';
import { Paginated } from '../models/paginated.model';

/**
 * Módulo Editor (plan secciones 2.4 y 3.6): bandeja de nuevos envíos,
 * detalle editorial, paso a revisión, selección de Revisores, asignación,
 * revocación, asignaciones vencidas, evaluaciones y veredicto.
 *
 * La descarga del PDF de una versión no vive aquí: el Editor usa el mismo
 * endpoint autorizado que el Autor (`ManuscriptService.downloadVersion`).
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

  /**
   * Revisores elegibles para el manuscrito (`GET .../reviewers/`): área,
   * disponibilidad y sin conflicto de interés. Si no queda ninguno, la
   * respuesta trae `diagnosis` con la causa.
   */
  listEligibleReviewers(manuscriptId: string, pageSize = 100): Observable<EligibleReviewersPage> {
    return this.http
      .get<EligibleReviewersPage>(`${this.url}reviewers/`, {
        params: toHttpParams({ manuscript_id: manuscriptId, page_size: pageSize }),
      })
      .pipe(catchError((error) => throwError(() => toApiError(error))));
  }

  /**
   * Asigna al Revisor (`POST .../assignments/`). El plazo (`due_at`) lo
   * fija el servidor: la respuesta trae la fecha límite definitiva.
   */
  assignReviewer(manuscriptId: string, reviewerId: string): Observable<Assignment> {
    return this.http
      .post<Assignment>(`${this.url}manuscripts/${manuscriptId}/assignments/`, {
        reviewer_id: reviewerId,
      })
      .pipe(catchError((error) => throwError(() => toApiError(error))));
  }

  /** Evaluaciones finales del manuscrito, con la identidad del Revisor (`GET .../evaluations/`). */
  listEvaluations(manuscriptId: string, pageSize = 100): Observable<Paginated<EditorEvaluation>> {
    return this.http
      .get<Paginated<EditorEvaluation>>(`${this.url}manuscripts/${manuscriptId}/evaluations/`, {
        params: toHttpParams({ page_size: pageSize }),
      })
      .pipe(catchError((error) => throwError(() => toApiError(error))));
  }

  /** Historial de veredictos, del más antiguo al más reciente (`GET .../verdicts/`). */
  listVerdicts(manuscriptId: string, pageSize = 100): Observable<Paginated<Verdict>> {
    return this.http
      .get<Paginated<Verdict>>(`${this.url}manuscripts/${manuscriptId}/verdicts/`, {
        params: toHttpParams({ page_size: pageSize }),
      })
      .pipe(catchError((error) => throwError(() => toApiError(error))));
  }

  /**
   * Registra el veredicto (`POST .../verdicts/`). `etag` es el del manuscrito
   * al leerlo (`If-Match`); `idempotencyKey` identifica esta intención:
   * reintentarla con la misma clave devuelve lo ya registrado en lugar de
   * duplicarlo.
   */
  createVerdict(
    manuscriptId: string,
    request: VerdictRequest,
    etag: string,
    idempotencyKey: string,
  ): Observable<VerdictRegistered> {
    return this.http
      .post<VerdictResult>(`${this.url}manuscripts/${manuscriptId}/verdicts/`, request, {
        observe: 'response',
        headers: { 'If-Match': etag, 'Idempotency-Key': idempotencyKey },
      })
      .pipe(
        map((response) => ({
          result: response.body as VerdictResult,
          etag: response.headers.get('ETag'),
        })),
        catchError((error) => throwError(() => toApiError(error))),
      );
  }

  /**
   * Asignaciones vencidas pendientes de decisión (`GET .../assignments/expired/`):
   * las que el servidor ya marcó `EXPIRED` y las `ACTIVE` con `due_at <= now()`
   * que la tarea programada aún no marcó. Es solo una consulta: nada se
   * revoca ni se reasigna.
   */
  listExpiredAssignments(page = 1, pageSize = 20): Observable<Paginated<Assignment>> {
    return this.http
      .get<Paginated<Assignment>>(`${this.url}assignments/expired/`, {
        params: toHttpParams({ page: page > 1 ? page : undefined, page_size: pageSize }),
      })
      .pipe(catchError((error) => throwError(() => toApiError(error))));
  }

  /** Revoca una asignación vigente o vencida, con causa y motivo (`POST .../revoke/`). */
  revokeAssignment(
    assignmentId: string,
    cause: RevocationCause,
    reason: string,
  ): Observable<Assignment> {
    return this.http
      .post<Assignment>(`${this.url}assignments/${assignmentId}/revoke/`, { cause, reason })
      .pipe(catchError((error) => throwError(() => toApiError(error))));
  }

  /**
   * Reportes confidenciales de los Revisores, los abiertos primero
   * (`GET .../incidents/`). `ALL` no filtra por estado.
   */
  listIncidents(filter: IncidentFilter, page = 1, pageSize = 20): Observable<Paginated<Incident>> {
    return this.http
      .get<Paginated<Incident>>(`${this.url}incidents/`, {
        params: toHttpParams({
          status: filter === 'ALL' ? undefined : filter,
          page: page > 1 ? page : undefined,
          page_size: pageSize,
        }),
      })
      .pipe(catchError((error) => throwError(() => toApiError(error))));
  }

  /**
   * Resuelve un reporte (`POST .../resolve/`). Solo se resuelve una vez: un
   * segundo intento responde `409`. Las dos primeras resoluciones revocan la
   * asignación y exigen el manuscrito en revisión.
   */
  resolveIncident(id: string, resolution: IncidentResolution): Observable<Incident> {
    return this.http
      .post<Incident>(`${this.url}incidents/${id}/resolve/`, { resolution })
      .pipe(catchError((error) => throwError(() => toApiError(error))));
  }
}

function toSnapshot(response: HttpResponse<SubmissionDetail>): SubmissionSnapshot {
  return { submission: response.body as SubmissionDetail, etag: response.headers.get('ETag') };
}
