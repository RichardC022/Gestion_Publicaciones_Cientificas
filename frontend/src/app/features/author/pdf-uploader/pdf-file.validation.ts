import { FileSizePipe } from '../../../shared/pipes/file-size.pipe';

/**
 * Validación de un PDF en el navegador antes de enviarlo (plan 3.5).
 *
 * Es solo ayuda de UX: evita subir 50 MB para que luego el servidor
 * diga que no era un PDF. La barrera de seguridad es el backend, que
 * vuelve a validar extensión, tipo declarado, tamaño y CONTENIDO real
 * (firma, estructura, cifrado y contenido activo) y rechaza lo que el
 * cliente deje pasar.
 */

/** Límite por archivo (plan 4.2); Nginx admite 60 MB para el sobre multipart. */
export const MAX_PDF_BYTES = 50 * 1024 * 1024;

/**
 * Tipos MIME declarados que pueden transportar un PDF. Algunos
 * navegadores y sistemas envían `application/octet-stream` o ningún
 * tipo; son los mismos que acepta el backend.
 */
export const ACCEPTED_PDF_TYPES: readonly string[] = [
  'application/pdf',
  'application/x-pdf',
  'application/octet-stream',
  '',
];

export type PdfFileProblem = 'extension' | 'type' | 'empty' | 'too-large';

export interface PdfFileCheck {
  problem: PdfFileProblem;
  message: string;
}

const fileSize = new FileSizePipe();

/** Devuelve el primer problema del archivo, o `null` si puede enviarse. */
export function validatePdfFile(file: Pick<File, 'name' | 'type' | 'size'>): PdfFileCheck | null {
  if (!file.name.toLowerCase().endsWith('.pdf')) {
    return { problem: 'extension', message: 'Solo se admiten archivos PDF (extensión .pdf).' };
  }
  if (!ACCEPTED_PDF_TYPES.includes(file.type.toLowerCase())) {
    return { problem: 'type', message: 'El tipo de archivo no es PDF.' };
  }
  if (file.size === 0) {
    return { problem: 'empty', message: 'El archivo está vacío.' };
  }
  if (file.size > MAX_PDF_BYTES) {
    return {
      problem: 'too-large',
      message: `El archivo pesa ${fileSize.transform(file.size)} y supera el límite de 50 MB.`,
    };
  }
  return null;
}
