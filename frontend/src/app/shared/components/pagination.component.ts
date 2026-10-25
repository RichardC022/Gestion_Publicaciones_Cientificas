import { Component, computed, input, output } from '@angular/core';

/**
 * Paginación de listados con botones Anterior/Siguiente (plan §3.5).
 * El estado vive en la URL: el contenedor actualiza los `queryParams`
 * al recibir `pageChange`.
 */
@Component({
  selector: 'app-pagination',
  template: `
    @if (totalPages() > 1) {
      <nav class="pagination" aria-label="Paginación de resultados">
        <button
          type="button"
          class="btn btn--ghost"
          [disabled]="isFirst()"
          (click)="goTo(page() - 1)"
        >
          Anterior
        </button>
        <span class="pagination__status" aria-live="polite">
          Página {{ page() }} de {{ totalPages() }} · {{ totalItems() }} elementos
        </span>
        <button
          type="button"
          class="btn btn--ghost"
          [disabled]="isLast()"
          (click)="goTo(page() + 1)"
        >
          Siguiente
        </button>
      </nav>
    }
  `,
  styles: `
    .pagination {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 0.75rem;
      padding: 0.75rem 0;
    }
    .pagination__status {
      color: var(--gpc-text-muted);
      font-variant-numeric: tabular-nums;
    }
  `,
})
export class PaginationComponent {
  /** Página actual (base 1). */
  readonly page = input.required<number>();

  /** Tamaño de página solicitado al backend (máximo 100). */
  readonly pageSize = input.required<number>();

  /** Total de elementos devuelto por el backend. */
  readonly totalItems = input.required<number>();

  /** Se dispara con la página destino (base 1). */
  readonly pageChange = output<number>();

  protected readonly totalPages = computed(() =>
    Math.max(1, Math.ceil(this.totalItems() / this.pageSize())),
  );

  protected readonly isFirst = computed(() => this.page() <= 1);

  protected readonly isLast = computed(() => this.page() >= this.totalPages());

  protected goTo(target: number): void {
    if (target >= 1 && target <= this.totalPages() && target !== this.page()) {
      this.pageChange.emit(target);
    }
  }
}
