/** Longitud máxima de una palabra clave (la API la limita a 100). */
export const KEYWORD_MAX_LENGTH = 100;

/**
 * Palabras clave desde el texto del formulario: se separan por coma,
 * punto y coma o salto de línea, se recortan, se descartan las vacías
 * y se eliminan repetidas sin distinguir mayúsculas (se conserva la
 * primera escritura).
 */
export function parseKeywords(text: string): string[] {
  const seen = new Set<string>();
  const keywords: string[] = [];
  for (const raw of text.split(/[,;\n]/)) {
    const keyword = raw.trim();
    const key = keyword.toLowerCase();
    if (keyword && !seen.has(key)) {
      seen.add(key);
      keywords.push(keyword);
    }
  }
  return keywords;
}
