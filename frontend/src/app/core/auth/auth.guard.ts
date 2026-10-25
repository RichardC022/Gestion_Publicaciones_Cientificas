import { inject } from '@angular/core';
import { Router } from '@angular/router';
import { CanActivateFn } from '@angular/router';
import { map } from 'rxjs';

import { AuthService } from './auth.service';
import { AuthStore } from './auth.store';

/**
 * Guard de sesión de las rutas internas (plan sección 3.3).
 *
 * Verifica la sesión; si no existe, intenta refrescar UNA sola vez
 * desde la cookie `HttpOnly` y, si el refresh falla, redirige a
 * `/login?returnUrl=...` para volver a donde estaba la persona.
 */
export const authGuard: CanActivateFn = (_route, state) => {
  const store = inject(AuthStore);
  const auth = inject(AuthService);
  const router = inject(Router);

  if (store.isAuthenticated()) {
    return true;
  }

  return auth.restoreSession().pipe(
    map((restored) =>
      restored
        ? true
        : router.createUrlTree(['/login'], {
            queryParams: { returnUrl: state.url },
          }),
    ),
  );
};
