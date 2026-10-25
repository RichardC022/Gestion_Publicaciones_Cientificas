import { Component, computed, inject } from '@angular/core';
import { Router, RouterOutlet } from '@angular/router';

import { AuthService } from '../auth/auth.service';
import { AuthStore } from '../auth/auth.store';
import { ApiFeedbackStore } from '../http/api-feedback.store';
import { HeaderComponent } from './header.component';
import { SideNavComponent } from './side-nav.component';

/**
 * Layout interno del área autenticada (plan §3.5): encabezado,
 * navegación por roles, campana de avisos y contenido enrutado.
 *
 * TSK-26: se conecta al `AuthStore` (nombre, roles activos) y al
 * `AuthService` (cierre de sesión) y renderiza los mensajes
 * accionables de la API publicados por el interceptor de errores
 * (`ApiFeedbackStore`). El contador de avisos se alimenta del
 * backend de notificaciones en la TSK-75/83; hasta entonces vale 0.
 */
@Component({
  selector: 'app-shell',
  imports: [RouterOutlet, HeaderComponent, SideNavComponent],
  template: `
    <a class="skip-link" href="#main-content">Saltar al contenido principal</a>

    <!-- Mensajes accionables de la API (409/413/429/503…). -->
    @if (feedback.feedback(); as current) {
      <div
        class="app-feedback"
        role="alert"
        [class.app-feedback--warning]="current.kind === 'warning'"
      >
        <p class="app-feedback__message">{{ current.message }}</p>
        <button
          type="button"
          class="app-feedback__dismiss"
          (click)="feedback.dismiss()"
          aria-label="Cerrar el aviso"
        >
          ×
        </button>
      </div>
    }

    <div class="shell">
      <app-header
        [userName]="userName()"
        [roles]="roles()"
        [unreadCount]="0"
        (logout)="logout()"
        (bellOpened)="openNotifications()"
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
    .app-feedback {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 1rem;
      padding: 0.75rem 1.25rem;
      background: var(--gpc-danger-50, #fef2f2);
      border-bottom: 1px solid var(--gpc-danger-700);
      color: var(--gpc-danger-900, #7f1d1d);
    }
    .app-feedback--warning {
      background: var(--gpc-warning-50, #fefce8);
      border-bottom-color: var(--gpc-warning-700, #a16207);
      color: var(--gpc-warning-900, #713f12);
    }
    .app-feedback__message {
      margin: 0;
      font-weight: 600;
    }
    .app-feedback__dismiss {
      border: none;
      background: transparent;
      font-size: 1.25rem;
      line-height: 1;
      cursor: pointer;
      color: inherit;
    }
    @media (max-width: 60rem) {
      .shell__body {
        grid-template-columns: minmax(0, 1fr);
      }
    }
  `,
})
export class ShellComponent {
  private readonly store = inject(AuthStore);
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  readonly feedback = inject(ApiFeedbackStore);

  /** Nombre visible de la persona autenticada (null si anónima). */
  protected readonly userName = computed(() => this.store.user()?.full_name ?? null);

  /** Roles activos: alimentan insignias y módulos de navegación. */
  protected readonly roles = computed(() => this.store.roles());

  /** Cierre de sesión: revoca el refresh y vuelve al login. */
  protected logout(): void {
    this.auth.logout().subscribe({
      complete: () => void this.router.navigate(['/login']),
      error: () => void this.router.navigate(['/login']),
    });
  }

  /** La campana lleva a los avisos propios (TSK-83). */
  protected openNotifications(): void {
    void this.router.navigate(['/app/notifications']);
  }
}
