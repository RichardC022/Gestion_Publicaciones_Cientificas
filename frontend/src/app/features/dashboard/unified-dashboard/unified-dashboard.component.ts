import { Component } from '@angular/core';

/**
 * Andamio de ruta (TSK-25). El panel unificado con las secciones de
 * todos los roles activos se implementa en la TSK-27.
 */
@Component({
  selector: 'app-unified-dashboard',
  template: `
    <section aria-labelledby="dashboard-title">
      <h1 id="dashboard-title">Panel unificado</h1>
      <p role="note">Sección en construcción; se implementa en la TSK-27.</p>
    </section>
  `,
})
export class UnifiedDashboardComponent {}
