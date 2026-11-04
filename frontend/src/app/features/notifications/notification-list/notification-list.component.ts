import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { BehaviorSubject, catchError, combineLatest, map, of, switchMap, tap } from 'rxjs';

import { toPage } from '../../../core/http/query-params';
import { ApiError, toApiError } from '../../../core/models/api-error.model';
import {
  DEFAULT_NOTICE_FILTER,
  NOTICE_FILTERS,
  Notice,
  NoticeFilter,
  NoticePage,
  toNoticeFilter,
} from '../../../core/models/notification.model';
import { NotificationService } from '../../../core/services/notification.service';
import { EmptyStateComponent } from '../../../shared/components/empty-state.component';
import { ErrorStateComponent } from '../../../shared/components/error-state.component';
import { LoadingSpinnerComponent } from '../../../shared/components/loading-spinner.component';
import { PaginationComponent } from '../../../shared/components/pagination.component';
import { NotificationItemComponent } from '../notification-item/notification-item.component';

/** Tamaño de página de la vista (la API admite hasta 100). */
export const PAGE_SIZE = 20;

/**
 * Avisos propios del usuario (plan sección 3.5, HU-18).
 *
 * * Lista solo los avisos del usuario autenticado, los más recientes
 *   primero; el filtro (Todos o No leídos) y la página viven en la URL
 *   (`filter`, `page`) y un valor manipulado se ignora.
 * * Marca uno o todos como leídos. El contador de la campana sale del
 *   `NotificationService` y cambia al instante, sin recargar la página.
 * * Un aviso marcado con el filtro «No leídos» sigue a la vista hasta la
 *   próxima lectura, para que la lista no se mueva bajo el puntero.
 * * Un error al marcar no cambia nada: el aviso sigue sin leer y se explica
 *   el motivo.
 */
@Component({
  selector: 'app-notification-list',
  imports: [
    RouterLink,
    NotificationItemComponent,
    PaginationComponent,
    LoadingSpinnerComponent,
    ErrorStateComponent,
    EmptyStateComponent,
  ],
  template: `
    <section aria-labelledby="notification-list-title">
      <header class="list-header">
        <h1 id="notification-list-title">Avisos</h1>
        <button
          type="button"
          class="btn btn--ghost"
          [disabled]="busyAll() || unreadCount() === 0"
          (click)="markAll()"
        >
          Marcar todos como leídos
        </button>
      </header>

      <p class="list-header__count" role="status">
        @if (unreadCount() > 0) {
          {{ unreadCount() }} {{ unreadCount() === 1 ? 'aviso sin leer' : 'avisos sin leer' }}
        } @else {
          No tiene avisos sin leer.
        }
      </p>

      <nav class="tabs" aria-label="Filtrar avisos">
        @for (option of filters; track option.value) {
          <a
            class="tabs__link"
            [routerLink]="[]"
            [queryParams]="filterParams(option.value)"
            [attr.aria-current]="filter() === option.value ? 'page' : null"
            >{{ option.label }}</a
          >
        }
      </nav>

      @if (actionError(); as message) {
        <p class="callout" role="alert">{{ message }}</p>
      }

      @switch (viewState()) {
        @case ('loading') {
          <app-loading-spinner label="Cargando avisos…" />
        }
        @case ('error') {
          <app-error-state [message]="error()?.userMessage ?? ''" (retry)="reload()" />
        }
        @default {
          @if (rows().length === 0) {
            <app-empty-state [message]="emptyMessage()" />
          } @else {
            <ul class="notices">
              @for (notice of rows(); track notice.id) {
                <li>
                  <app-notification-item
                    [notice]="notice"
                    [busy]="busyId() === notice.id"
                    (opened)="open($event)"
                    (markRead)="markOne($event)"
                  />
                </li>
              }
            </ul>
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
      gap: 0.5rem;
    }
    .list-header h1 {
      margin: 0;
    }
    .list-header__count {
      margin: 0.5rem 0;
      color: var(--gpc-text-muted);
    }
    .tabs {
      display: flex;
      gap: 0.5rem;
      margin: 0 0 1rem;
    }
    .tabs__link {
      padding: 0.375rem 0.75rem;
      border: 1px solid var(--gpc-border);
      border-radius: var(--gpc-radius);
      text-decoration: none;
    }
    .tabs__link[aria-current='page'] {
      background: var(--gpc-primary-700);
      border-color: var(--gpc-primary-700);
      color: #ffffff;
    }
    .callout {
      margin: 0 0 1rem;
      padding: 0.5rem 0.75rem;
      background: var(--gpc-danger-50, #fef2f2);
      border: 1px solid var(--gpc-danger-700);
      border-radius: var(--gpc-radius);
      color: var(--gpc-danger-700);
    }
    .notices {
      display: grid;
      gap: 0.75rem;
      margin: 0 0 1rem;
      padding: 0;
      list-style: none;
    }
  `,
})
export class NotificationListComponent {
  private readonly service = inject(NotificationService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);

  protected readonly filters = NOTICE_FILTERS;
  protected readonly pageSize = PAGE_SIZE;
  protected readonly unreadCount = this.service.unreadCount;

  protected readonly viewState = signal<'loading' | 'ready' | 'error'>('loading');
  protected readonly error = signal<ApiError | null>(null);
  protected readonly filter = signal<NoticeFilter>(DEFAULT_NOTICE_FILTER);
  protected readonly currentPage = signal(1);
  protected readonly result = signal<NoticePage | null>(null);
  protected readonly actionError = signal('');
  protected readonly busyId = signal<string | null>(null);
  protected readonly busyAll = signal(false);

  private readonly retry$ = new BehaviorSubject<void>(undefined);

  constructor() {
    combineLatest([this.route.queryParamMap, this.retry$])
      .pipe(
        map(([params]) => ({ filter: toNoticeFilter(params), page: toPage(params) })),
        tap(({ filter, page }) => {
          this.viewState.set('loading');
          this.actionError.set('');
          this.filter.set(filter);
          this.currentPage.set(page);
        }),
        switchMap(({ filter, page }) =>
          this.service.list(filter, page, PAGE_SIZE).pipe(
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

  protected rows(): Notice[] {
    return this.result()?.results ?? [];
  }

  protected total(): number {
    return this.result()?.count ?? 0;
  }

  protected emptyMessage(): string {
    return this.filter() === 'UNREAD' ? 'No tiene avisos sin leer.' : 'Todavía no tiene avisos.';
  }

  protected filterParams(value: NoticeFilter): Record<string, string | null> {
    return { filter: value === 'UNREAD' ? 'unread' : null, page: null };
  }

  protected goToPage(page: number): void {
    void this.router.navigate([], {
      relativeTo: this.route,
      queryParams: { page: page > 1 ? page : null },
      queryParamsHandling: 'merge',
    });
  }

  protected reload(): void {
    this.retry$.next();
  }

  /** Abrir el enlace de un aviso lo da por leído; si falla, la navegación sigue igual. */
  protected open(notice: Notice): void {
    if (!notice.is_read) {
      this.markOne(notice);
    }
  }

  protected markOne(notice: Notice): void {
    if (this.busyId() !== null) {
      return;
    }
    this.busyId.set(notice.id);
    this.actionError.set('');
    this.service.markRead(notice).subscribe({
      next: (updated) => {
        this.busyId.set(null);
        this.result.update((page) =>
          page
            ? { ...page, results: page.results.map((n) => (n.id === updated.id ? updated : n)) }
            : page,
        );
      },
      error: (error: ApiError) => {
        this.busyId.set(null);
        this.actionError.set(error.userMessage);
      },
    });
  }

  protected markAll(): void {
    if (this.busyAll()) {
      return;
    }
    this.busyAll.set(true);
    this.actionError.set('');
    this.service.markAllRead().subscribe({
      next: () => {
        this.busyAll.set(false);
        // Con «No leídos» la página queda vacía: se relee para mostrar el estado real.
        this.reload();
      },
      error: (error: ApiError) => {
        this.busyAll.set(false);
        this.actionError.set(error.userMessage);
      },
    });
  }
}
