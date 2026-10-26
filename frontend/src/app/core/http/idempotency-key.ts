/**
 * Clave de idempotencia para los `POST` que el servidor no debe repetir
 * (envío formal y nueva versión; plan sección 2.11).
 *
 * Una clave identifica UNA intención del usuario: se genera al iniciar la
 * operación y se reutiliza en los reintentos de esa misma operación (tras
 * un corte de red, por ejemplo), de modo que el servidor responda con lo
 * ya registrado en lugar de duplicarlo. Una operación nueva usa una clave
 * nueva. El formato (letras, números y `. _ : -`, hasta 100 caracteres) es
 * el que acepta el backend.
 */
export function newIdempotencyKey(): string {
  const webCrypto = globalThis.crypto;
  if (typeof webCrypto?.randomUUID === 'function') {
    return webCrypto.randomUUID();
  }
  const random = Array.from({ length: 4 }, () => Math.random().toString(36).slice(2, 10)).join('');
  return `k-${Date.now().toString(36)}-${random}`;
}
