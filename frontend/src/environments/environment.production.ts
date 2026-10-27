/**
 * Entorno de producción.
 *
 * La SPA se sirve desde el mismo origen que la API (Nginx publica los
 * estáticos y proxya `/api/` al backend), por lo que la URL base es
 * relativa al origen.
 */
export const environment = {
  production: true,
  apiBaseUrl: '/api/'
};
