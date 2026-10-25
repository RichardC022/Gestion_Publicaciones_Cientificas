import { Component, effect, input, signal } from '@angular/core';

import { SafeUrlPipe } from '../pipes/safe-url.pipe';

/**
 * Visor embebido de PDF (plan §3.9).
 *
 * Recibe el documento como `Blob` (PDF interno con autorización del
 * backend o PDF sanitizado del Revisor) y lo renderiza en un `iframe`
 * con `sandbox`; no usa `innerHTML`. Las URLs de objeto se revocan al
 * cambiar de documento o al destruir el componente.
 */
@Component({
  selector: 'app-pdf-viewer',
  imports: [SafeUrlPipe],
  template: `
    @if (objectUrl(); as url) {
      <div class="pdf-viewer">
        <div class="pdf-viewer__actions">
          <button type="button" class="btn btn--primary" (click)="download(url)">
            Descargar
          </button>
          <button type="button" class="btn btn--ghost" (click)="openInNewTab(url)">
            Abrir en pestaña nueva
          </button>
        </div>
        <iframe
          class="pdf-viewer__frame"
          [title]="frameTitle()"
          [src]="url | safeUrl"
          sandbox="allow-same-origin"
          loading="lazy"
        ></iframe>
      </div>
    } @else {
      <p class="pdf-viewer__empty">{{ emptyLabel() }}</p>
    }
  `,
  styles: `
    .pdf-viewer {
      display: flex;
      flex-direction: column;
      gap: 0.75rem;
    }
    .pdf-viewer__actions {
      display: flex;
      gap: 0.5rem;
    }
    .pdf-viewer__frame {
      width: 100%;
      min-height: 32rem;
      border: 1px solid var(--gpc-border);
      border-radius: var(--gpc-radius);
      background: var(--gpc-surface-alt);
    }
    .pdf-viewer__empty {
      margin: 0;
      padding: 1rem;
      color: var(--gpc-text-muted);
      text-align: center;
    }
  `,
})
export class PdfViewerComponent {
  /** Documento interno; nunca se guarda en `localStorage`. */
  readonly blob = input<Blob | null>(null);

  /** Nombre sugerido para la descarga. */
  readonly filename = input('documento.pdf');

  /** Título accesible del `iframe`. */
  readonly frameTitle = input('Visor de documento PDF');

  /** Mensaje cuando no hay documento disponible. */
  readonly emptyLabel = input('No hay documento disponible.');

  protected readonly objectUrl = signal<string | null>(null);

  constructor() {
    effect((onCleanup) => {
      const blob = this.blob();
      const url = blob ? URL.createObjectURL(blob) : null;
      this.objectUrl.set(url);
      onCleanup(() => {
        if (url) {
          URL.revokeObjectURL(url);
        }
      });
    });
  }

  protected download(url: string): void {
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = this.filename();
    anchor.rel = 'noopener';
    anchor.click();
  }

  protected openInNewTab(url: string): void {
    window.open(url, '_blank', 'noopener');
  }
}
