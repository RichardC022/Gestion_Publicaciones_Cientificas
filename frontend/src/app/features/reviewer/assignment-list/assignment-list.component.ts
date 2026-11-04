import { DatePipe } from '@angular/common';
import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { BehaviorSubject, catchError, combineLatest, map, of, switchMap, tap } from 'rxjs';

import { toPage } from '../../../core/http/query-params';
import { ApiError, toApiError } from '../../../core/models/api-error.model';
import { Paginated } from '../../../core/models/paginated.model';
import { ReviewerAssignmentRow, hasDetail } from '../../../core/models/reviewer.model';
import { ReviewerService } from '../../../core/services/reviewer.service';
import { EmptyStateComponent } from '../../../shared/components/empty-state.component';
import { ErrorStateComponent } from '../../../shared/components/error-state.component';
import { LoadingSpinnerComponent } from '../../../shared/components/loading-spinner.component';
import { PaginationComponent } from '../../../shared/components/pagination.component';
import { StatusBadgeComponent } from '../../../shared/components/status-badge.component';

/** Tamaño de página de la vista (la API admite hasta 100). */
export const PAGE_SIZE = 20;

/** Fechas y horas se muestran en la zona institucional (UTC-5, sin horario de verano). */
const INSTITUTIONAL_OFFSET = '-0500';

/**
 * Bandeja de asignaciones del Revisor (plan sección 3.5, HU-14).
 *
 * * Lista solo las asignaciones propias, con código, título, área, versión,
 *   ronda, fecha límite y estado (pendiente, en plazo, vencida, evaluada o
 *   revocada). El estado lo deriva el servidor con su reloj.
 * * **Doble ciego:** la fila no tiene autores, filiaciones ni contacto; el
 *   tipo `ReviewerAssignmentRow` ni siquiera los declara.
 * * Solo las asignaciones activas o completadas tienen detalle; las demás se
 *   muestran sin enlace porque el servidor respondería `404`.
 * * La página vive en la URL (`page`); un valor manipulado se ignora.
 */
@Component({
  selector: 'app-assignment-list',
  imports: [
    DatePipe,
    RouterLink,
    StatusBadgeComponent,
    PaginationComponent,
    LoadingSpinnerComponent,
    ErrorStateComponent,
    EmptyStateComponent,
  ],
  template: `
    <section aria-labelledby="assignment-list-title">
      <header class="list-header">
        <h1 id="assignment-list-title">Mis asignaciones</h1>
        <p class="list-header__count" role="status">
          @if (viewState() === 'ready') {
            {{ total() }} {{ total() === 1 ? 'asignación' : 'asignaciones' }}
          }
        </p>
      </header>

      @switch (viewState()) {
        @case ('loading') {
          <app-loading-spinner label="Cargando asignaciones…" />
        }
        @case ('error') {
          <app-error-state [message]="error()?.userMessage ?? ''" (retry)="reload()" />
        }
        @default {
          @if (rows().length === 0) {
            <app-empty-state message="No tiene asignaciones de revisión por ahora." />
          } @else {
            <div class="table-wrap">
              <table class="assignments">
                <caption class="visually-hidden">
                  Asignaciones de revisión
                </caption>
                <thead>
                  <tr>
                    <th scope="col">Manuscrito</th>
                    <th scope="col">Título</th>
                    <th scope="col">Área</th>
                    <th scope="col">Versión</th>
                    <th scope="col">Fecha límite</th>
                    <th scope="col">Estado</th>
                  </tr>
                </thead>
                <tbody>
                  @for (row of rows(); track row.id) {
                    <tr>
                      <td>
                        @if (canOpen(row)) {
                          <a [routerLink]="['/app/reviewer/assignments', row.id]">{{
                            row.manuscript_code
                          }}</a>
                        } @else {
                          {{ row.manuscript_code }}
                        }
                      </td>
                      <td class="assignments__title">{{ row.manuscript_title || 'Sin título' }}</td>
                      <td>{{ row.area }}</td>
                      <td>
                        v{{ row.version_number }}
                        <span class="assignments__meta">Ronda {{ row.round_number }}</span>
                      </td>
                      <td>{{ row.due_at | date: 'dd/MM/yyyy HH:mm' : offset }}</td>
                      <td><app-status-badge [status]="row.state" /></td>
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
    .table-wrap {
      overflow-x: auto;
    }
    .assignments {
      width: 100%;
      border-collapse: collapse;
      background: var(--gpc-surface-alt);
      border: 1px solid var(--gpc-border);
    }
    .assignments th,
    .assignments td {
      padding: 0.625rem 0.75rem;
      border-bottom: 1px solid var(--gpc-border);
      text-align: left;
      vertical-align: middle;
    }
    .assignments th {
      background: var(--gpc-primary-50);
      font-size: 0.8125rem;
      color: var(--gpc-primary-900);
    }
    .assignments__title {
      max-width: 22rem;
      overflow-wrap: anywhere;
    }
    .assignments__meta {
      display: block;
      font-size: 0.8125rem;
      color: var(--gpc-text-muted);
    }
  `,
})
export class AssignmentListComponent {
  private readonly service = inject(ReviewerService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);

  protected readonly pageSize = PAGE_SIZE;
  protected readonly offset = INSTITUTIONAL_OFFSET;

  protected readonly viewState = signal<'loading' | 'ready' | 'error'>('loading');
  protected readonly result = signal<Paginated<ReviewerAssignmentRow> | null>(null);
  protected readonly error = signal<ApiError | null>(null);
  protected readonly currentPage = signal(1);

  private readonly retry$ = new BehaviorSubject<void>(undefined);

  constructor() {
    combineLatest([this.route.queryParamMap, this.retry$])
      .pipe(
        map(([params]) => toPage(params)),
        tap((page) => {
          this.viewState.set('loading');
          this.currentPage.set(page);
        }),
        switchMap((page) =>
          this.service.listAssignments(page, PAGE_SIZE).pipe(
            map((data) => ({ data, error: null as ApiError | null })),
            catchError((error: unknown) => of({ data: null, error: toApiError(error) })),
          ),
        ),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe(({ data, error }) => {
        this.result.set(data);
        this.error.set(error);
        this.viewState.set(error ? 'error' : 'ready');
      });
  }

  protected rows(): ReviewerAssignmentRow[] {
    return this.result()?.results ?? [];
  }

  protected total(): number {
    return this.result()?.count ?? 0;
  }

  protected canOpen(row: ReviewerAssignmentRow): boolean {
    return hasDetail(row);
  }

  protected reload(): void {
    this.retry$.next();
  }

  protected goToPage(page: number): void {
    void this.router.navigate([], {
      relativeTo: this.route,
      queryParams: { page: page > 1 ? page : null },
      queryParamsHandling: 'merge',
    });
  }
}
