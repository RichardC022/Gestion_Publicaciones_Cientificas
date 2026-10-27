import { Routes } from '@angular/router';

import { Role } from './core/models/role.model';
import { authGuard } from './core/auth/auth.guard';
import { publicOnlyGuard } from './core/auth/public-only.guard';
import { rolesGuard } from './core/auth/roles.guard';
import { unsavedChangesGuard } from './core/auth/unsaved-changes.guard';

/**
 * Rutas de la SPA con carga diferida (plan sección 3.3).
 *
 * * `/login` es solo-público: con sesión activa redirige al panel.
 * * `/app/**` exige sesión (`authGuard`) y las rutas de módulo exigen
 *   al menos un rol activo (`rolesGuard` con `data.roles`); sin el
 *   rol se muestra el `403` de `/forbidden`.
 * * Los formularios advierten antes de abandonar con cambios sin
 *   guardar (`unsavedChangesGuard`).
 * * No existe ruta, guard ni componente de selección o conmutación de
 *   rol: una persona con roles simultáneos accede a todas sus
 *   secciones sin conmutar.
 */
export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'catalog' },
  {
    path: 'login',
    title: 'Iniciar sesión',
    canActivate: [publicOnlyGuard],
    loadComponent: () =>
      import('./features/auth/login/login.component').then((m) => m.LoginComponent),
  },
  {
    path: 'forbidden',
    title: 'Acceso denegado',
    loadComponent: () =>
      import('./features/forbidden/forbidden.component').then((m) => m.ForbiddenComponent),
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
    // Área interna: el ShellComponent de TSK-14 envuelve el contenido
    // enrutado; TSK-26 lo conecta con el AuthStore.
    path: 'app',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./core/layout/shell.component').then((m) => m.ShellComponent),
    children: [
      { path: '', pathMatch: 'full', redirectTo: 'dashboard' },
      {
        path: 'dashboard',
        title: 'Panel unificado',
        loadComponent: () =>
          import('./features/dashboard/unified-dashboard/unified-dashboard.component').then(
            (m) => m.UnifiedDashboardComponent,
          ),
      },
      {
        path: 'author/manuscripts',
        title: 'Mis manuscritos',
        canActivate: [rolesGuard],
        data: { roles: ['AUTHOR'] as Role[] },
        loadComponent: () =>
          import('./features/author/manuscript-list/manuscript-list.component').then(
            (m) => m.ManuscriptListComponent,
          ),
      },
      {
        path: 'author/manuscripts/new',
        title: 'Nuevo manuscrito',
        canActivate: [rolesGuard],
        canDeactivate: [unsavedChangesGuard],
        data: { roles: ['AUTHOR'] as Role[] },
        loadComponent: () =>
          import('./features/author/manuscript-form/manuscript-form.component').then(
            (m) => m.ManuscriptFormComponent,
          ),
      },
      {
        path: 'author/manuscripts/:id',
        title: 'Detalle del manuscrito',
        canActivate: [rolesGuard],
        data: { roles: ['AUTHOR'] as Role[] },
        loadComponent: () =>
          import('./features/author/manuscript-detail/manuscript-detail.component').then(
            (m) => m.ManuscriptDetailComponent,
          ),
      },
      {
        path: 'author/manuscripts/:id/edit',
        title: 'Editar manuscrito',
        canActivate: [rolesGuard],
        canDeactivate: [unsavedChangesGuard],
        data: { roles: ['AUTHOR'] as Role[] },
        loadComponent: () =>
          import('./features/author/manuscript-form/manuscript-form.component').then(
            (m) => m.ManuscriptFormComponent,
          ),
      },
      {
        path: 'author/manuscripts/:id/history',
        title: 'Historial de versiones',
        canActivate: [rolesGuard],
        data: { roles: ['AUTHOR'] as Role[] },
        loadComponent: () =>
          import('./features/author/version-history/version-history.component').then(
            (m) => m.VersionHistoryComponent,
          ),
      },
      {
        path: 'editor/submissions',
        title: 'Nuevos envíos',
        canActivate: [rolesGuard],
        data: { roles: ['EDITOR'] as Role[] },
        loadComponent: () =>
          import('./features/editor/submission-inbox/submission-inbox.component').then(
            (m) => m.SubmissionInboxComponent,
          ),
      },
      {
        path: 'editor/submissions/:id',
        title: 'Detalle del envío',
        canActivate: [rolesGuard],
        data: { roles: ['EDITOR'] as Role[] },
        loadComponent: () =>
          import('./features/editor/submission-detail/submission-detail.component').then(
            (m) => m.SubmissionDetailComponent,
          ),
      },
      {
        path: 'editor/assignments/expired',
        title: 'Asignaciones vencidas',
        canActivate: [rolesGuard],
        data: { roles: ['EDITOR'] as Role[] },
        loadComponent: () =>
          import(
            './features/editor/expired-assignments/expired-assignments.component'
          ).then((m) => m.ExpiredAssignmentsComponent),
      },
      {
        path: 'editor/incidents',
        title: 'Incidentes confidenciales',
        canActivate: [rolesGuard],
        data: { roles: ['EDITOR'] as Role[] },
        loadComponent: () =>
          import('./features/editor/incident-list/incident-list.component').then(
            (m) => m.IncidentListComponent,
          ),
      },
      {
        path: 'reviewer/assignments',
        title: 'Mis asignaciones',
        canActivate: [rolesGuard],
        data: { roles: ['REVIEWER'] as Role[] },
        loadComponent: () =>
          import('./features/reviewer/assignment-list/assignment-list.component').then(
            (m) => m.AssignmentListComponent,
          ),
      },
      {
        path: 'reviewer/assignments/:id',
        title: 'Detalle de la asignación',
        canActivate: [rolesGuard],
        data: { roles: ['REVIEWER'] as Role[] },
        loadComponent: () =>
          import('./features/reviewer/assignment-detail/assignment-detail.component').then(
            (m) => m.AssignmentDetailComponent,
          ),
      },
      {
        path: 'reviewer/assignments/:id/evaluate',
        title: 'Evaluación',
        canActivate: [rolesGuard],
        canDeactivate: [unsavedChangesGuard],
        data: { roles: ['REVIEWER'] as Role[] },
        loadComponent: () =>
          import('./features/reviewer/evaluation-form/evaluation-form.component').then(
            (m) => m.EvaluationFormComponent,
          ),
      },
      {
        path: 'reviewer/history',
        title: 'Historial de evaluaciones',
        canActivate: [rolesGuard],
        data: { roles: ['REVIEWER'] as Role[] },
        loadComponent: () =>
          import(
            './features/reviewer/evaluation-history/evaluation-history.component'
          ).then((m) => m.EvaluationHistoryComponent),
      },
      {
        path: 'admin/audit',
        title: 'Auditoría',
        canActivate: [rolesGuard],
        data: { roles: ['ADMIN'] as Role[] },
        loadComponent: () =>
          import('./features/admin/audit-log-list/audit-log-list.component').then(
            (m) => m.AuditLogListComponent,
          ),
      },
      {
        path: 'admin/audit/:id',
        title: 'Detalle del evento',
        canActivate: [rolesGuard],
        data: { roles: ['ADMIN'] as Role[] },
        loadComponent: () =>
          import('./features/admin/audit-log-detail/audit-log-detail.component').then(
            (m) => m.AuditLogDetailComponent,
          ),
      },
      {
        path: 'notifications',
        title: 'Avisos',
        loadComponent: () =>
          import(
            './features/notifications/notification-list/notification-list.component'
          ).then((m) => m.NotificationListComponent),
      },
    ],
  },
  {
    path: '**',
    title: 'Página no encontrada',
    loadComponent: () =>
      import('./features/not-found/not-found.component').then((m) => m.NotFoundComponent),
  },
];
