import { DatePipe } from '@angular/common';
import { Component, computed, inject, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';

import { ApiError } from '../../../core/models/api-error.model';
import { ReviewerAssignmentDetail } from '../../../core/models/reviewer.model';
import { ReviewerDocument, ReviewerService } from '../../../core/services/reviewer.service';
import { ErrorStateComponent } from '../../../shared/components/error-state.component';
import { LoadingSpinnerComponent } from '../../../shared/components/loading-spinner.component';
import { PdfViewerComponent } from '../../../shared/components/pdf-viewer.component';
import { RoundCounterComponent } from '../../../shared/components/round-counter.component';
import { StatusBadgeComponent } from '../../../shared/components/status-badge.component';
import { saveBlob } from '../../../shared/utils/save-blob';
import { DeadlineCountdownComponent } from '../deadline-countdown/deadline-countdown.component';
import { IdentityLeakDialogComponent } from '../identity-leak-dialog/identity-leak-dialog.component';

/** Fechas y horas se muestran en la zona institucional (UTC-5, sin horario de verano). */
const INSTITUTIONAL_OFFSET = '-0500';

/**
 * Detalle anonimizado de una asignación (plan sección 3.5, HU-14 y HU-16).
 *
 * * Muestra código, título, resumen, palabras clave, área, idioma, ronda,
 *   versión, plazo y el PDF sanitizado.
 * * **Doble ciego:** no renderiza autores, filiaciones, contacto, nombre
 *   original del archivo ni enlace alguno al PDF original. El tipo
 *   `ReviewerAssignmentDetail` no los declara, y el único documento que se
 *   pide es el del endpoint sanitizado de la propia asignación.
 * * El PDF no se pide al abrir el detalle: cada lectura queda auditada, así
 *   que solo se descarga cuando el Revisor lo solicita, y se conserva en
 *   memoria mientras la vista siga abierta. Se guarda con un nombre
 *   genérico derivado del código del manuscrito.
 * * El contador cuenta contra la fecha límite del backend. Al vencer se
 *   deshabilita el acceso a la evaluación; el corte definitivo lo aplica
 *   el servidor al recibir el envío.
 */
@Component({
  selector: 'app-assignment-detail',
  imports: [
    DatePipe,
    RouterLink,
    LoadingSpinnerComponent,
    ErrorStateComponent,
    StatusBadgeComponent,
    RoundCounterComponent,
    PdfViewerComponent,
    DeadlineCountdownComponent,
    IdentityLeakDialogComponent,
  ],
  template: `
    <section aria-labelledby="assignment-detail-title">
      <nav aria-label="Navegación de la asignación">
        <a routerLink="/app/reviewer/assignments">← Volver a mis asignaciones</a>
      </nav>

      @if (loading()) {
        <app-loading-spinner label="Cargando la asignación…" />
      } @else if (error()) {
        <app-error-state [message]="error()?.userMessage ?? ''" (retry)="load()" />
      } @else if (assignment(); as a) {
        <header class="detail-header">
          <div>
            <p class="detail-code">{{ a.manuscript.code }}</p>
            <h1 id="assignment-detail-title">{{ a.manuscript.title || 'Sin título' }}</h1>
          </div>
          <div class="detail-badges">
            <app-status-badge [status]="a.state" />
            <app-round-counter [round]="a.round_number" />
            <span class="badge badge--neutral">Versión v{{ a.version_number }}</span>
          </div>
        </header>

        <p class="callout callout--info" role="note">
          Revisión a doble ciego: no se muestra información de los autores.
        </p>

        @if (a.status === 'ACTIVE') {
          <app-deadline-countdown
            [dueAt]="a.due_at"
            [serverOffsetMs]="serverOffsetMs()"
            [overdue]="a.is_overdue"
            (expired)="deadlinePassed.set(true)"
          />
        } @else if (a.completed_at) {
          <p class="callout callout--success" role="status">
            Evaluación enviada el {{ a.completed_at | date: 'dd/MM/yyyy HH:mm' : offset }}.
          </p>
        }

        <section class="card" aria-labelledby="manuscript-title">
          <h2 id="manuscript-title">Manuscrito</h2>
          <dl class="data">
            <dt>Área</dt>
            <dd>{{ a.manuscript.area }}</dd>
            <dt>Idioma</dt>
            <dd>{{ a.manuscript.language }}</dd>
            <dt>Ronda</dt>
            <dd>{{ a.version.round_number }}</dd>
            <dt>Versión</dt>
            <dd>
              v{{ a.version.version_number }}, enviada el
              {{ a.version.submitted_at | date: 'dd/MM/yyyy HH:mm' : offset }}
            </dd>
            <dt>Asignada el</dt>
            <dd>{{ a.assigned_at | date: 'dd/MM/yyyy HH:mm' : offset }}</dd>
            <dt>Palabras clave</dt>
            <dd>{{ a.manuscript.keywords.join(', ') || '—' }}</dd>
          </dl>
          <h3>Resumen</h3>
          <p class="prose">{{ a.manuscript.abstract }}</p>
        </section>

        <section class="card" aria-labelledby="document-title">
          <h2 id="document-title">Documento</h2>
          @if (a.document_url) {
            <p>PDF sanitizado, sin datos de autoría.</p>
            @if (documentError()) {
              <p class="document-error" role="alert">{{ documentError() }}</p>
            }
            <div class="actions">
              <button
                type="button"
                class="btn btn--primary"
                [disabled]="fetching()"
                (click)="toggleViewer(a)"
              >
                {{ fetching() ? 'Cargando…' : shown() ? 'Ocultar documento' : 'Ver documento' }}
              </button>
              <button
                type="button"
                class="btn btn--ghost"
                [disabled]="fetching()"
                (click)="download(a)"
              >
                Descargar PDF
              </button>
            </div>
            @if (document(); as doc) {
              <app-pdf-viewer
                [blob]="doc.blob"
                [filename]="doc.filename"
                frameTitle="Manuscrito sanitizado para revisión"
              />
            }
          } @else {
            <p class="callout callout--neutral" role="status">
              El documento ya no está disponible para esta asignación.
            </p>
          }
        </section>

        <div class="actions">
          @if (a.status === 'ACTIVE') {
            @if (blocked()) {
              <button
                type="button"
                class="btn btn--primary"
                disabled
                aria-describedby="blocked-note"
              >
                Evaluar manuscrito
              </button>
              <p id="blocked-note" class="document-error" role="status">
                El plazo venció: ya no puede enviar la evaluación.
              </p>
            } @else {
              <a
                class="btn btn--primary"
                [routerLink]="['/app/reviewer/assignments', a.id, 'evaluate']"
              >
                Evaluar manuscrito
              </a>
            }
          } @else {
            <a class="btn btn--ghost" routerLink="/app/reviewer/history">Ver mi historial</a>
          }
          @if (a.status === 'ACTIVE') {
            <button type="button" class="btn btn--ghost" (click)="leakOpen.set(true)">
              Reportar posible fuga de identidad
            </button>
          }
        </div>

        @if (leakNotice()) {
          <p class="callout callout--success" role="status">{{ leakNotice() }}</p>
        }

        <app-identity-leak-dialog
          [assignmentId]="a.id"
          [open]="leakOpen()"
          (reported)="onLeakReported()"
          (cancelled)="leakOpen.set(false)"
        />
      }
    </section>
  `,
  styles: `
    .detail-header {
      display: flex;
      flex-wrap: wrap;
      align-items: flex-start;
      justify-content: space-between;
      gap: 0.75rem;
      margin: 1rem 0;
    }
    .detail-code {
      margin: 0;
      font-weight: 700;
      color: var(--gpc-primary-700);
    }
    .detail-header h1 {
      margin: 0.25rem 0 0;
      overflow-wrap: anywhere;
    }
    .detail-badges {
      display: flex;
      flex-wrap: wrap;
      gap: 0.5rem;
    }
    .callout {
      margin: 1rem 0;
      padding: 0.75rem 1rem;
      border: 1px solid;
      border-radius: var(--gpc-radius);
    }
    .callout--info {
      background: var(--gpc-primary-50);
      border-color: var(--gpc-primary-700);
    }
    .callout--success {
      background: var(--gpc-success-100);
      border-color: var(--gpc-success-700);
      color: var(--gpc-success-700);
    }
    .callout--neutral {
      background: var(--gpc-surface);
      border-color: var(--gpc-border);
    }
    .card {
      margin: 1rem 0;
      padding: 1rem 1.25rem;
      background: var(--gpc-surface-alt);
      border: 1px solid var(--gpc-border);
      border-radius: var(--gpc-radius);
    }
    .card h2 {
      margin-top: 0;
      font-size: 1.125rem;
    }
    .card h3 {
      font-size: 1rem;
    }
    .data {
      display: grid;
      grid-template-columns: max-content 1fr;
      gap: 0.375rem 1rem;
      margin: 0;
    }
    .data dt {
      font-weight: 600;
    }
    .data dd {
      margin: 0;
    }
    .prose {
      white-space: pre-line;
      overflow-wrap: anywhere;
    }
    .actions {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 0.75rem;
      margin: 1rem 0;
    }
    .document-error {
      margin: 0;
      color: var(--gpc-danger-700);
    }
  `,
})
export class AssignmentDetailComponent {
  private readonly service = inject(ReviewerService);
  private readonly route = inject(ActivatedRoute);

  protected readonly offset = INSTITUTIONAL_OFFSET;
  private readonly id = this.route.snapshot.paramMap.get('id') ?? '';

  protected readonly loading = signal(true);
  protected readonly error = signal<ApiError | null>(null);
  protected readonly assignment = signal<ReviewerAssignmentDetail | null>(null);
  protected readonly serverOffsetMs = signal(0);

  /** El contador llegó a cero mientras la vista estaba abierta. */
  protected readonly deadlinePassed = signal(false);

  /** Sin plazo no hay evaluación: lo dice el servidor al cargar o lo dice el contador al vencer. */
  protected readonly blocked = computed(
    () => this.deadlinePassed() || this.assignment()?.is_overdue === true,
  );

  /** PDF sanitizado ya descargado; se conserva para no auditar cada vista. */
  private readonly fetched = signal<ReviewerDocument | null>(null);
  protected readonly shown = signal(false);
  protected readonly fetching = signal(false);
  protected readonly documentError = signal('');

  /** El documento que se renderiza en el visor. */
  protected readonly document = computed(() => (this.shown() ? this.fetched() : null));

  protected readonly leakOpen = signal(false);
  protected readonly leakNotice = signal('');

  constructor() {
    this.load();
  }

  protected onLeakReported(): void {
    this.leakOpen.set(false);
    this.leakNotice.set(
      'Reporte confidencial enviado. Solo el Editor lo verá y su evaluación no cambió.',
    );
  }

  protected load(): void {
    this.loading.set(true);
    this.fetchAssignment();
  }

  /** Muestra u oculta el visor; la primera vez descarga el PDF sanitizado. */
  protected toggleViewer(assignment: ReviewerAssignmentDetail): void {
    if (this.shown()) {
      this.shown.set(false);
      return;
    }
    this.withDocument(assignment, () => this.shown.set(true));
  }

  protected download(assignment: ReviewerAssignmentDetail): void {
    this.withDocument(assignment, (doc) => saveBlob(doc.blob, doc.filename));
  }

  private fetchAssignment(): void {
    this.error.set(null);
    this.service.getAssignment(this.id).subscribe({
      next: ({ assignment, serverOffsetMs }) => {
        this.assignment.set(assignment);
        this.serverOffsetMs.set(serverOffsetMs);
        this.loading.set(false);
      },
      error: (error: ApiError) => {
        this.error.set(error);
        this.loading.set(false);
      },
    });
  }

  private withDocument(
    assignment: ReviewerAssignmentDetail,
    done: (document: ReviewerDocument) => void,
  ): void {
    const cached = this.fetched();
    if (cached !== null) {
      done(cached);
      return;
    }
    if (this.fetching()) {
      return;
    }
    this.fetching.set(true);
    this.documentError.set('');
    this.service
      .downloadDocument(
        assignment.id,
        assignment.manuscript.code,
        assignment.version.version_number,
      )
      .subscribe({
        next: (doc) => {
          this.fetching.set(false);
          this.fetched.set(doc);
          done(doc);
        },
        error: (error: ApiError) => {
          this.fetching.set(false);
          this.documentError.set(error.userMessage);
          // Con 410 la asignación cambió de estado: se vuelve a leer sin parpadeo.
          if (error.status === 410) {
            this.fetchAssignment();
          }
        },
      });
  }
}
