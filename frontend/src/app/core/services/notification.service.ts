import { HttpClient } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { Observable, catchError, map, tap, throwError } from 'rxjs';

import { API_BASE_URL } from '../http/api-base-url.token';
import { toHttpParams } from '../http/query-params';
import { toApiError } from '../models/api-error.model';
import { Notice, NoticeFilter, NoticePage } from '../models/notification.model';

/**
 * Avisos propios del usuario autenticado (plan sección 2.8).
 *
 * Mantiene el contador de no leídos que muestra la campana: lo fija cada
 * lectura de la lista y lo ajusta cada marcado, de modo que se actualiza sin
 * recargar la página. El servidor solo devuelve avisos del propio usuario; el
 * aviso ajeno responde `404`.
 */
@Injectable({ providedIn: 'root' })
export class NotificationService {
  private readonly http = inject(HttpClient);
  private readonly baseUrl = inject(API_BASE_URL);

  private readonly unread = signal(0);

  /** Avisos propios sin leer (la campana lo muestra). */
  readonly unreadCount = this.unread.asReadonly();

  private get url(): string {
    return `${this.baseUrl}notifications/`;
  }

  /** Avisos del más reciente al más antiguo (`GET /api/notifications/`). */
  list(filter: NoticeFilter, page = 1, pageSize = 20): Observable<NoticePage> {
    return this.http
      .get<NoticePage>(this.url, {
        params: toHttpParams({
          read: filter === 'UNREAD' ? 'false' : undefined,
          page: page > 1 ? page : undefined,
          page_size: pageSize,
        }),
      })
      .pipe(
        tap((result) => this.unread.set(result.unread_count)),
        catchError((error) => throwError(() => toApiError(error))),
      );
  }

  /**
   * Lee solo el contador (la campana). Un fallo no molesta: el contador queda
   * como estaba y la lista de avisos mostrará el error si se abre.
   */
  refresh(): void {
    this.list('UNREAD', 1, 1).subscribe({ error: () => undefined });
  }

  /** Marca un aviso como leído (`PATCH .../{id}/read/`, idempotente). */
  markRead(notice: Notice): Observable<Notice> {
    return this.http.patch<Notice>(`${this.url}${encodeURIComponent(notice.id)}/read/`, {}).pipe(
      tap(() => {
        if (!notice.is_read) {
          this.unread.update((count) => Math.max(0, count - 1));
        }
      }),
      catchError((error) => throwError(() => toApiError(error))),
    );
  }

  /** Marca todos los avisos propios como leídos (`POST .../read-all/`). */
  markAllRead(): Observable<void> {
    return this.http.post<void>(`${this.url}read-all/`, {}).pipe(
      tap(() => this.unread.set(0)),
      map(() => undefined),
      catchError((error) => throwError(() => toApiError(error))),
    );
  }
}
