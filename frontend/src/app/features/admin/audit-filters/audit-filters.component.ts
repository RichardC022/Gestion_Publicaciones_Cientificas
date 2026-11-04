import { Component, effect, inject, input, output } from '@angular/core';
import {
  AbstractControl,
  NonNullableFormBuilder,
  ReactiveFormsModule,
  ValidationErrors,
} from '@angular/forms';

import {
  AUDIT_ACTIONS,
  AUDIT_RESULTS,
  AuditFilters,
  AuditResult,
} from '../../../core/models/audit.model';

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const ACTION = /^[A-Z0-9_]{1,64}$/;

/** Vacío o un UUID: el backend rechaza (`400`) cualquier otro valor. */
function optionalUuid(control: AbstractControl): ValidationErrors | null {
  const value = String(control.value ?? '').trim();
  return !value || UUID.test(value) ? null : { uuid: true };
}

function optionalAction(control: AbstractControl): ValidationErrors | null {
  const value = String(control.value ?? '').trim();
  return !value || ACTION.test(value) ? null : { action: true };
}

/**
 * Filtros combinados de la auditoría (HU-17): fecha, actor, acción,
 * manuscrito y resultado.
 *
 * Es presentacional: recibe los filtros vigentes (los de la URL) y emite
 * los nuevos al enviar; quien lo contiene los lleva a la URL y consulta.
 * Un campo vacío no es un filtro, y solo se envía lo que el backend acepta:
 * «Desde» no puede ser posterior a «Hasta», y actor y manuscrito son ids.
 */
@Component({
  selector: 'app-audit-filters',
  imports: [ReactiveFormsModule],
  template: `
    <form
      class="filters"
      role="search"
      [formGroup]="form"
      (ngSubmit)="submit()"
      aria-label="Filtrar la auditoría"
    >
      <div class="filters__field">
        <label for="audit-from">Desde</label>
        <input id="audit-from" type="date" formControlName="date_from" />
      </div>
      <div class="filters__field">
        <label for="audit-to">Hasta</label>
        <input id="audit-to" type="date" formControlName="date_to" />
      </div>
      <div class="filters__field">
        <label for="audit-action">Acción</label>
        <input
          id="audit-action"
          type="text"
          formControlName="action"
          list="audit-actions"
          maxlength="64"
          autocomplete="off"
          placeholder="Ej.: VERDICT_REGISTERED"
        />
        <datalist id="audit-actions">
          @for (option of actions; track option.value) {
            <option [value]="option.value">{{ option.label }}</option>
          }
        </datalist>
      </div>
      <div class="filters__field">
        <label for="audit-result">Resultado</label>
        <select id="audit-result" formControlName="result">
          <option value="">Todos</option>
          @for (option of results; track option.value) {
            <option [value]="option.value">{{ option.label }}</option>
          }
        </select>
      </div>
      <div class="filters__field filters__field--wide">
        <label for="audit-actor">Actor (id)</label>
        <input
          id="audit-actor"
          type="text"
          formControlName="actor"
          maxlength="40"
          autocomplete="off"
          placeholder="Identificador del usuario"
        />
      </div>
      <div class="filters__field filters__field--wide">
        <label for="audit-manuscript">Manuscrito (id)</label>
        <input
          id="audit-manuscript"
          type="text"
          formControlName="manuscript"
          maxlength="40"
          autocomplete="off"
          placeholder="Identificador del manuscrito"
        />
      </div>
      <div class="filters__actions">
        <button type="submit" class="btn btn--primary">Filtrar</button>
        <button type="button" class="btn btn--ghost" (click)="clear()">Limpiar</button>
      </div>
      @if (form.errors?.['dateRange']) {
        <p class="filters__error" role="alert">La fecha «Desde» no puede ser posterior a «Hasta».</p>
      }
      @if (form.controls.actor.invalid) {
        <p class="filters__error" role="alert">El actor debe ser un identificador válido.</p>
      }
      @if (form.controls.manuscript.invalid) {
        <p class="filters__error" role="alert">El manuscrito debe ser un identificador válido.</p>
      }
      @if (form.controls.action.invalid) {
        <p class="filters__error" role="alert">
          La acción solo admite mayúsculas, números y guion bajo.
        </p>
      }
    </form>
  `,
  styles: `
    .filters {
      display: flex;
      flex-wrap: wrap;
      align-items: flex-end;
      gap: 0.75rem 1rem;
      margin: 1rem 0;
      padding: 0.75rem 1rem;
      background: var(--gpc-surface-alt);
      border: 1px solid var(--gpc-border);
      border-radius: var(--gpc-radius);
    }
    .filters__field {
      display: flex;
      flex-direction: column;
      gap: 0.25rem;
      font-size: 0.875rem;
    }
    .filters__field--wide {
      flex: 1 1 18rem;
    }
    .filters__field input,
    .filters__field select {
      padding: 0.5rem 0.625rem;
      border: 1px solid var(--gpc-border);
      border-radius: var(--gpc-radius);
      font: inherit;
    }
    .filters__actions {
      display: flex;
      gap: 0.5rem;
    }
    .filters__error {
      flex-basis: 100%;
      margin: 0;
      color: var(--gpc-danger-700);
      font-size: 0.875rem;
    }
  `,
})
export class AuditFiltersComponent {
  private readonly formBuilder = inject(NonNullableFormBuilder);

  /** Filtros vigentes (los de la URL); el formulario los refleja. */
  readonly filters = input<AuditFilters>({});

  /** Filtros nuevos al enviar (sin campos vacíos). */
  readonly searched = output<AuditFilters>();

  /** Se quitaron todos los filtros. */
  readonly cleared = output<void>();

  protected readonly actions = AUDIT_ACTIONS;
  protected readonly results = AUDIT_RESULTS;

  protected readonly form = this.formBuilder.group(
    {
      date_from: [''],
      date_to: [''],
      action: ['', optionalAction],
      result: [''],
      actor: ['', optionalUuid],
      manuscript: ['', optionalUuid],
    },
    {
      validators: (group) => {
        const from = group.get('date_from')?.value as string;
        const to = group.get('date_to')?.value as string;
        return from && to && from > to ? { dateRange: true } : null;
      },
    },
  );

  constructor() {
    effect(() => {
      const filters = this.filters();
      this.form.reset(
        {
          date_from: filters.date_from ?? '',
          date_to: filters.date_to ?? '',
          action: filters.action ?? '',
          result: filters.result ?? '',
          actor: filters.actor ?? '',
          manuscript: filters.manuscript ?? '',
        },
        { emitEvent: false },
      );
    });
  }

  protected submit(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    const value = this.form.getRawValue();
    const filters: AuditFilters = {};
    if (value.date_from) {
      filters.date_from = value.date_from;
    }
    if (value.date_to) {
      filters.date_to = value.date_to;
    }
    const action = value.action.trim();
    if (action) {
      filters.action = action;
    }
    if (value.result) {
      filters.result = value.result as AuditResult;
    }
    for (const key of ['actor', 'manuscript'] as const) {
      const id = value[key].trim();
      if (id) {
        filters[key] = id.toLowerCase();
      }
    }
    this.searched.emit(filters);
  }

  protected clear(): void {
    this.cleared.emit();
  }
}
