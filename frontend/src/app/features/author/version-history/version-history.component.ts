import { Component } from '@angular/core';

/**
 * Andamio de ruta (TSK-25). La línea de tiempo de versiones se
 * implementa en la TSK-43.
 */
@Component({
  selector: 'app-version-history',
  template: `
    <section aria-labelledby="version-history-title">
      <h1 id="version-history-title">Historial de versiones</h1>
      <p role="note">Sección en construcción; se implementa en la TSK-43.</p>
    </section>
  `,
})
export class VersionHistoryComponent {}
