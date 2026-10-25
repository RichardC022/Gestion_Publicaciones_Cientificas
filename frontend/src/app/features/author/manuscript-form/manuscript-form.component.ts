import { Component } from '@angular/core';

/**
 * Andamio de ruta (TSK-25). El formulario reactivo de manuscrito con
 * su `FormArray` de autores se implementa en la TSK-41; desde esa
 * tarea el componente implementa `UnsavedChangesAware` para que el
 * `unsavedChangesGuard` advierta antes de abandonar la página.
 */
@Component({
  selector: 'app-manuscript-form',
  template: `
    <section aria-labelledby="manuscript-form-title">
      <h1 id="manuscript-form-title">Manuscrito</h1>
      <p role="note">Formulario en construcción; se implementa en la TSK-41.</p>
    </section>
  `,
})
export class ManuscriptFormComponent {}
