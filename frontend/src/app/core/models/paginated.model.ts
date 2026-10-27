/**
 * Envelope estándar de listas paginadas de la API (plan sección 2.1).
 *
 * `page` y `page_size` viajan como query params; el servidor nunca
 * devuelve más de 100 resultados por página.
 */
export interface Paginated<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}
