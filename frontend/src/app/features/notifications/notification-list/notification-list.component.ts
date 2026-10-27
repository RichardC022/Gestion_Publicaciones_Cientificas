import { Component } from '@angular/core';

/**
 * Andamio de ruta (TSK-25). La lista de avisos propios con marcado de
 * leídos se implementa en la TSK-83.
 */
@Component({
  selector: 'app-notification-list',
  template: `
    <section aria-labelledby="notification-list-title">
      <h1 id="notification-list-title">Avisos</h1>
      <p role="note">Sección en construcción; se implementa en la TSK-83.</p>
    </section>
  `,
})
export class NotificationListComponent {}
