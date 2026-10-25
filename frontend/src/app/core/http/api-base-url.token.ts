import { InjectionToken } from '@angular/core';

/**
 * Token de inyección para la URL base de la API REST.
 *
 * El valor proviene de los archivos de entorno (`src/environments/`) y
 * se registra en `app.config.ts`; los componentes y servicios nunca
 * codifican la URL. Debe terminar en `/` (por ejemplo `/api/`) para que
 * los servicios concatenen rutas relativas.
 */
export const API_BASE_URL = new InjectionToken<string>('API_BASE_URL');
