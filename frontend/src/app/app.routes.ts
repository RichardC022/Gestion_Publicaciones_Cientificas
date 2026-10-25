import { Routes } from '@angular/router';

/**
 * Rutas de la SPA con carga diferida (lazy loading).
 *
 * En la Fase 0 solo existen las rutas públicas (catálogo, login y 404).
 * Las rutas internas de `/app` con sus guards llegan en la Fase 1
 * (TSK-25) y no existe ninguna ruta de selección de rol.
 */
export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'catalog' },
  {
    path: 'login',
    title: 'Iniciar sesión',
    loadComponent: () =>
      import('./features/auth/login/login.component').then((m) => m.LoginComponent),
  },
  {
    path: 'catalog',
    title: 'Catálogo público',
    loadComponent: () =>
      import('./features/catalog/catalog-list/catalog-list.component').then(
        (m) => m.CatalogListComponent,
      ),
  },
  {
    path: 'catalog/:code',
    title: 'Ficha del artículo',
    loadComponent: () =>
      import('./features/catalog/catalog-detail/catalog-detail.component').then(
        (m) => m.CatalogDetailComponent,
      ),
  },
  {
    path: '**',
    title: 'Página no encontrada',
    loadComponent: () =>
      import('./features/not-found/not-found.component').then((m) => m.NotFoundComponent),
  },
];
