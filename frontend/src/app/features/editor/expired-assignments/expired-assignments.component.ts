import { Component } from '@angular/core';

/**
 * Andamio de ruta (TSK-25). La vista de asignaciones vencidas se
 * implementa en la TSK-57.
 */
@Component({
  selector: 'app-expired-assignments',
  template: `
    <section aria-labelledby="expired-assignments-title">
      <h1 id="expired-assignments-title">Plazos vencidos</h1>
      <p role="note">Sección en construcción; se implementa en la TSK-57.</p>
    </section>
  `,
})
export class ExpiredAssignmentsComponent {}
