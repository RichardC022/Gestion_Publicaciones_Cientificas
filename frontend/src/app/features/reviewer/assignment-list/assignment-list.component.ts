import { Component } from '@angular/core';

/**
 * Andamio de ruta (TSK-25). La bandeja de asignaciones del Revisor se
 * implementa en la TSK-66; nunca renderiza autorías (doble ciego).
 */
@Component({
  selector: 'app-assignment-list',
  template: `
    <section aria-labelledby="assignment-list-title">
      <h1 id="assignment-list-title">Mis asignaciones</h1>
      <p role="note">Sección en construcción; se implementa en la TSK-66.</p>
    </section>
  `,
})
export class AssignmentListComponent {}
