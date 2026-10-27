import { DatePipe } from '@angular/common';
import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { NonNullableFormBuilder, ReactiveFormsModule } from '@angular/forms';
import { ActivatedRoute, ParamMap, Router, RouterLink } from '@angular/router';
import { BehaviorSubject, catchError, combineLatest, map, of, switchMap, tap } from 'rxjs';

import { ApiError, toApiError } from '../../../core/models/api-error.model';
import {
  MANUSCRIPT_STATUSES,
  Manuscript,
  ManuscriptListParams,
  ManuscriptStatus,
  isEditable,
  nextAction,
} from '../../../core/models/manuscript.model';
import { Paginated } from '../../../core/models/paginated.model';
import { ManuscriptService } from '../../../core/services/manuscript.service';
import { EmptyStateComponent } from '../../../shared/components/empty-state.component';
import { ErrorStateComponent } from '../../../shared/components/error-state.component';
import { LoadingSpinnerComponent } from '../../../shared/components/loading-spinner.component';
import { PaginationComponent } from '../../../shared/components/pagination.component';
import { RoundCounterComponent } from '../../../shared/components/round-counter.component';
import {
  STATUS_LABELS,
  StatusBadgeComponent,
} from '../../../shared/components/status-badge.component';

/** Tamaño de página del listado (la API admite hasta 100). */
export const PAGE_SIZE = 20;

/** Fechas y horas se muestran en la zona institucional (UTC-5, sin horario de verano). */
const INSTITUTIONAL_OFFSET = '-0500';

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

/**
 * Listado propio de manuscritos del Autor (plan sección 3.5, HU-06).
 *
 * * Tabla paginada con código, título, estado, versión, ronda, última
 *   actualización y acción pendiente.
 * * Filtros por estado y fecha, y vista de archivados (dados de baja).
 * * El estado vive en la URL (`status`, `date_from`, `date_to`,
 *   `archived`, `page`): recargar o compartir el enlace conserva la
 *   vista. Un parámetro manipulado a mano que no es válido se ignora
 *   en lugar de provocar un `400`.
 * * La edición solo se ofrece en `DRAFT` o `REQUIRES_CORRECTIONS`.
 */
@Component({
  selector: 'app-manuscript-list',
  imports: [
    ReactiveFormsModule,
    RouterLink,
    DatePipe,
    StatusBadgeComponent,
    RoundCounterComponent,
    PaginationComponent,
    LoadingSpinnerComponent,
    ErrorStateComponent,
    EmptyStateComponent,
  ],
  template: `
    <section aria-labelledby="manuscript-list-title">
      <header class="list-header">
        <h1 id="manuscript-list-title">
          {{ archivedView() ? 'Manuscritos archivados' : 'Mis manuscritos' }}
        </h1>
        <a class="btn btn--primary" routerLink="/app/author/manuscripts/new">Nuevo manuscrito</a>
      </header>

      <form
        class="filters"
        [formGroup]="filters"
        (ngSubmit)="applyFilters()"
        aria-label="Filtros del listado"
      >
        <div class="filters__field">
          <label for="filter-status">Estado</label>
          <select id="filter-status" formControlName="status">
            <option value="">Todos</option>
            @for (status of statuses; track status) {
              <option [value]="status">{{ label(status) }}</option>
            }
          </select>
        </div>
        <div class="filters__field">
          <label for="filter-from">Desde</label>
          <input id="filter-from" type="date" formControlName="date_from" />
        </div>
        <div class="filters__field">
          <label for="filter-to">Hasta</label>
          <input id="filter-to" type="date" formControlName="date_to" />
        </div>
        <div class="filters__field filters__field--check">
          <input id="filter-archived" type="checkbox" formControlName="archived" />
          <label for="filter-archived">Ver archivados (dados de baja)</label>
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
          <app-loading-spinner label="Cargando manuscritos…" />
        }
        @case ('error') {
          <app-error-state [message]="error()?.userMessage ?? ''" (retry)="reload()" />
        }
        @default {
          @if (rows().length === 0) {
            @if (hasFilters()) {
              <app-empty-state message="Ningún manuscrito coincide con los filtros aplicados." />
            } @else if (archivedView()) {
              <app-empty-state message="No tiene manuscritos archivados." />
            } @else {
              <app-empty-state
                message="Aún no ha registrado manuscritos."
                actionLabel="Registrar mi primer manuscrito"
                (action)="createFirst()"
              />
            }
          } @else {
            <div class="table-wrap">
              <table class="manuscripts">
                <caption class="visually-hidden">
                  Listado de manuscritos propios
                </caption>
                <thead>
                  <tr>
                    <th scope="col">Código</th>
                    <th scope="col">Título</th>
                    <th scope="col">Estado</th>
                    <th scope="col">Versión</th>
                    <th scope="col">Ronda</th>
                    <th scope="col">Actualizado</th>
                    <th scope="col">Acción pendiente</th>
                    <th scope="col"><span class="visually-hidden">Acciones</span></th>
                  </tr>
                </thead>
                <tbody>
                  @for (row of rows(); track row.id) {
                    <tr>
                      <td>
                        <a [routerLink]="['/app/author/manuscripts', row.id]">{{ row.code }}</a>
                      </td>
                      <td class="manuscripts__title">{{ row.title || 'Sin título' }}</td>
                      <td>
                        <app-status-badge [status]="row.status" />
                        @if (!row.is_active) {
                          <app-status-badge status="WITHDRAWN" />
                        }
                      </td>
                      <td>{{ row.current_version > 0 ? 'v' + row.current_version : '—' }}</td>
                      <td><app-round-counter [round]="row.current_round" /></td>
                      <td>{{ row.updated_at | date: 'dd/MM/yyyy HH:mm' : offset }}</td>
                      <td>{{ pending(row) }}</td>
                      <td class="manuscripts__actions">
                        <a [routerLink]="['/app/author/manuscripts', row.id]">Ver</a>
                        @if (canEdit(row)) {
                          <a [routerLink]="['/app/author/manuscripts', row.id, 'edit']">Editar</a>
                        }
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
      align-items: center;
      justify-content: space-between;
      gap: 0.75rem;
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
    .filters__field--check {
      flex-direction: row;
      align-items: center;
      gap: 0.5rem;
    }
    .filters__field select,
    .filters__field input[type='date'] {
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
    .manuscripts {
      width: 100%;
      border-collapse: collapse;
      background: var(--gpc-surface-alt);
      border: 1px solid var(--gpc-border);
    }
    .manuscripts th,
    .manuscripts td {
      padding: 0.625rem 0.75rem;
      border-bottom: 1px solid var(--gpc-border);
      text-align: left;
      vertical-align: middle;
    }
    .manuscripts th {
      background: var(--gpc-primary-50);
      font-size: 0.8125rem;
      color: var(--gpc-primary-900);
    }
    .manuscripts__title {
      max-width: 22rem;
      overflow-wrap: anywhere;
    }
    .manuscripts__actions {
      display: flex;
      gap: 0.75rem;
      white-space: nowrap;
    }
  `,
})
export class ManuscriptListComponent {
  private readonly service = inject(ManuscriptService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly formBuilder = inject(NonNullableFormBuilder);
  private readonly destroyRef = inject(DestroyRef);

  protected readonly pageSize = PAGE_SIZE;
  protected readonly offset = INSTITUTIONAL_OFFSET;
  protected readonly statuses = MANUSCRIPT_STATUSES;

  readonly filters = this.formBuilder.group(
    {
      status: [''],
      date_from: [''],
      date_to: [''],
      archived: [false],
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
  protected readonly result = signal<Paginated<Manuscript> | null>(null);
  protected readonly error = signal<ApiError | null>(null);
  protected readonly currentPage = signal(1);
  protected readonly archivedView = signal(false);
  protected readonly hasFilters = signal(false);

  private readonly retry$ = new BehaviorSubject<void>(undefined);

  constructor() {
    combineLatest([this.route.queryParamMap, this.retry$])
      .pipe(
        map(([params]) => params),
        tap((params) => this.syncFromUrl(params)),
        switchMap((params) =>
          this.service.list(toListParams(params)).pipe(
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

  protected rows(): Manuscript[] {
    return this.result()?.results ?? [];
  }

  protected total(): number {
    return this.result()?.count ?? 0;
  }

  protected label(status: string): string {
    return STATUS_LABELS[status] ?? status;
  }

  protected canEdit(manuscript: Manuscript): boolean {
    return isEditable(manuscript);
  }

  protected pending(manuscript: Manuscript): string {
    return nextAction(manuscript).short;
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
    const { status, date_from, date_to, archived } = this.filters.getRawValue();
    this.navigate({
      status: status || null,
      date_from: date_from || null,
      date_to: date_to || null,
      archived: archived ? 'true' : null,
      page: null,
    });
  }

  protected clearFilters(): void {
    this.navigate({ status: null, date_from: null, date_to: null, archived: null, page: null });
  }

  protected goToPage(page: number): void {
    this.navigate({ page: page > 1 ? page : null });
  }

  protected createFirst(): void {
    void this.router.navigate(['/app/author/manuscripts/new']);
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
    const list = toListParams(params);
    this.viewState.set('loading');
    this.currentPage.set(list.page ?? 1);
    this.archivedView.set(!!list.archived);
    this.hasFilters.set(!!(list.status || list.date_from || list.date_to));
    this.filters.reset(
      {
        status: list.status ?? '',
        date_from: list.date_from ?? '',
        date_to: list.date_to ?? '',
        archived: !!list.archived,
      },
      { emitEvent: false },
    );
  }
}

/**
 * Parámetros de la URL a filtros de la API. Los valores que no son
 * válidos se descartan: una URL editada a mano nunca llega al backend.
 */
export function toListParams(params: ParamMap): ManuscriptListParams {
  const result: ManuscriptListParams = { page_size: PAGE_SIZE };

  const status = params.get('status');
  if (status && (MANUSCRIPT_STATUSES as readonly string[]).includes(status)) {
    result.status = status as ManuscriptStatus;
  }
  for (const key of ['date_from', 'date_to'] as const) {
    const value = params.get(key);
    if (value && ISO_DATE.test(value)) {
      result[key] = value;
    }
  }
  if (params.get('archived') === 'true') {
    result.archived = true;
  }
  const page = Number.parseInt(params.get('page') ?? '', 10);
  if (Number.isInteger(page) && page > 1) {
    result.page = page;
  }
  return result;
}
