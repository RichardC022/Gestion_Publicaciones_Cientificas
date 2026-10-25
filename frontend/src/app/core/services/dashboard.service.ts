import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, catchError, throwError } from 'rxjs';

import { API_BASE_URL } from '../http/api-base-url.token';
import { toApiError } from '../models/api-error.model';
import { DashboardResponse } from '../models/dashboard.model';

/**
 * Panel unificado en una sola respuesta (plan secciones 2.2 y 3.4).
 *
 * Una única llamada a `GET /api/dashboard/` devuelve todas las
 * secciones habilitadas por los roles activos; el panel nunca exige
 * elegir rol y ninguna vista vuelve a pedir el panel por sección.
 */
@Injectable({ providedIn: 'root' })
export class DashboardService {
  private readonly http = inject(HttpClient);
  private readonly baseUrl = inject(API_BASE_URL);

  getDashboard(): Observable<DashboardResponse> {
    return this.http
      .get<DashboardResponse>(`${this.baseUrl}dashboard/`)
      .pipe(catchError((error) => throwError(() => toApiError(error))));
  }
}
