import { signal } from '@angular/core';

import { NotificationService } from '../services/notification.service';

/**
 * Sustituto de `NotificationService` para las pruebas que montan el
 * `ShellComponent` real (rutas completas): el shell lee el contador de la
 * campana al crearse y esas pruebas no esperan esa petición. El
 * comportamiento real se prueba en `notification.service.spec.ts` y
 * `shell.component.spec.ts`.
 */
export const NOTIFICATION_SERVICE_STUB = {
  provide: NotificationService,
  useValue: { unreadCount: signal(0).asReadonly(), refresh: () => undefined },
};
