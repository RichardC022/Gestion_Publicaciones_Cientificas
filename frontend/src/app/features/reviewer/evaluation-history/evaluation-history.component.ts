import { DatePipe } from '@angular/common';
import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { BehaviorSubject, catchError, combineLatest, map, of, switchMap, tap } from 'rxjs';

import { toPage } from '../../../core/http/query-params';
import { ApiError, toApiError } from '../../../core/models/api-error.model';
import { RECOMMENDATION_LABELS } from '../../../core/models/editor.model';
import { Paginated } from '../../../core/models/paginated.model';
import {
  MAX_SCORE,
  ReviewerHistoryDetail,
  ReviewerHistoryRow,
  SCORE_CRITERIA,
} from '../../../core/models/reviewer.model';
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

/** Estado de carga del detalle de una fila. */
type DetailState =
  | { kind: 'loading' }
  | { kind: 'ready'; detail: ReviewerHistoryDetail }
  | { kind: 'error'; message: string };

/**
 * Historial propio de evaluaciones del Revisor (plan sección 3.5, HU-17).
 *
 * * **Solo lectura:** lista únicamente las evaluaciones ya enviadas, de la
 *   más reciente a la más antigua, y no ofrece editar, reenviar ni borrar.
 * * **Anónimo:** identifica el manuscrito por código, título y área, y el
 *   resultado editorial es solo la decisión y su fecha. Nunca muestra
 *   autores, ni el texto que el Editor escribió para el Autor.
 * * **Sin comentarios confidenciales:** el detalle muestra los puntajes y
 *   los comentarios para el Autor; el tipo `ReviewerHistoryDetail` ni siquiera
 *   declara los confidenciales, así que no hay forma de pintarlos.
 * * La página vive en la URL (`page`); un valor manipulado se ignora. El
 *   detalle se pide al abrir cada fila y se conserva mientras la vista siga.
 */
@Component({
  selector: 'app-evaluation-history',
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
    <section aria-labelledby="evaluation-history-title">
      <header class="list-header">
        <h1 id="evaluation-history-title">Historial de evaluaciones</h1>
        <p class="list-header__count" role="status">
          @if (viewState() === 'ready') {
            {{ total() }} {{ total() === 1 ? 'evaluación enviada' : 'evaluaciones enviadas' }}
          }
        </p>
      </header>

      <p class="note" role="note">
        Aquí solo se muestran las evaluaciones que ya envió. Son de solo lectura y no incluyen
        información de los autores.
      </p>

      @switch (viewState()) {
        @case ('loading') {
          <app-loading-spinner label="Cargando su historial…" />
        }
        @case ('error') {
          <app-error-state [message]="error()?.userMessage ?? ''" (retry)="reload()" />
        }
        @default {
          @if (rows().length === 0) {
            <app-empty-state message="Todavía no ha enviado ninguna evaluación." />
          } @else {
            <div class="table-wrap">
              <table class="history">
                <caption class="visually-hidden">
                  Evaluaciones enviadas
                </caption>
                <thead>
                  <tr>
                    <th scope="col">Manuscrito</th>
                    <th scope="col">Título</th>
                    <th scope="col">Área</th>
                    <th scope="col">Versión</th>
                    <th scope="col">Su recomendación</th>
                    <th scope="col">Enviada</th>
                    <th scope="col">Resultado editorial</th>
                    <th scope="col"><span class="visually-hidden">Acciones</span></th>
                  </tr>
                </thead>
                <tbody>
                  @for (row of rows(); track row.id) {
                    <tr>
                      <td>{{ row.manuscript_code }}</td>
                      <td class="history__title">{{ row.manuscript_title || 'Sin título' }}</td>
                      <td>{{ row.area }}</td>
                      <td>
                        v{{ row.version_number }}
                        <span class="history__meta">Ronda {{ row.round_number }}</span>
                      </td>
                      <td>{{ recommendationLabel(row) }}</td>
                      <td>{{ row.submitted_at | date: 'dd/MM/yyyy HH:mm' : offset }}</td>
                      <td>
                        @if (row.editorial_result; as result) {
                          <app-status-badge [status]="result.decision" />
                          <span class="history__meta">{{
                            result.decided_at | date: 'dd/MM/yyyy' : offset
                          }}</span>
                        } @else {
                          <span class="history__meta">Pendiente de decisión</span>
                        }
                      </td>
                      <td>
                        <button
                          type="button"
                          class="btn btn--ghost"
                          [attr.aria-expanded]="openId() === row.id"
                          [attr.aria-controls]="'detail-' + row.id"
                          (click)="toggle(row)"
                        >
                          {{ openId() === row.id ? 'Ocultar' : 'Ver evaluación'
                          }}<span class="visually-hidden"> {{ row.manuscript_code }}</span>
                        </button>
                      </td>
                    </tr>
                    @if (openId() === row.id) {
                      <tr class="history__detail" [id]="'detail-' + row.id">
                        <td colspan="8">
                          @switch (stateOf(row.id)?.kind) {
                            @case ('ready') {
                              @if (detailOf(row.id); as detail) {
                                <h2 class="history__detail-title">
                                  Evaluación de {{ detail.manuscript_code }}
                                </h2>
                                <dl class="scores">
                                  @for (criterion of criteria; track criterion.field) {
                                    <div class="scores__row">
                                      <dt>{{ criterion.label }}</dt>
                                      <dd>{{ detail[criterion.field] }} / {{ maxScore }}</dd>
                                    </div>
                                  }
                                </dl>
                                <h3>Comentarios para el Autor</h3>
                                <p class="prose">{{ detail.comments_for_author }}</p>
                              }
                            }
                            @case ('error') {
                              <p class="history__error" role="alert">{{ errorOf(row.id) }}</p>
                              <button
                                type="button"
                                class="btn btn--ghost"
                                (click)="retryDetail(row)"
                              >
                                Reintentar
                              </button>
                            }
                            @default {
                              <app-loading-spinner label="Cargando la evaluación…" />
                            }
                          }
                        </td>
                      </tr>
                    }
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

      <p class="back">
        <a routerLink="/app/reviewer/assignments">← Volver a mis asignaciones</a>
      </p>
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
    .history {
      width: 100%;
      border-collapse: collapse;
      background: var(--gpc-surface-alt);
      border: 1px solid var(--gpc-border);
    }
    .history th,
    .history td {
      padding: 0.625rem 0.75rem;
      border-bottom: 1px solid var(--gpc-border);
      text-align: left;
      vertical-align: middle;
    }
    .history th {
      background: var(--gpc-primary-50);
      font-size: 0.8125rem;
      color: var(--gpc-primary-900);
    }
    .history__title {
      max-width: 20rem;
      overflow-wrap: anywhere;
    }
    .history__meta {
      display: block;
      font-size: 0.8125rem;
      color: var(--gpc-text-muted);
    }
    .history__detail td {
      background: var(--gpc-surface);
    }
    .history__detail-title {
      margin: 0 0 0.5rem;
      font-size: 1rem;
    }
    .history__detail h3 {
      margin: 0.75rem 0 0.25rem;
      font-size: 0.9375rem;
    }
    .history__error {
      margin: 0 0 0.5rem;
      color: var(--gpc-danger-700);
    }
    .scores {
      display: flex;
      flex-wrap: wrap;
      gap: 0.5rem 1.5rem;
      margin: 0;
    }
    .scores__row {
      display: flex;
      gap: 0.375rem;
    }
    .scores dt {
      font-weight: 600;
    }
    .scores dd {
      margin: 0;
    }
    .prose {
      margin: 0;
      white-space: pre-line;
      overflow-wrap: anywhere;
    }
    .back {
      margin-top: 1.5rem;
    }
  `,
})
export class EvaluationHistoryComponent {
  private readonly service = inject(ReviewerService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);

  protected readonly pageSize = PAGE_SIZE;
  protected readonly offset = INSTITUTIONAL_OFFSET;
  protected readonly criteria = SCORE_CRITERIA;
  protected readonly maxScore = MAX_SCORE;

  protected readonly viewState = signal<'loading' | 'ready' | 'error'>('loading');
  protected readonly result = signal<Paginated<ReviewerHistoryRow> | null>(null);
  protected readonly error = signal<ApiError | null>(null);
  protected readonly currentPage = signal(1);

  protected readonly openId = signal<string | null>(null);
  private readonly details = signal<Record<string, DetailState>>({});

  private readonly retry$ = new BehaviorSubject<void>(undefined);

  constructor() {
    combineLatest([this.route.queryParamMap, this.retry$])
      .pipe(
        map(([params]) => toPage(params)),
        tap((page) => {
          this.viewState.set('loading');
          this.currentPage.set(page);
          this.openId.set(null);
        }),
        switchMap((page) =>
          this.service.listHistory(page, PAGE_SIZE).pipe(
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

  protected rows(): ReviewerHistoryRow[] {
    return this.result()?.results ?? [];
  }

  protected total(): number {
    return this.result()?.count ?? 0;
  }

  protected recommendationLabel(row: ReviewerHistoryRow): string {
    return RECOMMENDATION_LABELS[row.recommendation] ?? row.recommendation;
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

  protected stateOf(id: string): DetailState | undefined {
    return this.details()[id];
  }

  protected detailOf(id: string): ReviewerHistoryDetail | null {
    const state = this.details()[id];
    return state?.kind === 'ready' ? state.detail : null;
  }

  protected errorOf(id: string): string {
    const state = this.details()[id];
    return state?.kind === 'error' ? state.message : '';
  }

  /** Abre o cierra una fila; el detalle se pide la primera vez y se conserva. */
  protected toggle(row: ReviewerHistoryRow): void {
    if (this.openId() === row.id) {
      this.openId.set(null);
      return;
    }
    this.openId.set(row.id);
    if (this.details()[row.id]?.kind !== 'ready') {
      this.loadDetail(row);
    }
  }

  protected retryDetail(row: ReviewerHistoryRow): void {
    this.loadDetail(row);
  }

  private loadDetail(row: ReviewerHistoryRow): void {
    this.setDetail(row.id, { kind: 'loading' });
    this.service.getHistoryEntry(row.id).subscribe({
      next: (detail) => this.setDetail(row.id, { kind: 'ready', detail }),
      error: (error: ApiError) =>
        this.setDetail(row.id, { kind: 'error', message: error.userMessage }),
    });
  }

  private setDetail(id: string, state: DetailState): void {
    this.details.update((current) => ({ ...current, [id]: state }));
  }
}
