import { Component, computed, input } from '@angular/core';
import { RouterLink, RouterLinkActive } from '@angular/router';

import { Role, ROLE_LABELS } from '../models/role.model';

interface NavGroup {
  label: string;
  items: { label: string; path: string }[];
}

/**
 * Navegación lateral con los módulos de todos los roles activos
 * (plan §3.4): nunca exige elegir rol ni muestra apartados de roles
 * inexistentes. En pantallas pequeñas se vuelve horizontal.
 */
@Component({
  selector: 'app-side-nav',
  imports: [RouterLink, RouterLinkActive],
  template: `
    <nav class="side-nav" aria-label="Navegación principal">
      <ul class="side-nav__group">
        <li>
          <a
            class="side-nav__link"
            routerLink="/app/dashboard"
            routerLinkActive="side-nav__link--active"
          >
            Panel
          </a>
        </li>
        <li>
          <a
            class="side-nav__link"
            routerLink="/app/notifications"
            routerLinkActive="side-nav__link--active"
          >
            Notificaciones
          </a>
        </li>
      </ul>
      @for (group of groups(); track group.label) {
        <h2 class="side-nav__heading">{{ group.label }}</h2>
        <ul class="side-nav__group">
          @for (item of group.items; track item.path) {
            <li>
              <a
                class="side-nav__link"
                [routerLink]="item.path"
                routerLinkActive="side-nav__link--active"
              >
                {{ item.label }}
              </a>
            </li>
          }
        </ul>
      }
    </nav>
  `,
  styles: `
    .side-nav {
      display: flex;
      flex-direction: column;
      gap: 0.75rem;
    }
    .side-nav__heading {
      margin: 0;
      padding: 0 0.625rem;
      color: var(--gpc-text-muted);
      font-size: 0.75rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }
    .side-nav__group {
      display: flex;
      flex-direction: column;
      gap: 0.125rem;
      margin: 0;
      padding: 0;
      list-style: none;
    }
    .side-nav__link {
      display: block;
      padding: 0.5rem 0.625rem;
      border-radius: var(--gpc-radius);
      color: var(--gpc-primary-700);
      text-decoration: none;
      font-weight: 500;
    }
    .side-nav__link:hover {
      background: var(--gpc-primary-50);
    }
    .side-nav__link--active {
      background: var(--gpc-primary-100);
      color: var(--gpc-primary-900);
      font-weight: 700;
    }
    @media (max-width: 60rem) {
      .side-nav {
        flex-direction: row;
        flex-wrap: wrap;
        align-items: baseline;
        gap: 0.5rem 1rem;
      }
      .side-nav__group {
        flex-direction: row;
        flex-wrap: wrap;
        gap: 0.25rem;
      }
    }
  `,
})
export class SideNavComponent {
  /** Roles activos de la sesión. */
  readonly roles = input<Role[]>([]);

  /** Módulos por rol; solo aparecen los roles activos. */
  protected readonly groups = computed<NavGroup[]>(() => {
    const roles = this.roles();
    const groups: NavGroup[] = [];
    if (roles.includes('AUTHOR')) {
      groups.push({
        label: ROLE_LABELS.AUTHOR,
        items: [{ label: 'Mis manuscritos', path: '/app/author/manuscripts' }],
      });
    }
    if (roles.includes('REVIEWER')) {
      groups.push({
        label: ROLE_LABELS.REVIEWER,
        items: [
          { label: 'Mis asignaciones', path: '/app/reviewer/assignments' },
          { label: 'Historial de evaluaciones', path: '/app/reviewer/history' },
        ],
      });
    }
    if (roles.includes('EDITOR')) {
      groups.push({
        label: ROLE_LABELS.EDITOR,
        items: [
          { label: 'Nuevos envíos', path: '/app/editor/submissions' },
          { label: 'Asignaciones vencidas', path: '/app/editor/assignments/expired' },
          { label: 'Incidentes', path: '/app/editor/incidents' },
        ],
      });
    }
    if (roles.includes('ADMIN')) {
      groups.push({
        label: ROLE_LABELS.ADMIN,
        items: [{ label: 'Auditoría', path: '/app/admin/audit' }],
      });
    }
    return groups;
  });
}
