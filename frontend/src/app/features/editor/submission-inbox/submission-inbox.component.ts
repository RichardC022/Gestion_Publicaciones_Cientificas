import { DatePipe } from '@angular/common';
import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { NonNullableFormBuilder, ReactiveFormsModule } from '@angular/forms';
import { ActivatedRoute, ParamMap, Router, RouterLink } from '@angular/router';
import { BehaviorSubject, catchError, combineLatest, map, of, switchMap, tap } from 'rxjs';

import { ApiError, toApiError } from '../../../core/models/api-error.model';
import {
  DEFAULT_SUBMISSION_ORDERING,
  SUBMISSION_ORDERINGS,
  SubmissionListParams,
  SubmissionOrdering,
  SubmissionRow,
} from '../../../core/models/editor.model';
import { Paginated } from '../../../core/models/paginated.model';
import { EditorService } from '../../../core/services/editor.service';
import { EmptyStateComponent } from '../../../shared/components/empty-state.component';
import { ErrorStateComponent } from '../../../shared/components/error-state.component';
import { LoadingSpinnerComponent } from '../../../shared/components/loading-spinner.component';
import { PaginationComponent } from '../../../shared/components/pagination.component';
import { RoundCounterComponent } from '../../../shared/components/round-counter.component';

/** Tamaño de página de la bandeja (la API admite hasta 100). */
export const PAGE_SIZE = 20;

/** Fechas y horas se muestran en la zona institucional (UTC-5, sin horario de verano). */
const INSTITUTIONAL_OFFSET = '-0500';

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

/**
 * Bandeja de nuevos envíos del Editor (plan sección 3.5, HU-10).
 *
 * * Lista solo los manuscritos `SUBMITTED` de su ámbito (el backend deja
 *   fuera los que el Editor registró o co-escribió): código, título,
 *   autor, área, fecha de envío, versión y ronda.
 * * Búsqueda, filtros por área y fechas, y orden.
 * * El estado vive en la URL (`search`, `area`, `date_from`, `date_to`,
 *   `ordering`, `page`): recargar o compartir el enlace conserva la vista.
 *   Un parámetro manipulado a mano que no es válido se ignora.
 * * No ofrece ninguna acción de auditoría global ni de Administrador.
 */
@Component({
  selector: 'app-submission-inbox',
  imports: [
    ReactiveFormsModule,
    RouterLink,
    DatePipe,
    RoundCounterComponent,
    PaginationComponent,
    LoadingSpinnerComponent,
    ErrorStateComponent,
    EmptyStateComponent,
  ],
  template: `
    <section aria-labelledby="submission-inbox-title">
      <header class="list-header">
        <h1 id="submission-inbox-title">Nuevos envíos</h1>
        <p class="list-header__count" role="status">
          @if (viewState() === 'ready') {
            {{ total() }} {{ total() === 1 ? 'envío pendiente' : 'envíos pendientes' }}
          }
        </p>
      </header>

      <form
        class="filters"
        [formGroup]="filters"
        (ngSubmit)="applyFilters()"
        aria-label="Filtros de la bandeja"
      >
        <div class="filters__field filters__field--wide">
          <label for="filter-search">Buscar</label>
          <input
            id="filter-search"
            type="search"
            formControlName="search"
            placeholder="Código, título, resumen o palabras clave"
          />
        </div>
        <div class="filters__field">
          <label for="filter-area">Área</label>
          <input id="filter-area" type="text" formControlName="area" />
        </div>
        <div class="filters__field">
          <label for="filter-from">Desde</label>
          <input id="filter-from" type="date" formControlName="date_from" />
        </div>
        <div class="filters__field">
          <label for="filter-to">Hasta</label>
          <input id="filter-to" type="date" formControlName="date_to" />
        </div>
        <div class="filters__field">
          <label for="filter-ordering">Ordenar por</label>
          <select id="filter-ordering" formControlName="ordering">
            @for (option of orderings; track option.value) {
              <option [value]="option.value">{{ option.label }}</option>
            }
          </select>
        </div>
        <div class="filters__actions">
          <button type="submit" class="btn btn--primary">Filtrar</button>
          <button type="button" class="btn btn--ghost" (click)="clearFilters()">Limpiar</button>
        </div>
        @if (filters.errors?.['dateRange']) {
          <p class="filters__error" role="alert">
            La fecha «Desde» no puede ser posterior a «Hasta».
          </p>
        }
      </form>

      @switch (viewState()) {
        @case ('loading') {
          <app-loading-spinner label="Cargando envíos…" />
        }
        @case ('error') {
          <app-error-state [message]="error()?.userMessage ?? ''" (retry)="reload()" />
        }
        @default {
          @if (rows().length === 0) {
            @if (hasFilters()) {
              <app-empty-state message="Ningún envío coincide con los filtros aplicados." />
            } @else {
              <app-empty-state message="No hay envíos nuevos por revisar." />
            }
          } @else {
            <div class="table-wrap">
              <table class="submissions">
                <caption class="visually-hidden">
                  Manuscritos enviados pendientes de pasar a revisión
                </caption>
                <thead>
                  <tr>
                    <th scope="col">Código</th>
                    <th scope="col">Título</th>
                    <th scope="col">Autor</th>
                    <th scope="col">Área</th>
                    <th scope="col">Enviado</th>
                    <th scope="col">Versión</th>
                    <th scope="col">Ronda</th>
                    <th scope="col"><span class="visually-hidden">Acciones</span></th>
                  </tr>
                </thead>
                <tbody>
                  @for (row of rows(); track row.id) {
                    <tr>
                      <td>
                        <a [routerLink]="['/app/editor/submissions', row.id]">{{ row.code }}</a>
                      </td>
                      <td class="submissions__title">{{ row.title || 'Sin título' }}</td>
                      <td>{{ row.corresponding_author || '—' }}</td>
                      <td>{{ row.area || '—' }}</td>
                      <td>
                        @if (row.submitted_at) {
                          {{ row.submitted_at | date: 'dd/MM/yyyy HH:mm' : offset }}
                        } @else {
                          —
                        }
                      </td>
                      <td>{{ row.current_version > 0 ? 'v' + row.current_version : '—' }}</td>
                      <td><app-round-counter [round]="row.current_round" /></td>
                      <td class="submissions__actions">
                        <a [routerLink]="['/app/editor/submissions', row.id]"
                          >Ver detalle<span class="visually-hidden"> de {{ row.code }}</span></a
                        >
                      </td>
                    </tr>
                  }
                </tbody>
              </table>
            </div>
            <app-pagination
              [page]="currentPage()"
              [pageSize]="pageSize"
              [totalItems]="total()"
              (pageChange)="goToPage($event)"
            />
          }
        }
      }
    </section>
  `,
  styles: `
    .list-header {
      display: flex;
      flex-wrap: wrap;
      align-items: baseline;
      justify-content: space-between;
      gap: 0.75rem;
    }
    .list-header__count {
      margin: 0;
      color: var(--gpc-text-muted);
    }
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
      flex: 1 1 16rem;
    }
    .filters__field select,
    .filters__field input {
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
    .table-wrap {
      overflow-x: auto;
    }
    .submissions {
      width: 100%;
      border-collapse: collapse;
      background: var(--gpc-surface-alt);
      border: 1px solid var(--gpc-border);
    }
    .submissions th,
    .submissions td {
      padding: 0.625rem 0.75rem;
      border-bottom: 1px solid var(--gpc-border);
      text-align: left;
      vertical-align: middle;
    }
    .submissions th {
      background: var(--gpc-primary-50);
      font-size: 0.8125rem;
      color: var(--gpc-primary-900);
    }
    .submissions__title {
      max-width: 22rem;
      overflow-wrap: anywhere;
    }
    .submissions__actions {
      white-space: nowrap;
    }
  `,
})
export class SubmissionInboxComponent {
  private readonly service = inject(EditorService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly formBuilder = inject(NonNullableFormBuilder);
  private readonly destroyRef = inject(DestroyRef);

  protected readonly pageSize = PAGE_SIZE;
  protected readonly offset = INSTITUTIONAL_OFFSET;
  protected readonly orderings = SUBMISSION_ORDERINGS;

  readonly filters = this.formBuilder.group(
    {
      search: [''],
      area: [''],
      date_from: [''],
      date_to: [''],
      ordering: [DEFAULT_SUBMISSION_ORDERING as string],
    },
    {
      validators: (group) => {
        const from = group.get('date_from')?.value as string;
        const to = group.get('date_to')?.value as string;
        return from && to && from > to ? { dateRange: true } : null;
      },
    },
  );

  protected readonly viewState = signal<'loading' | 'ready' | 'error'>('loading');
  protected readonly result = signal<Paginated<SubmissionRow> | null>(null);
  protected readonly error = signal<ApiError | null>(null);
  protected readonly currentPage = signal(1);
  protected readonly hasFilters = signal(false);

  private readonly retry$ = new BehaviorSubject<void>(undefined);

  constructor() {
    combineLatest([this.route.queryParamMap, this.retry$])
      .pipe(
        map(([params]) => params),
        tap((params) => this.syncFromUrl(params)),
        switchMap((params) =>
          this.service.listSubmissions(toInboxParams(params)).pipe(
            map((page) => ({ page, error: null as ApiError | null })),
            catchError((error: unknown) => of({ page: null, error: toApiError(error) })),
          ),
        ),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe(({ page, error }) => {
        this.result.set(page);
        this.error.set(error);
        this.viewState.set(error ? 'error' : 'ready');
      });
  }

  protected rows(): SubmissionRow[] {
    return this.result()?.results ?? [];
  }

  protected total(): number {
    return this.result()?.count ?? 0;
  }

  protected reload(): void {
    this.viewState.set('loading');
    this.retry$.next();
  }

  protected applyFilters(): void {
    if (this.filters.invalid) {
      this.filters.markAllAsTouched();
      return;
    }
    const { search, area, date_from, date_to, ordering } = this.filters.getRawValue();
    this.navigate({
      search: search.trim() || null,
      area: area.trim() || null,
      date_from: date_from || null,
      date_to: date_to || null,
      ordering: ordering === DEFAULT_SUBMISSION_ORDERING ? null : ordering,
      page: null,
    });
  }

  protected clearFilters(): void {
    this.navigate({
      search: null,
      area: null,
      date_from: null,
      date_to: null,
      ordering: null,
      page: null,
    });
  }

  protected goToPage(page: number): void {
    this.navigate({ page: page > 1 ? page : null });
  }

  private navigate(queryParams: Record<string, string | number | null>): void {
    void this.router.navigate([], {
      relativeTo: this.route,
      queryParams,
      queryParamsHandling: 'merge',
    });
  }

  /** Refleja la URL en el formulario y en el estado de la vista. */
  private syncFromUrl(params: ParamMap): void {
    const list = toInboxParams(params);
    this.viewState.set('loading');
    this.currentPage.set(list.page ?? 1);
    this.hasFilters.set(!!(list.search || list.area || list.date_from || list.date_to));
    this.filters.reset(
      {
        search: list.search ?? '',
        area: list.area ?? '',
        date_from: list.date_from ?? '',
        date_to: list.date_to ?? '',
        ordering: list.ordering ?? DEFAULT_SUBMISSION_ORDERING,
      },
      { emitEvent: false },
    );
  }
}

/**
 * Parámetros de la URL a filtros de la API. Los valores que no son
 * válidos se descartan: una URL editada a mano nunca llega al backend.
 */
export function toInboxParams(params: ParamMap): SubmissionListParams {
  const result: SubmissionListParams = { page_size: PAGE_SIZE };

  for (const key of ['search', 'area'] as const) {
    const value = params.get(key)?.trim();
    if (value) {
      result[key] = value;
    }
  }
  for (const key of ['date_from', 'date_to'] as const) {
    const value = params.get(key);
    if (value && ISO_DATE.test(value)) {
      result[key] = value;
    }
  }
  const ordering = params.get('ordering');
  if (SUBMISSION_ORDERINGS.some((option) => option.value === ordering)) {
    result.ordering = ordering as SubmissionOrdering;
  }
  const page = Number.parseInt(params.get('page') ?? '', 10);
  if (Number.isInteger(page) && page > 1) {
    result.page = page;
  }
  return result;
}
