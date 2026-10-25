/**
 * Clasificación de rutas de la API compartida por los interceptores
 * (plan sección 3.7).
 *
 * La URL base se inyecta por entorno (`API_BASE_URL`, terminada en
 * `/api/`), de modo que los helpers aceptan tanto rutas relativas
 * (`/api/auth/login/`) como absolutas con origen.
 */

/** Endpoints que nunca llevan `Authorization` ni disparan refresh. */
const PUBLIC_API_PATTERNS: readonly RegExp[] = [
  /^\/api\/auth\/login\/?$/,
  /^\/api\/auth\/refresh\/?$/,
  /^\/api\/catalog(\/|$)/,
];

/** Ruta de cualquier URL, absoluta o relativa al origen. */
export function apiPath(url: string): string {
  try {
    return new URL(url, 'http://gpc.local').pathname;
  } catch {
    return url;
  }
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
