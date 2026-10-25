import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { catchError, switchMap, throwError } from 'rxjs';

import { AuthService } from '../auth/auth.service';
import { withAuthorization } from '../auth/auth.interceptor';
import { ApiError, toApiError } from '../models/api-error.model';
import { ApiFeedbackStore } from './api-feedback.store';
import { isApiRequest, isPublicApiRequest } from './api-url';

/**
 * Intercepta los errores de la API (plan sección 3.7):
 *
 * * `401` en un endpoint protegido: intenta refrescar la sesión UNA
 *   sola vez (`refreshOnce` compartido) y reintenta la petición con el
 *   token nuevo. Si el refresh falla, limpia la sesión y redirige a
 *   `/login`. Login, refresh y catálogo público nunca refrescan.
 * * `403`, `404`, `409`, `413`, `415`, `429` y `5xx`: normalizan el
 *   fallo a `ApiError` y publican el mensaje accionable en el almacén
 *   de feedback (el shell lo renderiza en TSK-26). El `429` respeta el
 *   `Retry-After` del backend y lo expone para deshabilitar acciones.
 * * Todo error sale de la capa HTTP ya normalizado a `ApiError`.
 */
export const errorInterceptor: HttpInterceptorFn = (req, next) => {
  const auth = inject(AuthService);
  const feedback = inject(ApiFeedbackStore);

  return next(req).pipe(
    catchError((raw: unknown) => {
      if (!(raw instanceof HttpErrorResponse)) {
        return throwError(() => toApiError(raw));
      }

      const apiError = toApiError(raw);
      const requestUrl = raw.url ?? req.url;
      const isProtectedApi = isApiRequest(requestUrl) && !isPublicApiRequest(requestUrl);

      // 401 en endpoint protegido: un único refresh y reintento.
      if (raw.status === 401 && isProtectedApi) {
        return auth.refreshOnce().pipe(
          switchMap((access) => next(withAuthorization(req, access))),
          catchError(() => {
            // Refresh fallido: sesión limpia y vuelta a login.
            auth.handleSessionExpired();
            return throwError(() => apiError);
          }),
        );
      }

      if (shouldShowFeedback(apiError)) {
        feedback.show(apiError);
      }
      return throwError(() => apiError);
    }),
  );
};

/**
 * Mensajes globales solo para fallos que ningún formulario controla:
 * `400` lo maneja el formulario con los detalles del envelope y el
 * `401` pertenece al flujo de sesión.
 */
function shouldShowFeedback(apiError: ApiError): boolean {
  const globalStatuses = new Set([403, 404, 409, 410, 413, 415, 429]);
  return globalStatuses.has(apiError.status) || apiError.status >= 500;
}
