import { Injectable, computed, signal } from '@angular/core';

import { Role } from '../models/role.model';
import { SessionUser } from '../models/session-user.model';

/** Estado de la sesión (plan sección 3.7). */
export type AuthStatus = 'anonymous' | 'authenticated' | 'refreshing';

interface AuthState {
  user: SessionUser | null;
  roles: Role[];
  /**
   * Access token en memoria: nunca se persiste en `localStorage`, en
   * cookies legibles ni en ningún otro almacenamiento del navegador.
   * El refresh token vive únicamente en la cookie `HttpOnly`.
   */
  accessToken: string | null;
  status: AuthStatus;
}

const ANONYMOUS_STATE: AuthState = {
  user: null,
  roles: [],
  accessToken: null,
  status: 'anonymous',
};

/**
 * Almacén de sesión basado en señales: única fuente de roles del
 * cliente (plan sección 3.8). Sin NgRx.
 */
@Injectable({ providedIn: 'root' })
export class AuthStore {
  private readonly state = signal<AuthState>(ANONYMOUS_STATE);

  /** Identidad de la sesión (null cuando es anónima). */
  readonly user = computed(() => this.state().user);

  /** Roles activos, releídos por el backend en cada solicitud. */
  readonly roles = computed(() => this.state().roles);

  /** Access token en memoria; los interceptores lo leen por solicitud. */
  readonly accessToken = computed(() => this.state().accessToken);

  readonly status = computed(() => this.state().status);

  /**
   * Sesión utilizable: authenticated o refreshing con token en mano.
   * Mientras el refresh único está en vuelo la interfaz no parpadea.
   */
  readonly isAuthenticated = computed(
    () => this.state().status !== 'anonymous' && this.state().accessToken !== null,
  );

  /** Indica si la sesión tiene al menos uno de los roles indicados. */
  hasAnyRole(required: readonly Role[]): boolean {
    return required.some((role) => this.roles().includes(role));
  }

  /** Sustituye la sesión completa tras login o refresh. */
  setSession(session: { user: SessionUser; roles: readonly Role[]; access: string }): void {
    this.state.set({
      user: session.user,
      roles: [...session.roles],
      accessToken: session.access,
      status: 'authenticated',
    });
  }

  /** Actualiza identidad y roles (lo consume `me()`). */
  updateUser(user: SessionUser, roles: readonly Role[]): void {
    this.state.update((state) => ({ ...state, user, roles: [...roles] }));
  }

  /** Sustituye solo los roles activos (pruebas de la directiva `appHasRole`). */
  setRoles(roles: readonly Role[]): void {
    this.state.update((state) => ({ ...state, roles: [...roles] }));
  }

  /** Marca la ola de refresh en curso conservando la sesión actual. */
  markRefreshing(): void {
    this.state.update((state) => ({ ...state, status: 'refreshing' }));
  }

  /** Limpia por completo la sesión en memoria (logout o refresh fallido). */
  clear(): void {
    this.state.set(ANONYMOUS_STATE);
  }

  /** Alias de `clear` conservado del andamiaje de Fase 0. */
  clearRoles(): void {
    this.clear();
  }
}
