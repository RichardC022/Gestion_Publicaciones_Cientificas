import { ApiError } from '../../core/models/api-error.model';

/** Campos que el backend puede reportar como faltantes al enviar (HU-04). */
export const SUBMISSION_FIELD_LABELS: Readonly<Record<string, string>> = {
  title: 'Título',
  abstract: 'Resumen',
  keywords: 'Palabras clave',
  area: 'Área de conocimiento',
  language: 'Idioma',
  authors: 'Autores',
  draft_file: 'PDF del manuscrito',
};

/** Etiquetas de los campos que el `400` señala en `details`, en el orden del formulario. */
export function missingSubmissionFields(details: unknown): string[] {
  if (details === null || typeof details !== 'object') {
    return [];
  }
  return Object.keys(SUBMISSION_FIELD_LABELS)
    .filter((field) => field in (details as Record<string, unknown>))
    .map((field) => SUBMISSION_FIELD_LABELS[field]);
}

/**
 * Mensaje de un envío (formal o nueva versión) rechazado.
 *
 * * `400` de validación: el texto del servidor ya es específico ("Complete
 *   los campos obligatorios…", "debe existir al menos una corrección") y se
 *   completa con los campos que faltan.
 * * `PDF_INVALID`: el motivo exacto del servidor (cifrado, sin páginas…).
 * * El resto usa el mensaje accionable por código.
 */
export function submissionErrorMessage(error: ApiError): string {
  if (error.code === 'VALIDATION_ERROR' && error.message) {
    const missing = missingSubmissionFields(error.details);
    return missing.length > 0 ? `${error.message} Falta: ${missing.join(', ')}.` : error.message;
  }
  if (error.code === 'PDF_INVALID' && error.message) {
    return error.message;
  }
  return error.userMessage;
}
