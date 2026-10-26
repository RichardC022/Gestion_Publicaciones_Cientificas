/**
 * Entrega un `Blob` al usuario como descarga del navegador.
 *
 * Crea una URL de objeto, la activa desde un enlace temporal y la
 * revoca de inmediato: el PDF vive solo en memoria mientras se guarda
 * y no se persiste en `localStorage` ni en ningún otro almacenamiento.
 * El nombre es solo una sugerencia de archivo, nunca una ruta.
 */
export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  try {
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    link.rel = 'noopener';
    link.style.display = 'none';
    document.body.appendChild(link);
    link.click();
    link.remove();
  } finally {
    URL.revokeObjectURL(url);
  }
}
