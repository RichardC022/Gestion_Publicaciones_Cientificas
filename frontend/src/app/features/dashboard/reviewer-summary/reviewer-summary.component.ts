import { Component, input } from '@angular/core';

/**
 * Resumen del rol Revisor dentro del panel unificado (plan sección 3.4).
 *
 * Muestra asignaciones pendientes, plazos y vencimientos; los datos
 * llegan del proveedor de la sección `reviewer` del backend, que se
 * llena a partir de la TSK-60. Nunca incluye identidad de Autores.
 */
@Component({
  selector: 'app-reviewer-summary',
  template: `
    <article class="summary" aria-labelledby="reviewer-summary-title">
      <h3 id="reviewer-summary-title">Revisor</h3>
      <p class="summary__hint">Sus asignaciones, plazos y vencimientos.</p>
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
export class ReviewerSummaryComponent {
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
