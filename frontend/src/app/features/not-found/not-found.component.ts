import { Component } from '@angular/core';
import { RouterLink } from '@angular/router';

/** Página 404 visual para rutas desconocidas. */
@Component({
  selector: 'app-not-found',
  imports: [RouterLink],
  template: `
    <section>
      <h1>Página no encontrada</h1>
      <p>El recurso solicitado no existe o ya no está disponible.</p>
      <a routerLink="/catalog">Volver al catálogo</a>
    </section>
  `,
})
export class NotFoundComponent {}
