import { Component } from '@angular/core';
import { RouterLink } from '@angular/router';

/**
 * Pantalla pública de acceso institucional.
 *
 * El formulario real (credenciales institucionales y mensaje de error
 * genérico) se implementa en la Fase 1 (TSK-26). No existe ninguna
 * pantalla de selección de rol.
 */
@Component({
  selector: 'app-login',
  imports: [RouterLink],
  template: `
    <main>
      <h1>Iniciar sesión</h1>
      <p>Acceso con credenciales institucionales. Próximamente.</p>
      <a routerLink="/catalog">Ir al catálogo público</a>
    </main>
  `,
})
export class LoginComponent {}
