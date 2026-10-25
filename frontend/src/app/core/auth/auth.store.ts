import { Injectable, signal } from '@angular/core';

import { Role } from '../models/role.model';

/**
 * Almacén de sesión basado en señales.
 *
 * En la Fase 0 solo expone los roles activos, que alimentan la directiva
 * `appHasRole` y la navegación por roles. El acceso, el refresco y el
 * cierre de sesión se completan en la Fase 1 (TSK-24); el access token
 * vive en memoria y nunca en `localStorage`.
 */
@Injectable({ providedIn: 'root' })
export class AuthStore {
  private readonly activeRoles = signal<Role[]>([]);

  /** Roles activos de la sesión. */
  readonly roles = this.activeRoles.asReadonly();

  /** Indica si la sesión tiene al menos uno de los roles indicados. */
  hasAnyRole(required: readonly Role[]): boolean {
    return required.some((role) => this.activeRoles().includes(role));
  }

  /** Sustituye los roles activos (lo consume AuthService en TSK-24). */
  setRoles(roles: readonly Role[]): void {
    this.activeRoles.set([...roles]);
  }

  /** Limpia la sesión (lo consume AuthService en TSK-24). */
  clearRoles(): void {
    this.activeRoles.set([]);
  }
}
