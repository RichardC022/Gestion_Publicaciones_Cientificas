import { Component } from '@angular/core';

/**
 * Andamio de ruta (TSK-25). El listado propio de manuscritos se
 * implementa en la TSK-41.
 */
@Component({
  selector: 'app-manuscript-list',
  template: `
    <section aria-labelledby="manuscript-list-title">
      <h1 id="manuscript-list-title">Mis manuscritos</h1>
      <p role="note">Sección en construcción; se implementa en la TSK-41.</p>
    </section>
  `,
})
export class ManuscriptListComponent {}
