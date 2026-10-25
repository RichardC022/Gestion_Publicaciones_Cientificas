import { Component, input } from '@angular/core';

/**
 * Indicador de carga con texto accesible para lectores de pantalla
 * (plan §3.10). Respeta `prefers-reduced-motion`.
 */
@Component({
  selector: 'app-loading-spinner',
  template: `
    <div class="spinner" role="status" aria-live="polite">
      <span class="spinner__disc" aria-hidden="true"></span>
      <span class="visually-hidden">{{ label() }}</span>
    </div>
  `,
  styles: `
    .spinner {
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 1.5rem 0;
    }
    .spinner__disc {
      width: 2rem;
      height: 2rem;
      border: 3px solid var(--gpc-primary-100);
      border-top-color: var(--gpc-primary-700);
      border-radius: 50%;
      animation: spinner-rotate 900ms linear infinite;
    }
    @keyframes spinner-rotate {
      to {
        transform: rotate(360deg);
      }
    }
    @media (prefers-reduced-motion: reduce) {
      .spinner__disc {
        animation-duration: 3s;
      }
    }
  `,
})
export class LoadingSpinnerComponent {
  /** Texto que se anuncia a los lectores de pantalla. */
  readonly label = input('Cargando…');
}
