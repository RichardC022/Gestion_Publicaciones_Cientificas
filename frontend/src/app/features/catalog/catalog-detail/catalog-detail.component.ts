import { Component, inject } from '@angular/core';
import { ActivatedRoute } from '@angular/router';

/**
 * Ficha pública de un artículo aceptado.
 *
 * La ficha completa (autores, filiaciones, resumen y descarga) se
 * implementa en la Fase 5 (TSK-80).
 */
@Component({
  selector: 'app-catalog-detail',
  template: `
    <section>
      <h1>Ficha del artículo</h1>
      <p>Código: {{ code }}</p>
    </section>
  `,
})
export class CatalogDetailComponent {
  private readonly route = inject(ActivatedRoute);

  /** Código público del artículo leído de la ruta. */
  protected readonly code = this.route.snapshot.paramMap.get('code') ?? '';
}
