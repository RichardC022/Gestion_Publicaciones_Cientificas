import { HttpErrorResponse, HttpHeaders } from '@angular/common/http';

/**
 * Error de API normalizado (plan sección 3.6).
 *
 * Todo fallo HTTP de la SPA se convierte a `ApiError` con `code`,
 * `message`, `details` y `request_id` del envelope del backend, más
 * `userMessage` accionable en español y `retryAfterSeconds` cuando la
 * respuesta incluye `Retry-After` (429 del límite de intentos).
 */
export interface ApiError {
  status: number;
  code: string;
  /** Mensaje del envelope del backend (o genérico si no llegó). */
  message: string;
  /** Mensaje accionable listo para mostrar en la interfaz. */
  userMessage: string;
  details: unknown;
  requestId: string | null;
  retryAfterSeconds: number | null;
}

interface ErrorEnvelope {
  error?: {
    code?: string;
    message?: string;
    details?: unknown;
    request_id?: string;
  };
}

/** Mensajes accionables por código de dominio (catálogo del plan 2.10). */
const MESSAGES_BY_CODE: Readonly<Record<string, string>> = {
  AUTH_INVALID: 'Su sesión no es válida o expiró. Inicie sesión de nuevo.',
  AUTH_LOCKED: 'Credenciales bloqueadas temporalmente. Espere unos instantes e intente de nuevo.',
  FORBIDDEN: 'Acceso denegado: su rol no habilita esta sección.',
  NOT_FOUND: 'El recurso solicitado no existe o no está disponible.',
  STATE_CONFLICT: 'La acción no es válida en el estado actual. Vuelva a cargar los datos e intente de nuevo.',
  VERSION_CONFLICT: 'Los datos cambiaron mientras los editaba. Vuelva a cargar e intente de nuevo.',
  ASSIGNMENT_CONFLICT: 'Ya existe una asignación activa. Vuelva a cargar los datos.',
  VERDICT_CONFLICT: 'Ya existe un veredicto registrado para esta versión.',
  PDF_TOO_LARGE: 'El archivo supera el límite de 50 MB.',
  PDF_INVALID: 'El archivo no es un PDF válido.',
  PDF_UNSUPPORTED: 'El tipo de contenido enviado no está soportado.',
  RATE_LIMITED: 'Demasiadas solicitudes. Espere unos instantes e intente de nuevo.',
  AUDIT_UNAVAILABLE: 'Servicio no disponible temporalmente. Intente de nuevo en unos minutos.',
  STORAGE_UNAVAILABLE: 'Servicio no disponible temporalmente. Intente de nuevo en unos minutos.',
  SERVER_ERROR: 'Error interno del servidor. Intente de nuevo más tarde.',
};

const MESSAGE_CONNECTION =
  'No fue posible conectar con el servidor. Verifique su conexión e intente de nuevo.';

const MESSAGES_BY_STATUS: Readonly<Record<number, string>> = {
  400: 'Los datos enviados no son válidos. Revise el formulario e intente de nuevo.',
  401: 'Su sesión no es válida o expiró. Inicie sesión de nuevo.',
  403: MESSAGES_BY_CODE['FORBIDDEN'],
  404: MESSAGES_BY_CODE['NOT_FOUND'],
  409: MESSAGES_BY_CODE['STATE_CONFLICT'],
  410: 'El recurso ya no está disponible.',
  413: MESSAGES_BY_CODE['PDF_TOO_LARGE'],
  415: MESSAGES_BY_CODE['PDF_UNSUPPORTED'],
  429: MESSAGES_BY_CODE['RATE_LIMITED'],
  500: MESSAGES_BY_CODE['SERVER_ERROR'],
  503: MESSAGES_BY_CODE['AUDIT_UNAVAILABLE'],
};

/** Convierte cualquier fallo HTTP o de red en un `ApiError` normalizado. */
export function toApiError(error: unknown): ApiError {
  if (!(error instanceof HttpErrorResponse)) {
    return {
      status: 0,
      code: 'NETWORK_ERROR',
      message: MESSAGE_CONNECTION,
      userMessage: MESSAGE_CONNECTION,
      details: {},
      requestId: null,
      retryAfterSeconds: null,
    };
  }

  const envelope = (error.error as ErrorEnvelope | null)?.error ?? {};
  const code = typeof envelope.code === 'string' && envelope.code ? envelope.code : 'SERVER_ERROR';
  const envelopeMessage =
    typeof envelope.message === 'string' && envelope.message ? envelope.message : '';
  const retryAfterSeconds = parseRetryAfter(error.headers);

  let userMessage =
    MESSAGES_BY_CODE[code] ??
    envelopeMessage ??
    MESSAGES_BY_STATUS[error.status] ??
    'La solicitud no pudo completarse. Intente de nuevo.';

  // 429 respeta el Retry-After del backend: la espera es parte del mensaje.
  if (retryAfterSeconds !== null) {
    userMessage = `Espere ${retryAfterSeconds} segundos e intente de nuevo.`;
  }

  return {
    status: error.status,
    code,
    message: envelopeMessage || userMessage,
    userMessage,
    details: envelope.details ?? {},
    requestId: typeof envelope.request_id === 'string' ? envelope.request_id : null,
    retryAfterSeconds,
  };
}

/** Lee `Retry-After` en segundos; cualquier otro formato se ignora. */
function parseRetryAfter(headers: HttpHeaders | null): number | null {
  const raw = headers?.get('Retry-After');
  if (!raw) {
    return null;
  }
  const seconds = Number.parseInt(raw, 10);
  return Number.isFinite(seconds) && seconds > 0 ? seconds : null;
}
