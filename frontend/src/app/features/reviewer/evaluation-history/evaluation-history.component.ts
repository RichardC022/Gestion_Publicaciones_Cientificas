import { Component } from '@angular/core';

/**
 * Andamio de ruta (TSK-25). El historial propio de evaluaciones se
 * implementa en la TSK-69; es de solo lectura y sin identidades de
 * Autores.
 */
@Component({
  selector: 'app-evaluation-history',
  template: `
    <section aria-labelledby="evaluation-history-title">
      <h1 id="evaluation-history-title">Historial de evaluaciones</h1>
      <p role="note">Sección en construcción; se implementa en la TSK-69.</p>
    </section>
  `,
})
export class EvaluationHistoryComponent {}
