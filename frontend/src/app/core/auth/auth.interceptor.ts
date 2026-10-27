import { HttpRequest, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';

import { isApiRequest, isPublicApiRequest } from '../http/api-url';
import { AuthStore } from './auth.store';

/**
 * Añade `Authorization: Bearer <access>` a las peticiones de la API,
 * salvo login, refresh y catálogo público (plan sección 3.7).
 *
 * El token se lee de la señal del AuthStore en cada solicitud: jamás
 * se persiste en `localStorage` ni se expone por otra vía.
 */
export const authInterceptor: HttpInterceptorFn = (req, next) => {
  if (!isApiRequest(req.url) || isPublicApiRequest(req.url)) {
    return next(req);
  }
  const store = inject(AuthStore);
  return next(withAuthorization(req, store.accessToken()));
};

/**
 * Devuelve la petición con el bearer indicado (o sin cambios cuando no
 * hay token). La comparte el interceptor de errores para reintentar
 * con el token renovado.
 */
export function withAuthorization(
  req: HttpRequest<unknown>,
  token: string | null,
): HttpRequest<unknown> {
  if (token === null) {
    return req;
  }
  return req.clone({ setHeaders: { Authorization: `Bearer ${token}` } });
}
