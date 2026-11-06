import { HttpInterceptorFn, HttpResponse } from '@angular/common/http';
import { map } from 'rxjs';

import { isApiEnvelope, unwrapSuccess } from '../models/api-envelope.model';

/**
 * Desenvuelve el contrato universal `{ success, message, data, errors, meta }`
 * de los éxitos: el resto de la SPA recibe la carga de dominio (o la página
 * `{ count, next, previous, results }`) y no conoce el sobre.
 *
 * Es el interceptor más interno: actúa antes que el de errores. Los fallos HTTP
 * no pasan por aquí (los normaliza `toApiError`) y los cuerpos que no cumplen el
 * contrato (descargas `Blob`, respuestas ajenas a la API) se dejan intactos.
 */
export const envelopeInterceptor: HttpInterceptorFn = (req, next) =>
  next(req).pipe(
    map((event) => {
      if (event instanceof HttpResponse && isApiEnvelope(event.body) && event.body.success) {
        return event.clone({ body: unwrapSuccess(event.body) });
      }
      return event;
    }),
  );
