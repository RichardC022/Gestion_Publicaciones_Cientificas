import { Component, input, output } from '@angular/core';
import { RouterLink } from '@angular/router';

import { Role, ROLE_LABELS } from '../models/role.model';
import { NotificationBellComponent } from './notification-bell.component';

/**
 * Encabezado del área interna: título institucional, roles activos
 * como insignias informativas (nunca un selector o conmutador de
 * rol), campana de avisos, nombre y cierre de sesión.
 */
@Component({
  selector: 'app-header',
  imports: [RouterLink, NotificationBellComponent],
  template: `
    <header class="app-header">
      <a routerLink="/app/dashboard" class="app-header__title">
        Gestión de Publicaciones Científicas
      </a>
      @if (roles().length > 0) {
        <ul class="app-header__roles" aria-label="Roles activos">
          @for (role of roles(); track role) {
            <li>
              <span class="badge badge--info">{{ roleLabels[role] }}</span>
            </li>
          }
        </ul>
      }
      <div class="app-header__session">
        <app-notification-bell
          [unreadCount]="unreadCount()"
          (opened)="bellOpened.emit()"
        />
        @if (userName(); as name) {
          <span class="app-header__user">{{ name }}</span>
        }
        <button type="button" class="btn btn--ghost" (click)="logout.emit()">
          Cerrar sesión
        </button>
      </div>
    </header>
  `,
  styles: `
    .app-header {
      display: flex;
      align-items: center;
      gap: 1rem;
      padding: 0.75rem 1.25rem;
      background: var(--gpc-primary-900);
      color: #ffffff;
      flex-wrap: wrap;
    }
    .app-header__title {
      color: #ffffff;
      font-weight: 700;
      text-decoration: none;
    }
    .app-header__roles {
      display: flex;
      gap: 0.375rem;
      margin: 0;
      padding: 0;
      list-style: none;
      flex-wrap: wrap;
    }
    .app-header__session {
      display: flex;
      align-items: center;
      gap: 0.75rem;
      margin-inline-start: auto;
      flex-wrap: wrap;
    }
    .app-header__user {
      font-weight: 600;
      max-width: 14rem;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
  `,
})
export class HeaderComponent {
  /** Nombre visible de la persona autenticada. */
  readonly userName = input<string | null>(null);

  /** Roles activos, mostrados como insignias informativas. */
  readonly roles = input<Role[]>([]);

  /** Cantidad de avisos propios no leídos. */
  readonly unreadCount = input(0);

  /** Se dispara al pulsar Cerrar sesión (se conecta en TSK-26). */
  readonly logout = output<void>();

  /** Se dispara al activar la campana (se conecta en TSK-26). */
  readonly bellOpened = output<void>();

  protected readonly roleLabels = ROLE_LABELS;
}
