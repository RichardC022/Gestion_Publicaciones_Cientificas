import { Component } from '@angular/core';

/**
 * Andamio de ruta (TSK-25). El detalle de manuscrito del Autor se
 * implementa en la TSK-41.
 */
@Component({
  selector: 'app-manuscript-detail',
  template: `
    <section aria-labelledby="manuscript-detail-title">
      <h1 id="manuscript-detail-title">Detalle del manuscrito</h1>
      <p role="note">Sección en construcción; se implementa en la TSK-41.</p>
    </section>
  `,
})
export class ManuscriptDetailComponent {}
