import { inject } from '@angular/core';
import { Router } from '@angular/router';
import { CanActivateFn } from '@angular/router';

import { AuthStore } from './auth.store';

/**
 * Guard de las rutas solo-públicas como `/login` (plan sección 3.3):
 * si ya hay sesión, redirige al panel unificado. El panel muestra las
 * secciones de todos los roles activos a la vez; no hay paso de
 * selección de rol.
 */
export const publicOnlyGuard: CanActivateFn = () => {
  const store = inject(AuthStore);
  const router = inject(Router);

  if (store.isAuthenticated()) {
    return router.createUrlTree(['/app/dashboard']);
  }
  return true;
};
