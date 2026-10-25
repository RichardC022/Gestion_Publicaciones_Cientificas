import { Component } from '@angular/core';

/**
 * Listado público del catálogo.
 *
 * La búsqueda, los filtros combinados y la paginación se implementan en
 * la Fase 5 (TSK-80); esta versión garantiza la ruta pública con carga
 * diferida.
 */
@Component({
  selector: 'app-catalog-list',
  template: `
    <section>
      <h1>Catálogo público</h1>
      <p>Aquí se publican los artículos aceptados y activos.</p>
    </section>
  `,
})
export class CatalogListComponent {}
