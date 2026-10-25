import { Component, input, output } from '@angular/core';

/**
 * Estado vacío con mensaje y acción sugerida (plan §3.10).
 * Se anuncia como `status` para lectores de pantalla.
 */
@Component({
  selector: 'app-empty-state',
  template: `
    <div class="empty-state" role="status">
      <p class="empty-state__message">{{ message() }}</p>
      @if (actionLabel()) {
        <button type="button" class="btn btn--primary" (click)="action.emit()">
          {{ actionLabel() }}
        </button>
      }
    </div>
  `,
  styles: `
    .empty-state {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 0.75rem;
      padding: 2rem 1rem;
      text-align: center;
      background: var(--gpc-surface-alt);
      border: 1px dashed var(--gpc-border);
      border-radius: var(--gpc-radius);
    }
    .empty-state__message {
      margin: 0;
      color: var(--gpc-text-muted);
    }
  `,
})
export class EmptyStateComponent {
  /** Mensaje descriptivo del estado vacío. */
  readonly message = input.required<string>();

  /** Etiqueta de la acción sugerida; si es nula no se muestra botón. */
  readonly actionLabel = input<string | null>(null);

  /** Se dispara al pulsar la acción sugerida. */
  readonly action = output<void>();
}
