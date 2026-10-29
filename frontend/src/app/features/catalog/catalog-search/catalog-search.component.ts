import { Component, effect, inject, input, output } from '@angular/core';
import { NonNullableFormBuilder, ReactiveFormsModule } from '@angular/forms';

import {
  CATALOG_LANGUAGES,
  CATALOG_ORDERINGS,
  CatalogFilters,
  CatalogOrdering,
  DEFAULT_CATALOG_ORDERING,
} from '../../../core/models/catalog.model';

/**
 * Formulario de búsqueda y filtros combinados del catálogo (HU-18).
 *
 * Es presentacional: recibe los filtros vigentes (los de la URL) y emite
 * los nuevos al enviar; quien lo contiene los lleva a la URL y consulta.
 * Un campo vacío no es un filtro, y la fecha «Desde» no puede ser
 * posterior a «Hasta» (el backend respondería `400`).
 */
@Component({
  selector: 'app-catalog-search',
  imports: [ReactiveFormsModule],
  template: `
    <form
      class="search"
      role="search"
      [formGroup]="form"
      (ngSubmit)="submit()"
      aria-label="Buscar en el catálogo"
    >
      <div class="search__field search__field--wide">
        <label for="catalog-search">Buscar</label>
        <input
          id="catalog-search"
          type="search"
          formControlName="search"
          maxlength="200"
          placeholder="Título, autor, palabra clave, área o resumen"
        />
      </div>
      <div class="search__field">
        <label for="catalog-area">Área</label>
        <input id="catalog-area" type="text" formControlName="area" maxlength="120" />
      </div>
      <div class="search__field">
        <label for="catalog-keyword">Palabra clave</label>
        <input id="catalog-keyword" type="text" formControlName="keyword" maxlength="100" />
      </div>
      <div class="search__field">
        <label for="catalog-language">Idioma</label>
        <select id="catalog-language" formControlName="language">
          <option value="">Todos</option>
          @for (language of languages; track language.value) {
            <option [value]="language.value">{{ language.label }}</option>
          }
        </select>
      </div>
      <div class="search__field">
        <label for="catalog-from">Publicado desde</label>
        <input id="catalog-from" type="date" formControlName="date_from" />
      </div>
      <div class="search__field">
        <label for="catalog-to">Publicado hasta</label>
        <input id="catalog-to" type="date" formControlName="date_to" />
      </div>
      <div class="search__field">
        <label for="catalog-ordering">Ordenar por</label>
        <select id="catalog-ordering" formControlName="ordering">
          @for (ordering of orderings; track ordering.value) {
            <option [value]="ordering.value">{{ ordering.label }}</option>
          }
        </select>
      </div>
      <div class="search__actions">
        <button type="submit" class="btn btn--primary">Buscar</button>
        <button type="button" class="btn btn--ghost" (click)="clear()">Limpiar</button>
      </div>
      @if (form.errors?.['dateRange']) {
        <p class="search__error" role="alert">
          La fecha «Desde» no puede ser posterior a «Hasta».
        </p>
      }
    </form>
  `,
  styles: `
    .search {
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
    .search__field {
      display: flex;
      flex-direction: column;
      gap: 0.25rem;
      font-size: 0.875rem;
    }
    .search__field--wide {
      flex: 1 1 100%;
    }
    .search__field input,
    .search__field select {
      padding: 0.5rem 0.625rem;
      border: 1px solid var(--gpc-border);
      border-radius: var(--gpc-radius);
      font: inherit;
    }
    .search__actions {
      display: flex;
      gap: 0.5rem;
    }
    .search__error {
      flex-basis: 100%;
      margin: 0;
      color: var(--gpc-danger-700);
      font-size: 0.875rem;
    }
  `,
})
export class CatalogSearchComponent {
  private readonly formBuilder = inject(NonNullableFormBuilder);

  /** Filtros vigentes (los de la URL); el formulario los refleja. */
  readonly filters = input<CatalogFilters>({});

  /** Filtros nuevos al buscar (sin campos vacíos). */
  readonly searched = output<CatalogFilters>();

  /** Se quitaron todos los filtros. */
  readonly cleared = output<void>();

  protected readonly languages = CATALOG_LANGUAGES;
  protected readonly orderings = CATALOG_ORDERINGS;

  protected readonly form = this.formBuilder.group(
    {
      search: [''],
      area: [''],
      keyword: [''],
      language: [''],
      date_from: [''],
      date_to: [''],
      ordering: [DEFAULT_CATALOG_ORDERING as string],
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
          search: filters.search ?? '',
          area: filters.area ?? '',
          keyword: filters.keyword ?? '',
          language: filters.language ?? '',
          date_from: filters.date_from ?? '',
          date_to: filters.date_to ?? '',
          ordering: filters.ordering ?? DEFAULT_CATALOG_ORDERING,
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
    const filters: CatalogFilters = {};
    for (const key of ['search', 'area', 'keyword'] as const) {
      const text = value[key].trim();
      if (text) {
        filters[key] = text;
      }
    }
    if (value.language) {
      filters.language = value.language;
    }
    if (value.date_from) {
      filters.date_from = value.date_from;
    }
    if (value.date_to) {
      filters.date_to = value.date_to;
    }
    if (value.ordering !== DEFAULT_CATALOG_ORDERING) {
      filters.ordering = value.ordering as CatalogOrdering;
    }
    this.searched.emit(filters);
  }

  protected clear(): void {
    this.cleared.emit();
  }
}
