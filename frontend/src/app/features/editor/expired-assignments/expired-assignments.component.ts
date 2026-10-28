import { DatePipe } from '@angular/common';
import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { BehaviorSubject, catchError, combineLatest, map, of, switchMap, tap } from 'rxjs';

import { toPage } from '../../../core/http/query-params';
import { ApiError, toApiError } from '../../../core/models/api-error.model';
import { Assignment } from '../../../core/models/editor.model';
import { Paginated } from '../../../core/models/paginated.model';
import { EditorService } from '../../../core/services/editor.service';
import { EmptyStateComponent } from '../../../shared/components/empty-state.component';
import { ErrorStateComponent } from '../../../shared/components/error-state.component';
import { LoadingSpinnerComponent } from '../../../shared/components/loading-spinner.component';
import { PaginationComponent } from '../../../shared/components/pagination.component';
import { StatusBadgeComponent } from '../../../shared/components/status-badge.component';
import {
  RevocationRequest,
  RevokeAssignmentDialogComponent,
} from '../revoke-assignment-dialog/revoke-assignment-dialog.component';

export { toPage };

/** Tamaño de página de la vista (la API admite hasta 100). */
export const PAGE_SIZE = 20;

/** Fechas y horas se muestran en la zona institucional (UTC-5, sin horario de verano). */
const INSTITUTIONAL_OFFSET = '-0500';

/**
 * Asignaciones vencidas pendientes de decisión (plan sección 3.5, HU-12).
 *
 * * Lista las asignaciones con `due_at <= now()` según el reloj del
 *   servidor: las ya marcadas `EXPIRED` y las `ACTIVE` que la tarea
 *   programada todavía no marcó. El navegador no calcula el vencimiento.
 * * **Nada se revoca ni se reasigna solo.** La decisión es del Editor: puede
 *   revocar desde aquí (con causa y motivo) o abrir el envío para decidir.
 *   Tras revocar, la reasignación se hace a mano desde el envío.
 * * La página vive en la URL (`page`); un valor manipulado se ignora.
 */
@Component({
  selector: 'app-expired-assignments',
  imports: [
    DatePipe,
    RouterLink,
    StatusBadgeComponent,
    PaginationComponent,
    LoadingSpinnerComponent,
    ErrorStateComponent,
    EmptyStateComponent,
    RevokeAssignmentDialogComponent,
  ],
  template: `
    <section aria-labelledby="expired-assignments-title">
      <header class="list-header">
        <h1 id="expired-assignments-title">Asignaciones vencidas</h1>
        <p class="list-header__count" role="status">
          @if (viewState() === 'ready') {
            {{ total() }} {{ total() === 1 ? 'pendiente de decisión' : 'pendientes de decisión' }}
          }
        </p>
      </header>

      <p class="note" role="note">
        Estas asignaciones superaron su fecha límite. Ninguna se revoca ni se reasigna sola: usted
        decide qué hacer con cada una.
      </p>

      @if (notice(); as done) {
        <p class="callout callout--success" role="status">
          {{ done.message }}
          <a [routerLink]="['/app/editor/submissions', done.manuscriptId]"
            >Abrir {{ done.manuscriptCode }} para asignar a otro Revisor</a
          >.
        </p>
      }

      @switch (viewState()) {
        @case ('loading') {
          <app-loading-spinner label="Cargando asignaciones vencidas…" />
        }
        @case ('error') {
          <app-error-state [message]="error()?.userMessage ?? ''" (retry)="reload()" />
        }
        @default {
          @if (rows().length === 0) {
            <app-empty-state message="No hay asignaciones vencidas pendientes de decisión." />
          } @else {
            <div class="table-wrap">
              <table class="expired">
                <caption class="visually-hidden">
                  Asignaciones vencidas pendientes de decisión
                </caption>
                <thead>
                  <tr>
                    <th scope="col">Envío</th>
                    <th scope="col">Título</th>
                    <th scope="col">Revisor</th>
                    <th scope="col">Fecha límite</th>
                    <th scope="col">Estado</th>
                    <th scope="col"><span class="visually-hidden">Acciones</span></th>
                  </tr>
                </thead>
                <tbody>
                  @for (row of rows(); track row.id) {
                    <tr>
                      <td>
                        <a [routerLink]="['/app/editor/submissions', row.manuscript]">{{
                          row.manuscript_code
                        }}</a>
                      </td>
                      <td class="expired__title">{{ row.manuscript_title || 'Sin título' }}</td>
                      <td>
                        {{ row.reviewer.full_name }}
                        <span class="expired__meta">{{ row.reviewer.email }}</span>
                      </td>
                      <td>{{ row.due_at | date: 'dd/MM/yyyy HH:mm' : offset }}</td>
                      <td>
                        <app-status-badge status="EXPIRED" />
                        @if (row.status === 'ACTIVE') {
                          <span class="expired__meta">por marcar</span>
                        }
                      </td>
                      <td class="expired__actions">
                        <a [routerLink]="['/app/editor/submissions', row.manuscript]"
                          >Ver envío<span class="visually-hidden"> {{ row.manuscript_code }}</span></a
                        >
                        <button
                          type="button"
                          class="btn btn--danger"
                          [attr.aria-label]="'Revocar la asignación de ' + row.manuscript_code"
                          (click)="startRevoke(row)"
                        >
                          Revocar
                        </button>
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

      <app-revoke-assignment-dialog
        [open]="revokeTarget() !== null"
        [assignment]="revokeTarget()"
        [busy]="revoking()"
        [error]="revokeError()"
        (confirmed)="confirmRevoke($event)"
        (cancelled)="closeRevoke()"
      />
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
    .note {
      margin: 0.75rem 0 1rem;
      padding: 0.625rem 0.875rem;
      background: var(--gpc-primary-50);
      border: 1px solid var(--gpc-primary-700);
      border-radius: var(--gpc-radius);
    }
    .table-wrap {
      overflow-x: auto;
    }
    .expired {
      width: 100%;
      border-collapse: collapse;
      background: var(--gpc-surface-alt);
      border: 1px solid var(--gpc-border);
    }
    .expired th,
    .expired td {
      padding: 0.625rem 0.75rem;
      border-bottom: 1px solid var(--gpc-border);
      text-align: left;
      vertical-align: middle;
    }
    .expired th {
      background: var(--gpc-primary-50);
      font-size: 0.8125rem;
      color: var(--gpc-primary-900);
    }
    .expired__title {
      max-width: 20rem;
      overflow-wrap: anywhere;
    }
    .expired__meta {
      display: block;
      font-size: 0.8125rem;
      color: var(--gpc-text-muted);
    }
    .expired__actions {
      display: flex;
      align-items: center;
      gap: 0.75rem;
      white-space: nowrap;
    }
  `,
})
export class ExpiredAssignmentsComponent {
  private readonly service = inject(EditorService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);

  protected readonly pageSize = PAGE_SIZE;
  protected readonly offset = INSTITUTIONAL_OFFSET;

  protected readonly viewState = signal<'loading' | 'ready' | 'error'>('loading');
  protected readonly result = signal<Paginated<Assignment> | null>(null);
  protected readonly error = signal<ApiError | null>(null);
  protected readonly currentPage = signal(1);

  protected readonly revokeTarget = signal<Assignment | null>(null);
  protected readonly revoking = signal(false);
  protected readonly revokeError = signal('');
  protected readonly notice = signal<{
    message: string;
    manuscriptId: string;
    manuscriptCode: string;
  } | null>(null);

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
          this.service.listExpiredAssignments(page, PAGE_SIZE).pipe(
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

  protected rows(): Assignment[] {
    return this.result()?.results ?? [];
  }

  protected total(): number {
    return this.result()?.count ?? 0;
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

  protected startRevoke(assignment: Assignment): void {
    this.revokeError.set('');
    this.notice.set(null);
    this.revokeTarget.set(assignment);
  }

  protected closeRevoke(): void {
    this.revokeTarget.set(null);
    this.revokeError.set('');
  }

  protected confirmRevoke(request: RevocationRequest): void {
    const target = this.revokeTarget();
    if (target === null || this.revoking()) {
      return;
    }
    this.revoking.set(true);
    this.revokeError.set('');
    this.service.revokeAssignment(target.id, request.cause, request.reason).subscribe({
      next: () => {
        this.revoking.set(false);
        this.revokeTarget.set(null);
        this.notice.set({
          message: 'Asignación revocada. El envío espera un nuevo Revisor.',
          manuscriptId: target.manuscript,
          manuscriptCode: target.manuscript_code,
        });
        this.reload();
      },
      error: (error: ApiError) => {
        this.revoking.set(false);
        this.revokeError.set(error.userMessage);
        // Si otro Editor actuó antes (409), la lista se vuelve a leer.
        this.reload();
      },
    });
  }
}
