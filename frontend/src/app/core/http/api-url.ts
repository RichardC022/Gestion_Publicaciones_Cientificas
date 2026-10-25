/**
 * Clasificación y normalización de rutas de la API compartida por los
 * interceptores (plan sección 3.7).
 *
 * La URL base se inyecta por entorno (`API_BASE_URL`, terminada en
 * `/api/`), de modo que los helpers aceptan tanto rutas absolutas
 * (`/api/auth/login/`) como URLs con origen.
 *
 * INVARIANTE (TSK-26 fix): toda petición que llega al backend lleva
 * SIEMPRE un slash absoluto. Una ruta relativa como `api/auth/refresh`
 * el navegador la resolvería contra la URL del documento (p. ej.
 * desde `/catalog` -> `/catalogapi/auth/refresh`, un URL malformado
 * que Nginx responde con index.html). El interceptor más externo la
 * normaliza a `/api/auth/refresh` antes de que salga al navegador.
 */

/** Endpoints que nunca llevan `Authorization` ni disparan refresh. */
const PUBLIC_API_PATTERNS: readonly RegExp[] = [
  /^\/api\/auth\/login\/?$/,
  /^\/api\/auth\/refresh\/?$/,
  /^\/api\/catalog(\/|$)/,
];

/** Indica si la URL es relativa (sin slash inicial ni esquema). */
function isRelative(url: string): boolean {
  return !url.startsWith('/') && !/^[a-z][a-z0-9+.-]*:/i.test(url);
}

/**
 * Ruta absoluta de la URL: las relativas se normalizan anteponiendo
 * el slash (la regla del invariante), las absolutas se toman tal cual.
 */
export function apiPath(url: string): string {
  const candidate = isRelative(url) ? `/${url}` : url;
  try {
    return new URL(candidate, 'http://gpc.local').pathname;
  } catch {
    return candidate;
  }
}

/**
 * Garantiza el slash absoluto de una URL de API:
 * `api/auth/refresh/` -> `/api/auth/refresh/`. Las que ya lo llevan
 * pasan intactas.
 */
export function ensureAbsoluteApiUrl(url: string): string {
  return isRelative(url) ? `/${url}` : url;
}

/** Indica si la solicitud apunta a la API REST. */
export function isApiRequest(url: string): boolean {
  return apiPath(url).startsWith('/api/');
}

/**
 * Endpoints públicos: login, refresh y catálogo. El interceptor de
 * autenticación no les añade `Authorization` y el de errores no
 * intenta refrescar la sesión al fallar.
 */
export function isPublicApiRequest(url: string): boolean {
  const path = apiPath(url);
  return PUBLIC_API_PATTERNS.some((pattern) => pattern.test(path));
}
