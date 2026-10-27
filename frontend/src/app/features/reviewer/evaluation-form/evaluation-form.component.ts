import { Component } from '@angular/core';

/**
 * Andamio de ruta (TSK-25). El formulario de evaluación estructurado
 * se implementa en la TSK-67; desde esa tarea el componente implementa
 * `UnsavedChangesAware` para que el `unsavedChangesGuard` advierta
 * antes de abandonar el borrador.
 */
@Component({
  selector: 'app-evaluation-form',
  template: `
    <section aria-labelledby="evaluation-form-title">
      <h1 id="evaluation-form-title">Evaluación</h1>
      <p role="note">Formulario en construcción; se implementa en la TSK-67.</p>
    </section>
  `,
})
export class EvaluationFormComponent {}
