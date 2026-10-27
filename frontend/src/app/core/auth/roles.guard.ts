import { inject } from '@angular/core';
import { Router } from '@angular/router';
import { CanActivateFn } from '@angular/router';

import { Role } from '../models/role.model';
import { AuthStore } from './auth.store';

/**
 * Guard por rol de las rutas de módulo (plan sección 3.3).
 *
 * Recibe los roles exigidos en ``data.roles`` y exige al menos un rol
 * activo. Un rol retirado durante la sesión bloquea la siguiente
 * acción aunque el access token siga vigente: los roles se leen del
 * AuthStore, que el backend revalida contra PostgreSQL en cada
 * solicitud. Sin el rol se muestra el `403` visual (`/forbidden`);
 * sin sesión se vuelve a `/login` con `returnUrl`.
 *
 * No existe ni debe existir un guard ni una ruta de selección de rol:
 * una persona con roles simultáneos accede a todas sus secciones sin
 * conmutar nada.
 */
export const rolesGuard: CanActivateFn = (route, state) => {
  const required = (route.data?.['roles'] as readonly Role[] | undefined) ?? [];
  const store = inject(AuthStore);
  const router = inject(Router);

  if (!store.isAuthenticated()) {
    return router.createUrlTree(['/login'], {
      queryParams: { returnUrl: state.url },
    });
  }

  // Sin roles exigidos solo hace falta la sesión.
  if (required.length === 0 || store.hasAnyRole(required)) {
    return true;
  }

  return router.createUrlTree(['/forbidden']);
};
