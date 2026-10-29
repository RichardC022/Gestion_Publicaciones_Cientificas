import { Component } from '@angular/core';
import { RouterLink } from '@angular/router';

/**
 * Encabezado de las páginas públicas (catálogo): nombre del sistema y
 * acceso a la sesión institucional. No lee ni muestra datos de sesión.
 */
@Component({
  selector: 'app-public-header',
  imports: [RouterLink],
  template: `
    <header class="public-header">
      <a routerLink="/catalog" class="public-header__title">Catálogo de publicaciones científicas</a>
      <a routerLink="/login" class="btn btn--ghost">Iniciar sesión</a>
    </header>
  `,
  styles: `
    .public-header {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 0.75rem;
      padding: 0.75rem 1.5rem;
      background: var(--gpc-primary-900);
      color: #fff;
    }
    .public-header__title {
      color: inherit;
      font-weight: 700;
      font-size: 1.125rem;
      text-decoration: none;
    }
    .public-header .btn {
      background: #fff;
    }
  `,
})
export class PublicHeaderComponent {}
