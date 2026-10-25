import { Component, input } from '@angular/core';

/**
 * Resumen del rol Administrador dentro del panel unificado
 * (plan sección 3.4). Muestra la vista de auditoría y la habilitación
 * de corrección de veredicto; los datos llegan del proveedor de la
 * sección `admin` del backend, que se llena a partir de la TSK-73.
 */
@Component({
  selector: 'app-admin-summary',
  template: `
    <article class="summary" aria-labelledby="admin-summary-title">
      <h3 id="admin-summary-title">Administrador</h3>
      <p class="summary__hint">Auditoría y habilitación de corrección.</p>
      <dl class="summary__data">
        @for (entry of entries(); track entry.key) {
          <div class="summary__row">
            <dt>{{ entry.key }}</dt>
            <dd>{{ entry.value }}</dd>
          </div>
        } @empty {
          <p class="summary__empty">Sin datos por ahora.</p>
        }
      </dl>
    </article>
  `,
})
export class AdminSummaryComponent {
  readonly data = input<Record<string, unknown> | null>(null);

  protected readonly entries = () =>
    Object.entries(this.data() ?? {}).map(([key, value]) => ({
      key,
      value: formatValue(value),
    }));
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return '—';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}
