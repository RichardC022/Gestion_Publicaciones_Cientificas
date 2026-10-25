import { HttpClient } from '@angular/common/http';
import { Injectable, Injector, inject } from '@angular/core';
import { Router } from '@angular/router';
import {
  Observable,
  catchError,
  finalize,
  map,
  of,
  share,
  throwError,
} from 'rxjs';

import { API_BASE_URL } from '../http/api-base-url.token';
import { ApiError, toApiError } from '../models/api-error.model';
import {
  LoginResponse,
  MeResponse,
  RefreshResponse,
} from '../models/session-user.model';
import { AuthStore } from './auth.store';

/**
 * Sesión institucional sobre la API REST (plan secciones 2.2 y 3.7).
 *
 * * El access token vive en memoria (AuthStore); el refresh token
 *   viaja en la cookie `HttpOnly`, de modo que login, refresh y logout
 *   se envían con `withCredentials: true`.
 *   Nada se persiste en `localStorage`.
 * * `refreshOnce()` comparte un único refresh entre todas las
 *   peticiones que reciben `401` a la vez: un solo intento por ola.
 * * `restoreSession()` reconstruye la sesión al recargar la página;
 *   si la cookie no sirve, la SPA queda anónima y los guards (TSK-25)
 *   redirigen a `/login`.
 */
@Injectable({ providedIn: 'root' })
export class AuthService {
  /**
   * `HttpClient` se resuelve perezosamente: el interceptor de errores
   * inyecta este servicio durante una petición y una referencia eager
   * de HttpClient cerraría una dependencia circular
   * (interceptor → AuthService → HttpClient → interceptor).
   */
  private readonly injector = inject(Injector);
  private readonly store = inject(AuthStore);
  private readonly router = inject(Router);
  private readonly baseUrl = inject(API_BASE_URL);

  private get http(): HttpClient {
    return this.injector.get(HttpClient);
  }

  /** Refresh compartido de la ola en curso; null cuando no hay uno activo. */
  private refresh$: Observable<string> | null = null;

  /** Valida credenciales institucionales y abre la sesión. */
  login(identifier: string, password: string): Observable<void> {
    return this.http
      .post<LoginResponse>(
        `${this.baseUrl}auth/login/`,
        { identifier, password },
        { withCredentials: true },
      )
      .pipe(
        map((response) => {
          this.store.setSession(response);
        }),
        catchError((error) => throwError(() => toApiError(error))),
      );
  }

  /**
   * Intenta refrescar la sesión una única vez por ola de `401`.
   *
   * La primera llamada dispara el refresh y las concurrentes comparten
   * el mismo observable; al terminar (éxito o error) el compartido se
   * descarta para que el siguiente `401` vuelva a intentar.
   */
  refreshOnce(): Observable<string> {
    if (this.refresh$ === null) {
      this.store.markRefreshing();
      this.refresh$ = this.http
        .post<RefreshResponse>(`${this.baseUrl}auth/refresh/`, {}, { withCredentials: true })
        .pipe(
          map((response) => {
            this.store.setSession(response);
            return response.access;
          }),
          finalize(() => {
            this.refresh$ = null;
          }),
          share(),
        );
    }
    return this.refresh$;
  }

  /**
   * Reconstruye la sesión desde la cookie `HttpOnly` al arrancar la SPA
   * (recarga de página, plan sección 3.7). Nunca falla: devuelve
   * `false` cuando no había sesión recuperable.
   */
  restoreSession(): Observable<boolean> {
    return this.http
      .post<RefreshResponse>(`${this.baseUrl}auth/refresh/`, {}, { withCredentials: true })
      .pipe(
        map((response) => {
          this.store.setSession(response);
          return true;
        }),
        catchError(() => {
          this.store.clear();
          return of(false);
        }),
      );
  }

  /** Relee identidad, roles activos y navegación (`GET /api/auth/me/`). */
  me(): Observable<MeResponse> {
    return this.http.get<MeResponse>(`${this.baseUrl}auth/me/`).pipe(
      map((response) => {
        this.store.updateUser(response.user, response.roles);
        return response;
      }),
      catchError((error) => throwError(() => toApiError(error))),
    );
  }

  /** Cierra la sesión: revoca el refresh en el backend y limpia la memoria. */
  logout(): Observable<void> {
    return this.http
      .post<void>(`${this.baseUrl}auth/logout/`, {}, { withCredentials: true })
      .pipe(
        map(() => {
          this.store.clear();
        }),
        catchError((error: unknown) => {
          // Sin sesión utilizable en el servidor, el estado local se
          // limpia igualmente; el error normalizado sube al llamador.
          this.store.clear();
          const apiError: ApiError = toApiError(error);
          return throwError(() => apiError);
        }),
      );
  }

  /**
   * Refresh fallido: limpia la sesión y redirige a `/login` con
   * `returnUrl` para volver a donde estaba la persona (plan 3.7).
   */
  handleSessionExpired(): void {
    this.store.clear();
    const current = this.router.url;
    if (current.startsWith('/login')) {
      return;
    }
    void this.router.navigate(['/login'], { queryParams: { returnUrl: current } });
  }
}
