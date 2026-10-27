import { Component } from '@angular/core';

/**
 * Andamio de ruta (TSK-25). La bandeja de envíos del Editor se
 * implementa en la TSK-54.
 */
@Component({
  selector: 'app-submission-inbox',
  template: `
    <section aria-labelledby="submission-inbox-title">
      <h1 id="submission-inbox-title">Nuevos envíos</h1>
      <p role="note">Sección en construcción; se implementa en la TSK-54.</p>
    </section>
  `,
})
export class SubmissionInboxComponent {}
