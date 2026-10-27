import { CanDeactivateFn } from '@angular/router';

/**
 * Contrato de los componentes con formulario sucio: cuando
 * ``hasUnsavedChanges()`` es ``true`` el guard advierte antes de
 * abandonar la ruta (plan sección 3.3). Lo implementan los formularios
 * reactivos a partir de la Fase 2 (manuscrito, evaluación).
 */
export interface UnsavedChangesAware {
  hasUnsavedChanges(): boolean;
}

/**
 * Avisa antes de abandonar un formulario con cambios sin guardar.
 *
 * Se registra con ``canDeactivate`` en las rutas de formulario
 * (`/app/author/manuscripts/new`, `.../edit` y
 * `/app/reviewer/assignments/:id/evaluate`). El guard nunca decide por
 * la persona: muestra la advertencia nativa y respeta su respuesta.
 */
export const unsavedChangesGuard: CanDeactivateFn<unknown> = (component) => {
  const aware = component as UnsavedChangesAware | null;
  const dirty = !!aware?.hasUnsavedChanges?.();
  if (!dirty) {
    return true;
  }
  return window.confirm(
    'Tiene cambios sin guardar. Si abandona la página se perderán. ¿Desea continuar?',
  );
};
