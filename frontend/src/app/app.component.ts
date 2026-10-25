import { Component } from '@angular/core';
import { RouterOutlet } from '@angular/router';

/**
 * Componente raíz de la SPA.
 *
 * Solo expone el enrutador; el layout interno (shell, navegación y campana
 * de avisos) se monta en `core/layout` (TSK-14) sobre las rutas de `/app`.
 */
@Component({
  selector: 'app-root',
  imports: [RouterOutlet],
  template: '<router-outlet />',
})
export class AppComponent {}
