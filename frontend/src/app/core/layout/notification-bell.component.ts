import { Component, computed, input, output } from '@angular/core';

/**
 * Campana de avisos con contador de no leídos (plan §3.5).
 * Botón nativo: navegable por teclado y con etiqueta accesible que
 * refleja el contador sin exponer datos de otros usuarios.
 */
@Component({
  selector: 'app-notification-bell',
  template: `
    <button type="button" class="bell" [attr.aria-label]="ariaLabel()" (click)="opened.emit()">
      <span class="bell__label" aria-hidden="true">Avisos</span>
      @if (unreadCount() > 0) {
        <span class="bell__badge" aria-hidden="true">
          {{ unreadCount() > 99 ? '99+' : unreadCount() }}
        </span>
      }
    </button>
  `,
  styles: `
    .bell {
      position: relative;
      display: inline-flex;
      align-items: center;
      gap: 0.375rem;
      padding: 0.375rem 0.75rem;
      border: 1px solid var(--gpc-border);
      border-radius: var(--gpc-radius);
      background: var(--gpc-surface-alt);
      color: var(--gpc-primary-700);
      font: inherit;
      font-weight: 600;
      cursor: pointer;
    }
    .bell:hover {
      background: var(--gpc-primary-50);
    }
    .bell__badge {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 1.25rem;
      padding: 0 0.25rem;
      border-radius: 999px;
      background: var(--gpc-danger-700);
      color: #ffffff;
      font-size: 0.75rem;
      line-height: 1.4;
    }
  `,
})
export class NotificationBellComponent {
  /** Cantidad de avisos propios no leídos. */
  readonly unreadCount = input(0);

  /** Se dispara al activar la campana. */
  readonly opened = output<void>();

  protected readonly ariaLabel = computed(() =>
    this.unreadCount() > 0
      ? `Avisos: ${this.unreadCount()} sin leer`
      : 'Avisos: sin notificaciones sin leer',
  );
}
