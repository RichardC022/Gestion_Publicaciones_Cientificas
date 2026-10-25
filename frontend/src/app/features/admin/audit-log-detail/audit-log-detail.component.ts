import { Component } from '@angular/core';

/**
 * Andamio de ruta (TSK-25). El detalle de un evento de auditoría se
 * implementa en la TSK-81.
 */
@Component({
  selector: 'app-audit-log-detail',
  template: `
    <section aria-labelledby="audit-log-detail-title">
      <h1 id="audit-log-detail-title">Detalle del evento</h1>
      <p role="note">Sección en construcción; se implementa en la TSK-81.</p>
    </section>
  `,
})
export class AuditLogDetailComponent {}
