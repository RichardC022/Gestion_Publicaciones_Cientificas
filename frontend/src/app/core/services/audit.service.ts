import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, catchError, throwError } from 'rxjs';

import { API_BASE_URL } from '../http/api-base-url.token';
import { toHttpParams } from '../http/query-params';
import { toApiError } from '../models/api-error.model';
import { AuditEvent, AuditEventDetail, AuditFilters } from '../models/audit.model';
import { Paginated } from '../models/paginated.model';

/**
 * Auditoría global del Administrador (plan sección 2.7).
 *
 * Solo el rol `ADMIN` accede (`403` para cualquier otro). Cada consulta
 * queda auditada por el propio backend; si no puede registrarla responde
 * `503` y no devuelve datos.
 */
@Injectable({ providedIn: 'root' })
export class AuditService {
  private readonly http = inject(HttpClient);
  private readonly baseUrl = inject(API_BASE_URL);

  private get url(): string {
    return `${this.baseUrl}admin/audit/`;
  }

  /** Eventos, del más reciente al más antiguo, con filtros combinados (`GET /api/admin/audit/`). */
  list(filters: AuditFilters, page = 1, pageSize = 25): Observable<Paginated<AuditEvent>> {
    return this.http
      .get<Paginated<AuditEvent>>(this.url, {
        params: toHttpParams({
          ...filters,
          page: page > 1 ? page : undefined,
          page_size: pageSize,
        }),
      })
      .pipe(catchError((error) => throwError(() => toApiError(error))));
  }

  /** Un evento por su identificador público (`GET /api/admin/audit/{id}/`). */
  get(id: string): Observable<AuditEventDetail> {
    return this.http
      .get<AuditEventDetail>(`${this.url}${encodeURIComponent(id)}/`)
      .pipe(catchError((error) => throwError(() => toApiError(error))));
  }
}
