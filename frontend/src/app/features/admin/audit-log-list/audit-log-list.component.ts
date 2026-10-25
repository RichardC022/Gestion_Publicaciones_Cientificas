import { Component } from '@angular/core';

/**
 * Andamio de ruta (TSK-25). La consulta global de auditoría se
 * implementa en la TSK-81.
 */
@Component({
  selector: 'app-audit-log-list',
  template: `
    <section aria-labelledby="audit-log-list-title">
      <h1 id="audit-log-list-title">Auditoría</h1>
      <p role="note">Sección en construcción; se implementa en la TSK-81.</p>
    </section>
  `,
})
export class AuditLogListComponent {}
