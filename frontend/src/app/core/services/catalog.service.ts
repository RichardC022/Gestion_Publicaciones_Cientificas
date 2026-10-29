import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, catchError, throwError } from 'rxjs';

import { API_BASE_URL } from '../http/api-base-url.token';
import { blobErrorToApiError } from '../http/blob-download';
import { toHttpParams } from '../http/query-params';
import { CatalogArticle, CatalogFilters } from '../models/catalog.model';
import { Paginated } from '../models/paginated.model';
import { toApiError } from '../models/api-error.model';

/**
 * Catálogo público (plan secciones 2.6 y 3.6): búsqueda, ficha y PDF.
 *
 * Los tres endpoints son anónimos: `/api/catalog/**` está en la lista de
 * rutas públicas, así que el interceptor de autenticación no añade
 * `Authorization` ni el de errores intenta refrescar una sesión. El
 * catálogo funciona igual con o sin sesión iniciada.
 */
@Injectable({ providedIn: 'root' })
export class CatalogService {
  private readonly http = inject(HttpClient);
  private readonly baseUrl = inject(API_BASE_URL);

  private get url(): string {
    return `${this.baseUrl}catalog/`;
  }

  /** Búsqueda y filtros combinados, paginados (`GET /api/catalog/`). */
  list(filters: CatalogFilters, page = 1, pageSize = 12): Observable<Paginated<CatalogArticle>> {
    return this.http
      .get<Paginated<CatalogArticle>>(this.url, {
        params: toHttpParams({
          ...filters,
          page: page > 1 ? page : undefined,
          page_size: pageSize,
        }),
      })
      .pipe(catchError((error) => throwError(() => toApiError(error))));
  }

  /** Ficha pública (`GET /api/catalog/{code}/`); un artículo no disponible responde `404`. */
  get(code: string): Observable<CatalogArticle> {
    return this.http
      .get<CatalogArticle>(`${this.url}${encodeURIComponent(code)}/`)
      .pipe(catchError((error) => throwError(() => toApiError(error))));
  }

  /**
   * PDF público (`GET /api/catalog/{code}/document/`). Un artículo retirado
   * responde `410`; uno que no es público, `404`; sin almacenamiento, `503`.
   */
  document(code: string): Observable<Blob> {
    return this.http
      .get(`${this.url}${encodeURIComponent(code)}/document/`, { responseType: 'blob' })
      .pipe(catchError((error) => blobErrorToApiError(error)));
  }
}
