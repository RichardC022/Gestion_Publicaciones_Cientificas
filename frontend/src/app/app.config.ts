import { ApplicationConfig, provideBrowserGlobalErrorListeners } from '@angular/core';
import { provideHttpClient } from '@angular/common/http';
import { provideRouter } from '@angular/router';

import { environment } from '../environments/environment';
import { API_BASE_URL } from './core/http/api-base-url.token';
import { routes } from './app.routes';

/**
 * Composición raíz de la SPA: enrutador, cliente HTTP y URL base de la
 * API inyectada por entorno. Los interceptores de sesión y errores se
 * agregan en la Fase 1 (TSK-24).
 */
export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideRouter(routes),
    provideHttpClient(),
    { provide: API_BASE_URL, useValue: environment.apiBaseUrl },
  ],
};
