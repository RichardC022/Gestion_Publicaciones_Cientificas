import { Component } from '@angular/core';

/**
 * Andamio de ruta (TSK-25). El detalle editorial de un envío se
 * implementa en la TSK-54.
 */
@Component({
  selector: 'app-submission-detail',
  template: `
    <section aria-labelledby="submission-detail-title">
      <h1 id="submission-detail-title">Detalle del envío</h1>
      <p role="note">Sección en construcción; se implementa en la TSK-54.</p>
    </section>
  `,
})
export class SubmissionDetailComponent {}
