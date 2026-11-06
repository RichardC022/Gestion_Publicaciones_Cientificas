/**
 * Contrato JSON universal de la API: `{ success, message, data, errors, meta }`.
 *
 * Toda respuesta de `/api/v1/` llega con este sobre. Los servicios y los
 * componentes trabajan con la carga de dominio: `envelopeInterceptor` la
 * extrae de los éxitos y `toApiError` lee `errors` y `meta` de los fallos.
 */

/** Entrada de `errors`; `details` conserva el detalle original del backend. */
export interface ApiErrorEntry {
  code: string;
  message: string;
  field: string | null;
  details: unknown;
}

export interface ApiPaginationMeta {
  count: number;
  next: string | null;
  previous: string | null;
}

export interface ApiEnvelopeMeta {
  request_id?: string | null;
  pagination?: ApiPaginationMeta;
  /** Datos extra de una vista (p. ej. el `diagnosis` de revisores elegibles). */
  [key: string]: unknown;
}

export interface ApiEnvelope<T = unknown> {
  success: boolean;
  message: string;
  data: T;
  errors: ApiErrorEntry[];
  meta: ApiEnvelopeMeta;
}

/** Comprueba que el cuerpo cumple el contrato universal. */
export function isApiEnvelope(body: unknown): body is ApiEnvelope {
  if (typeof body !== 'object' || body === null) {
    return false;
  }
  const candidate = body as Record<string, unknown>;
  return (
    typeof candidate['success'] === 'boolean' &&
    typeof candidate['message'] === 'string' &&
    'data' in candidate &&
    Array.isArray(candidate['errors']) &&
    typeof candidate['meta'] === 'object' &&
    candidate['meta'] !== null
  );
}

/**
 * Carga de dominio de un éxito: `data`, o `{ count, next, previous, results }`
 * (más los extras de `meta`) cuando la respuesta es una página.
 */
export function unwrapSuccess(envelope: ApiEnvelope): unknown {
  const { pagination, request_id: _requestId, ...extras } = envelope.meta;
  if (!pagination) {
    return envelope.data;
  }
  return { ...pagination, results: envelope.data, ...extras };
}

/**
 * Reconstruye el `details` original de un error: un objeto `{ campo: detalle }`
 * cuando todas las entradas son de campo (validación), o el `details` de la
 * primera entrada en los demás casos.
 */
export function errorDetailsOf(entries: readonly ApiErrorEntry[]): unknown {
  if (entries.length > 0 && entries.every((entry) => typeof entry.field === 'string')) {
    return Object.fromEntries(entries.map((entry) => [entry.field as string, entry.details]));
  }
  return entries[0]?.details ?? {};
}
