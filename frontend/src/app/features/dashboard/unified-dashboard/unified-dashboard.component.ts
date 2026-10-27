import { Component, OnInit, computed, inject, signal } from '@angular/core';

import { DashboardService } from '../../../core/services/dashboard.service';
import { ApiError } from '../../../core/models/api-error.model';
import {
  DASHBOARD_SECTION_KEYS,
  DASHBOARD_SECTION_LABELS,
  DashboardResponse,
  DashboardSection,
  DashboardSectionKey,
} from '../../../core/models/dashboard.model';
import { Role } from '../../../core/models/role.model';
import { EmptyStateComponent } from '../../../shared/components/empty-state.component';
import { ErrorStateComponent } from '../../../shared/components/error-state.component';
import { LoadingSpinnerComponent } from '../../../shared/components/loading-spinner.component';
import { AuthorSummaryComponent } from '../author-summary/author-summary.component';
import { ReviewerSummaryComponent } from '../reviewer-summary/reviewer-summary.component';
import { EditorSummaryComponent } from '../editor-summary/editor-summary.component';
import { AdminSummaryComponent } from '../admin-summary/admin-summary.component';

/**
 * Panel unificado multirrol (plan sección 3.4).
 *
 * Consume UNA sola vez `DashboardService.getDashboard()` y renderiza
 * las secciones de todos los roles activos a la vez; jamás pide al
 * usuario elegir un rol ni muestra un selector en el encabezado.
 *
 * Cada sección escribe en su propia señal y el fallo de una NO
 * cancela las demás: la sección fallida muestra el aviso reintentable
 * del backend con un botón "Reintentar" que vuelve a llamar al panel
 * conservando las demás visibles.
 */
@Component({
  selector: 'app-unified-dashboard',
  imports: [
    EmptyStateComponent,
    ErrorStateComponent,
    LoadingSpinnerComponent,
    AuthorSummaryComponent,
    ReviewerSummaryComponent,
    EditorSummaryComponent,
    AdminSummaryComponent,
  ],
  template: `
    <section class="dashboard" aria-labelledby="dashboard-title">
      <h1 id="dashboard-title">Panel unificado</h1>

      @if (loading()) {
        <p role="status">Cargando su panel…</p>
      } @else if (globalError(); as failure) {
        <app-error-state
          [message]="failure.userMessage"
          retryLabel="Reintentar"
          (retry)="load()"
        />
      } @else if (hasNoRoles()) {
        <!-- Sin roles activos: mensaje explícito y sin módulos. -->
        <app-empty-state
          message="Sin roles habilitados. Solicite acceso a la administración institucional."
        />
      } @else {
        <div class="dashboard__grid">
          @for (key of sectionKeys; track key) {
            @if (section(key); as current) {
              <div class="dashboard__section" [attr.data-section]="key">
                @if (current.status === 'ok') {
                  <!-- La tarjeta resumen ya lleva el nombre del rol: no se repite aquí. -->
                  @switch (key) {
                    @case ('author') {
                      <app-author-summary [data]="current.data" />
                    }
                    @case ('reviewer') {
                      <app-reviewer-summary [data]="current.data" />
                    }
                    @case ('editor') {
                      <app-editor-summary [data]="current.data" />
                    }
                    @case ('admin') {
                      <app-admin-summary [data]="current.data" />
                    }
                  }
                } @else {
                  <!-- La sección falló, las demás siguen visibles. Sin tarjeta resumen,
                       este título es lo único que nombra el rol. -->
                  <h3 class="dashboard__section-title">{{ sectionLabels[key] }}</h3>
                  <app-error-state
                    [message]="current.message ?? 'No se pudo cargar esta sección.'"
                    retryLabel="Reintentar"
                    (retry)="retrySection(key)"
                  />
                }
              </div>
            }
          }
        </div>
        @if (sectionErrors().length > 0) {
          <p class="dashboard__errors" role="status">
            {{ sectionErrors().length }}
            {{ sectionErrors().length === 1 ? 'sección con problemas' : 'secciones con problemas' }}.
          </p>
        }
      }
    </section>
  `,
  styles: `
    .dashboard {
      display: flex;
      flex-direction: column;
      gap: 1.25rem;
    }
    .dashboard__grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(18rem, 1fr));
      gap: 1.25rem;
    }
    .dashboard__section {
      display: flex;
      flex-direction: column;
      gap: 0.5rem;
      padding: 1rem;
      background: var(--gpc-surface-alt);
      border: 1px solid var(--gpc-border);
      border-radius: var(--gpc-radius-lg);
    }
    .dashboard__section-title {
      margin: 0 0 0.25rem;
      font-size: 0.95rem;
    }
    .dashboard__errors {
      margin: 0;
      color: var(--gpc-warning-800);
      font-size: 0.875rem;
    }
    :host ::ng-deep .summary h3 {
      margin: 0 0 0.25rem;
      font-size: 0.95rem;
    }
    :host ::ng-deep .summary__hint {
      margin: 0 0 0.5rem;
      color: var(--gpc-text-muted);
      font-size: 0.85rem;
    }
    :host ::ng-deep .summary__data {
      margin: 0;
    }
    :host ::ng-deep .summary__row {
      display: flex;
      justify-content: space-between;
      gap: 0.75rem;
      padding: 0.25rem 0;
      border-bottom: 1px dashed var(--gpc-border);
      font-size: 0.9rem;
    }
    :host ::ng-deep .summary__row dt {
      color: var(--gpc-text-muted);
    }
    :host ::ng-deep .summary__row dd {
      margin: 0;
      font-weight: 600;
    }
    :host ::ng-deep .summary__empty {
      margin: 0;
      color: var(--gpc-text-muted);
      font-size: 0.875rem;
    }
  `,
})
export class UnifiedDashboardComponent implements OnInit {
  private readonly service = inject(DashboardService);

  /** Señales por sección (plan sección 3.8). */
  readonly authorSection = signal<DashboardSection | null>(null);
  readonly reviewerSection = signal<DashboardSection | null>(null);
  readonly editorSection = signal<DashboardSection | null>(null);
  readonly adminSection = signal<DashboardSection | null>(null);

  readonly roles = signal<Role[]>([]);
  readonly loading = signal(true);
  readonly globalError = signal<ApiError | null>(null);

  /** Mensajes de las secciones fallidas; vacío cuando todas están bien. */
  readonly sectionErrors = computed(() =>
    DASHBOARD_SECTION_KEYS.filter((key) => this.section(key)?.status === 'error')
      .map((key) => this.section(key)?.message ?? key),
  );

  protected readonly hasNoRoles = computed(() => this.roles().length === 0);
  protected readonly sectionKeys = DASHBOARD_SECTION_KEYS;
  protected readonly sectionLabels = DASHBOARD_SECTION_LABELS;

  ngOnInit(): void {
    this.load();
  }

  /** Una sola llamada por carga: todas las secciones de una vez. */
  protected load(): void {
    this.loading.set(true);
    this.globalError.set(null);

    this.service.getDashboard().subscribe({
      next: (response: DashboardResponse) => {
        this.apply(response);
        this.loading.set(false);
      },
      error: (error: ApiError) => {
        this.globalError.set(error);
        this.loading.set(false);
      },
    });
  }

  /**
   * "Reintentar" de una sección fallida: vuelve a llamar al panel
   * (única fuente) conservando visibles las secciones sanas mientras
   * llega la respuesta nueva.
   */
  protected retrySection(_key: DashboardSectionKey): void {
    this.load();
  }

  protected section(key: DashboardSectionKey): DashboardSection | null {
    switch (key) {
      case 'author':
        return this.authorSection();
      case 'reviewer':
        return this.reviewerSection();
      case 'editor':
        return this.editorSection();
      case 'admin':
        return this.adminSection();
    }
  }

  private apply(response: DashboardResponse): void {
    this.roles.set(response.roles);
    this.authorSection.set(response.sections.author ?? null);
    this.reviewerSection.set(response.sections.reviewer ?? null);
    this.editorSection.set(response.sections.editor ?? null);
    this.adminSection.set(response.sections.admin ?? null);
  }
}
