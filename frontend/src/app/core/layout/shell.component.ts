import { Component, input, output } from '@angular/core';
import { RouterOutlet } from '@angular/router';

import { Role } from '../models/role.model';
import { HeaderComponent } from './header.component';
import { SideNavComponent } from './side-nav.component';

/**
 * Layout interno del área autenticada (plan §3.5): encabezado,
 * navegación por roles, campana de avisos y contenido enrutado.
 * Incluye enlace de salto al contenido y es responsive.
 */
@Component({
  selector: 'app-shell',
  imports: [RouterOutlet, HeaderComponent, SideNavComponent],
  template: `
    <a class="skip-link" href="#main-content">Saltar al contenido principal</a>
    <div class="shell">
      <app-header
        [userName]="userName()"
        [roles]="roles()"
        [unreadCount]="unreadCount()"
        (logout)="logout.emit()"
        (bellOpened)="notificationsOpened.emit()"
      />
      <div class="shell__body">
        <app-side-nav [roles]="roles()" />
        <main id="main-content" class="shell__content" tabindex="-1">
          <router-outlet />
        </main>
      </div>
    </div>
  `,
  styles: `
    .shell {
      display: flex;
      flex-direction: column;
      min-height: 100dvh;
    }
    .shell__body {
      display: grid;
      grid-template-columns: 15rem minmax(0, 1fr);
      gap: 1.25rem;
      width: min(90rem, 100%);
      margin-inline: auto;
      padding: 1.25rem;
      flex: 1;
    }
    .shell__content {
      min-width: 0;
    }
    @media (max-width: 60rem) {
      .shell__body {
        grid-template-columns: minmax(0, 1fr);
      }
    }
  `,
})
export class ShellComponent {
  /** Nombre visible de la persona autenticada. */
  readonly userName = input<string | null>(null);

  /** Roles activos de la sesión. */
  readonly roles = input<Role[]>([]);

  /** Cantidad de avisos propios no leídos. */
  readonly unreadCount = input(0);

  /** Se dispara al pulsar Cerrar sesión (se conecta en TSK-26). */
  readonly logout = output<void>();

  /** Se dispara al activar la campana (se conecta en TSK-26). */
  readonly notificationsOpened = output<void>();
}
