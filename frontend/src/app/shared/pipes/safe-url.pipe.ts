import { Pipe, PipeTransform, inject } from '@angular/core';
import { DomSanitizer, SafeResourceUrl } from '@angular/platform-browser';

/**
 * Marca como confiable una URL de recurso para incrustarla en un
 * `iframe` (plan §3.9). Solo debe usarse con URLs creadas por la propia
 * aplicación (objetos `blob:` de `PdfViewerComponent`) o con rutas
 * públicas del backend; nunca con URLs provenientes del usuario, para
 * no eludir la sanitización de contenido arbitrario.
 */
@Pipe({ name: 'safeUrl' })
export class SafeUrlPipe implements PipeTransform {
  private readonly sanitizer = inject(DomSanitizer);

  transform(value: string | null | undefined): SafeResourceUrl | null {
    if (!value) {
      return null;
    }
    return this.sanitizer.bypassSecurityTrustResourceUrl(value);
  }
}
