import { ApplicationConfig, inject, provideAppInitializer, provideBrowserGlobalErrorListeners } from '@angular/core';
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { provideRouter } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { environment } from '../environments/environment';
import { routes } from './app.routes';
import { authInterceptor } from './core/auth/auth.interceptor';
import { AuthService } from './core/auth/auth.service';
import { API_BASE_URL } from './core/http/api-base-url.token';
import { errorInterceptor } from './core/http/error.interceptor';
import { requestIdInterceptor } from './core/http/request-id.interceptor';

/**
 * Composición raíz de la SPA: enrutador, cliente HTTP con los
 * interceptores de sesión y errores, y URL base de la API inyectada
 * por entorno (TSK-24).
 *
 * Orden de interceptores: el `X-Request-ID` se añade primero y el
 * interceptor de errores (el más interno) reintenta con el token
 * renovado conservando las cabeceras ya aplicadas.
 */
export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideRouter(routes),
    provideHttpClient(
      withInterceptors([requestIdInterceptor, authInterceptor, errorInterceptor]),
    ),
    /**
     * Reconstruye la sesión desde la cookie `HttpOnly` antes de la
     * primera navegación (plan sección 3.7). Si el refresh falla, la
     * SPA arranca anónima y los guards (TSK-25) redirigen a `/login`
     * en las rutas internas.
     */
    provideAppInitializer(() => {
      const auth = inject(AuthService);
      return firstValueFrom(auth.restoreSession());
    }),
    { provide: API_BASE_URL, useValue: environment.apiBaseUrl },
  ],
};
