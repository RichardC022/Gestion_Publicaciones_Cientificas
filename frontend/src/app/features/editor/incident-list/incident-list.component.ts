import { Component } from '@angular/core';

/**
 * Andamio de ruta (TSK-25). La bandeja de incidentes confidenciales
 * del Editor se implementa en la TSK-70.
 */
@Component({
  selector: 'app-incident-list',
  template: `
    <section aria-labelledby="incident-list-title">
      <h1 id="incident-list-title">Incidentes confidenciales</h1>
      <p role="note">Sección en construcción; se implementa en la TSK-70.</p>
    </section>
  `,
})
export class IncidentListComponent {}
