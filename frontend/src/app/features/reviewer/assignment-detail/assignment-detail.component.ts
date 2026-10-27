import { Component } from '@angular/core';

/**
 * Andamio de ruta (TSK-25). El detalle anonimizado de la asignación se
 * implementa en la TSK-66; sin autores, filiaciones ni nombre original.
 */
@Component({
  selector: 'app-assignment-detail',
  template: `
    <section aria-labelledby="assignment-detail-title">
      <h1 id="assignment-detail-title">Detalle de la asignación</h1>
      <p role="note">Sección en construcción; se implementa en la TSK-66.</p>
    </section>
  `,
})
export class AssignmentDetailComponent {}
