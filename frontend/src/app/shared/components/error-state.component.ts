import { Component, input, output } from '@angular/core';

/**
 * Estado de error con reintento (plan §3.10). Se anuncia como `alert`
 * y nunca revela si un recurso ajeno existe: el mensaje llega ya
 * normalizado desde el backend.
 */
@Component({
  selector: 'app-error-state',
  template: `
    <div class="error-state" role="alert">
      <p class="error-state__message">{{ message() }}</p>
      @if (retryLabel()) {
        <button type="button" class="btn btn--primary" (click)="retry.emit()">
          {{ retryLabel() }}
        </button>
      }
    </div>
  `,
  styles: `
    .error-state {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 0.75rem;
      padding: 1.5rem 1rem;
      text-align: center;
      background: var(--gpc-danger-100);
      border: 1px solid var(--gpc-danger-700);
      border-radius: var(--gpc-radius);
    }
    .error-state__message {
      margin: 0;
      color: #9b1c1c;
      font-weight: 600;
    }
  `,
})
export class ErrorStateComponent {
  /** Mensaje de error accionable, sin detalles internos. */
  readonly message = input.required<string>();

  /** Etiqueta del botón de reintento; si es nula no se muestra botón. */
  readonly retryLabel = input<string | null>('Reintentar');

  /** Se dispara al pulsar el botón de reintento. */
  readonly retry = output<void>();
}
