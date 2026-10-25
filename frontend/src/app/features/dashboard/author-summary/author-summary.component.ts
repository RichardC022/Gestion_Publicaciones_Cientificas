import { Component, input } from '@angular/core';

/**
 * Resumen del rol Autor dentro del panel unificado (plan sección 3.4).
 *
 * Los datos propios (manuscritos y tareas pendientes) llegan del
 * proveedor de la sección `author` del backend, que se llena a partir
 * de la TSK-32. Esta vista solo pinta lo que recibe.
 */
@Component({
  selector: 'app-author-summary',
  template: `
    <article class="summary" aria-labelledby="author-summary-title">
      <h3 id="author-summary-title">Autor</h3>
      <p class="summary__hint">Sus manuscritos y tareas pendientes.</p>
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
export class AuthorSummaryComponent {
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
