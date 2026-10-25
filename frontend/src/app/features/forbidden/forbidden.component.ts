import { Component } from '@angular/core';
import { RouterLink } from '@angular/router';

/**
 * Página `403` visual (plan sección 3.3): el `rolesGuard` trae aquí
 * cuando la persona autenticada no tiene el rol del módulo. Usa el
 * rojo de la paleta para acciones restringidas y ofrece volver al
 * panel unificado, que siempre está habilitado para cualquier rol.
 */
@Component({
  selector: 'app-forbidden',
  imports: [RouterLink],
  template: `
    <section class="forbidden" aria-labelledby="forbidden-title">
      <p class="forbidden__code" aria-hidden="true">403</p>
      <h1 id="forbidden-title">Acceso denegado</h1>
      <p>
        Su rol no habilita esta sección. Si cree que debería tener
        acceso, consulte a la administración institucional.
      </p>
      <a routerLink="/app/dashboard" class="forbidden__back">Volver al panel</a>
    </section>
  `,
  styles: `
    .forbidden {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 0.75rem;
      max-width: 32rem;
      margin: 4rem auto;
      padding: 2rem;
      text-align: center;
    }
    .forbidden__code {
      margin: 0;
      font-size: 4rem;
      font-weight: 700;
      color: var(--app-danger, #b3261e);
    }
    .forbidden__back {
      color: var(--app-primary, #1d4ed8);
      font-weight: 600;
    }
  `,
})
export class ForbiddenComponent {}
