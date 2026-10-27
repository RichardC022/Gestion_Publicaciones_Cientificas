import { HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';

import { ensureAbsoluteApiUrl, isApiRequest } from './api-url';

/** Cabecera de correlación aceptada por el middleware del backend. */
export const REQUEST_ID_HEADER = 'X-Request-ID';

/**
 * Añade `X-Request-ID` a cada petición de la API para correlacionar
 * logs y auditoría (plan sección 3.7).
 *
 * Además es la primera capa de la cadena y garantiza el invariante de
 * rutas: cualquier URL relativa de la API se convierte en absoluta
 * (`api/auth/refresh/` -> `/api/auth/refresh/`) para que el navegador
 * jamás la resuelva contra la ruta del documento (p. ej. `/catalog` ->
 * `/catalogapi/auth/refresh`).
 *
 * El backend sanitiza el valor entrante (`[A-Za-z0-9@._~-]{1,64}`);
 * `crypto.randomUUID()` cumple el patrón. En contextos no seguros
 * (HTTP sin localhost) `randomUUID` no existe y se usa el generador
 * de respaldo, que también cumple el patrón.
 */
export const requestIdInterceptor: HttpInterceptorFn = (req, next) => {
  if (!isApiRequest(req.url)) {
    return next(req);
  }

  const normalizedUrl = ensureAbsoluteApiUrl(req.url);
  const normalizedReq = normalizedUrl === req.url ? req : req.clone({ url: normalizedUrl });

  const requestId =
    normalizedReq.headers.get(REQUEST_ID_HEADER) ?? newRequestId();
  return next(
    normalizedReq.clone({ setHeaders: { [REQUEST_ID_HEADER]: requestId } }),
  );
};

function newRequestId(): string {
  const cryptoApi = globalThis.crypto;
  if (cryptoApi && typeof cryptoApi.randomUUID === 'function') {
    return cryptoApi.randomUUID();
  }
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
}
