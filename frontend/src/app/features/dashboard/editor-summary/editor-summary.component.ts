import { Component, input } from '@angular/core';

/**
 * Resumen del rol Editor dentro del panel unificado (plan sección 3.4).
 *
 * Muestra nuevos envíos y asignaciones vencidas; los datos llegan del
 * proveedor de la sección `editor` del backend, que se llena a partir
 * de la TSK-47.
 */
@Component({
  selector: 'app-editor-summary',
  template: `
    <article class="summary" aria-labelledby="editor-summary-title">
      <h3 id="editor-summary-title">Editor</h3>
      <p class="summary__hint">Nuevos envíos y asignaciones vencidas.</p>
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
export class EditorSummaryComponent {
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
