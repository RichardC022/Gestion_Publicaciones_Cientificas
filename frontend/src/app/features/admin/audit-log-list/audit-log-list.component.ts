import { DatePipe } from '@angular/common';
import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { BehaviorSubject, catchError, combineLatest, map, of, switchMap, tap } from 'rxjs';

import { toPage } from '../../../core/http/query-params';
import { ApiError, toApiError } from '../../../core/models/api-error.model';
import {
  AuditEvent,
  AuditFilters,
  actionLabel,
  hasAuditFilters,
  resultLabel,
  shortHash,
  toAuditFilters,
} from '../../../core/models/audit.model';
import { Paginated } from '../../../core/models/paginated.model';
import { ROLE_LABELS } from '../../../core/models/role.model';
import { AuditService } from '../../../core/services/audit.service';
import { EmptyStateComponent } from '../../../shared/components/empty-state.component';
import { ErrorStateComponent } from '../../../shared/components/error-state.component';
import { LoadingSpinnerComponent } from '../../../shared/components/loading-spinner.component';
import { PaginationComponent } from '../../../shared/components/pagination.component';
import { AuditFiltersComponent } from '../audit-filters/audit-filters.component';

/** Tamaño de página de la auditoría (la API admite hasta 100). */
export const PAGE_SIZE = 25;

/** Las fechas se muestran en la zona institucional (UTC-5, sin horario de verano). */
const INSTITUTIONAL_OFFSET = '-0500';

/**
 * Auditoría global del Administrador (plan sección 3.5, HU-17).
 *
 * * Tabla paginada, del evento más reciente al más antiguo, con actor
 *   (id opaco), rol, acción, entidad, manuscrito, resultado, fecha y hash.
 * * Los filtros (fecha, actor, acción, manuscrito y resultado) y la página
 *   viven en la URL: recargar o compartir el enlace conserva la vista, y un
 *   parámetro manipulado a mano se descarta en lugar de provocar un `400`.
 * * Pulsar un actor o un manuscrito de la tabla filtra por él.
 * * El listado nunca decide permisos de escritura: la acción «Habilitar
 *   corrección» solo existe en el detalle, cuando el backend la autoriza.
 */
@Component({
  selector: 'app-audit-log-list',
  imports: [
    DatePipe,
    RouterLink,
    AuditFiltersComponent,
    PaginationComponent,
    LoadingSpinnerComponent,
    ErrorStateComponent,
    EmptyStateComponent,
  ],
  template: `
    <section aria-labelledby="audit-log-list-title">
      <header class="list-header">
        <h1 id="audit-log-list-title">Auditoría</h1>
        <p class="list-header__count" role="status">
          @if (viewState() === 'ready') {
            {{ total() }} {{ total() === 1 ? 'evento' : 'eventos' }}
          }
        </p>
      </header>

      <app-audit-filters [filters]="filters()" (searched)="search($event)" (cleared)="clear()" />

      @switch (viewState()) {
        @case ('loading') {
          <app-loading-spinner label="Cargando eventos…" />
        }
        @case ('error') {
          <app-error-state [message]="error()?.userMessage ?? ''" (retry)="reload()" />
        }
        @default {
          @if (rows().length === 0) {
            @if (filtered()) {
              <app-empty-state message="Ningún evento coincide con los filtros aplicados." />
            } @else {
              <app-empty-state message="Aún no hay eventos de auditoría." />
            }
          } @else {
            <div class="table-wrap">
              <table class="events">
                <caption class="visually-hidden">
                  Eventos de auditoría, del más reciente al más antiguo
                </caption>
                <thead>
                  <tr>
                    <th scope="col">Fecha</th>
                    <th scope="col">Actor</th>
                    <th scope="col">Rol</th>
                    <th scope="col">Acción</th>
                    <th scope="col">Entidad</th>
                    <th scope="col">Manuscrito</th>
                    <th scope="col">Resultado</th>
                    <th scope="col">Hash</th>
                    <th scope="col"><span class="visually-hidden">Acciones</span></th>
                  </tr>
                </thead>
                <tbody>
                  @for (row of rows(); track row.id) {
                    <tr>
                      <td class="events__date">
                        {{ row.occurred_at | date: 'dd/MM/yyyy HH:mm:ss' : offset }}
                      </td>
                      <td>
                        @if (row.actor_id) {
                          <a
                            class="events__id"
                            [routerLink]="[]"
                            [queryParams]="{ actor: row.actor_id, page: null }"
                            queryParamsHandling="merge"
                            [title]="row.actor_id"
                            >{{ row.actor_id.slice(0, 8) }}<span class="visually-hidden"
                              >: filtrar por este actor</span
                            ></a
                          >
                        } @else {
                          <span>Sistema</span>
                        }
                      </td>
                      <td>{{ role(row) }}</td>
                      <td>
                        <span>{{ action(row) }}</span>
                        <span class="events__code">{{ row.action }}</span>
                      </td>
                      <td>{{ row.entity_type }}</td>
                      <td>
                        @if (row.manuscript_id) {
                          <a
                            [routerLink]="[]"
                            [queryParams]="{ manuscript: row.manuscript_id, page: null }"
                            queryParamsHandling="merge"
                            >{{ row.manuscript_code ?? row.manuscript_id.slice(0, 8)
                            }}<span class="visually-hidden">: filtrar por este manuscrito</span></a
                          >
                        } @else {
                          —
                        }
                      </td>
                      <td>
                        <span [class]="'result result--' + row.result.toLowerCase()">{{
                          resultText(row)
                        }}</span>
                      </td>
                      <td>
                        <code class="events__hash" [title]="row.entry_hash">{{
                          hash(row)
                        }}</code>
                      </td>
                      <td class="events__actions">
                        <a [routerLink]="['/app/admin/audit', row.id]"
                          >Ver detalle<span class="visually-hidden"> del evento {{ row.action }}</span></a
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
    .table-wrap {
      overflow-x: auto;
    }
    .events {
      width: 100%;
      border-collapse: collapse;
      background: var(--gpc-surface-alt);
      border: 1px solid var(--gpc-border);
    }
    .events th,
    .events td {
      padding: 0.5rem 0.75rem;
      border-bottom: 1px solid var(--gpc-border);
      text-align: left;
      vertical-align: middle;
      font-size: 0.875rem;
    }
    .events th {
      background: var(--gpc-primary-50);
      font-size: 0.8125rem;
      color: var(--gpc-primary-900);
    }
    .events__date,
    .events__actions {
      white-space: nowrap;
    }
    .events__id,
    .events__hash {
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    }
    .events__code {
      display: block;
      font-size: 0.75rem;
      color: var(--gpc-text-muted);
      overflow-wrap: anywhere;
    }
    .result {
      padding: 0.125rem 0.5rem;
      border-radius: 999px;
      border: 1px solid var(--gpc-border);
      font-size: 0.8125rem;
    }
    .result--success {
      background: var(--gpc-primary-50);
      border-color: var(--gpc-primary-100);
    }
    .result--denied,
    .result--failure {
      background: var(--gpc-danger-100);
      border-color: var(--gpc-danger-700);
    }
  `,
})
export class AuditLogListComponent {
  private readonly service = inject(AuditService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);

  protected readonly pageSize = PAGE_SIZE;
  protected readonly offset = INSTITUTIONAL_OFFSET;

  protected readonly viewState = signal<'loading' | 'ready' | 'error'>('loading');
  protected readonly events = signal<Paginated<AuditEvent> | null>(null);
  protected readonly error = signal<ApiError | null>(null);
  protected readonly currentPage = signal(1);
  protected readonly filters = signal<AuditFilters>({});
  protected readonly filtered = signal(false);

  private readonly retry$ = new BehaviorSubject<void>(undefined);

  constructor() {
    combineLatest([this.route.queryParamMap, this.retry$])
      .pipe(
        map(([params]) => ({ filters: toAuditFilters(params), page: toPage(params) })),
        tap(({ filters, page }) => {
          this.viewState.set('loading');
          this.filters.set(filters);
          this.filtered.set(hasAuditFilters(filters));
          this.currentPage.set(page);
        }),
        switchMap(({ filters, page }) =>
          this.service.list(filters, page, PAGE_SIZE).pipe(
            map((data) => ({ data, error: null as ApiError | null })),
            catchError((error: unknown) => of({ data: null, error: toApiError(error) })),
          ),
        ),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe(({ data, error }) => {
        this.events.set(data);
        this.error.set(error);
        this.viewState.set(error ? 'error' : 'ready');
      });
  }

  protected rows(): AuditEvent[] {
    return this.events()?.results ?? [];
  }

  protected total(): number {
    return this.events()?.count ?? 0;
  }

  protected role(row: AuditEvent): string {
    return row.actor_role ? ROLE_LABELS[row.actor_role] : '—';
  }

  protected action(row: AuditEvent): string {
    return actionLabel(row.action);
  }

  protected resultText(row: AuditEvent): string {
    return resultLabel(row.result);
  }

  protected hash(row: AuditEvent): string {
    return shortHash(row.entry_hash);
  }

  protected reload(): void {
    this.retry$.next();
  }

  protected search(filters: AuditFilters): void {
    void this.router.navigate([], {
      relativeTo: this.route,
      queryParams: {
        date_from: filters.date_from ?? null,
        date_to: filters.date_to ?? null,
        action: filters.action ?? null,
        result: filters.result ?? null,
        actor: filters.actor ?? null,
        manuscript: filters.manuscript ?? null,
        page: null,
      },
    });
  }

  protected clear(): void {
    this.search({});
  }

  protected goToPage(page: number): void {
    void this.router.navigate([], {
      relativeTo: this.route,
      queryParams: { page: page > 1 ? page : null },
      queryParamsHandling: 'merge',
    });
  }
}
