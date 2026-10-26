import { DatePipe } from '@angular/common';
import { Component, computed, inject, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';

import { ApiError } from '../../../core/models/api-error.model';
import {
  DraftFileSummary,
  Manuscript,
  isEditable,
  nextAction,
} from '../../../core/models/manuscript.model';
import { ManuscriptService } from '../../../core/services/manuscript.service';
import { ErrorStateComponent } from '../../../shared/components/error-state.component';
import { LoadingSpinnerComponent } from '../../../shared/components/loading-spinner.component';
import { RoundCounterComponent } from '../../../shared/components/round-counter.component';
import { StatusBadgeComponent } from '../../../shared/components/status-badge.component';
import { FileSizePipe } from '../../../shared/pipes/file-size.pipe';
import { PdfUploaderComponent } from '../pdf-uploader/pdf-uploader.component';
import { WithdrawDialogComponent } from '../withdraw-dialog/withdraw-dialog.component';

/** Fechas y horas se muestran en la zona institucional (UTC-5, sin horario de verano). */
const INSTITUTIONAL_OFFSET = '-0500';

/**
 * Detalle de un manuscrito propio (plan sección 3.5, HU-06/HU-22).
 *
 * * Metadatos, autores, estado, versión, ronda y la **siguiente acción**.
 * * Observaciones y veredicto cuando existen: la vista solo lee
 *   `comments_for_author`, `decision` y `observations`
 *   (`AuthorEvaluationFeedbackSerializer`). Nunca muestra la identidad
 *   del Revisor, comentarios confidenciales ni puntuaciones, aunque
 *   la respuesta los trajera por error.
 * * La acción de editar solo aparece en `DRAFT` o `REQUIRES_CORRECTIONS`
 *   y si el manuscrito no está dado de baja.
 * * Un manuscrito dado de baja se muestra archivado y en solo lectura.
 *
 * El PDF de borrador se adjunta con el cargador (TSK-42); envío, nueva
 * versión y baja se agregan en las TSK-43 y TSK-44 sobre esta misma vista.
 */
@Component({
  selector: 'app-manuscript-detail',
  imports: [
    DatePipe,
    RouterLink,
    LoadingSpinnerComponent,
    ErrorStateComponent,
    StatusBadgeComponent,
    RoundCounterComponent,
    FileSizePipe,
    PdfUploaderComponent,
    WithdrawDialogComponent,
  ],
  template: `
    <section aria-labelledby="manuscript-detail-title">
      <nav aria-label="Navegación del manuscrito">
        <a routerLink="/app/author/manuscripts">← Volver a mis manuscritos</a>
      </nav>

      @if (loading()) {
        <app-loading-spinner label="Cargando manuscrito…" />
      } @else if (error()) {
        <app-error-state [message]="error()?.userMessage ?? ''" (retry)="load()" />
      } @else if (manuscript(); as m) {
        <header class="detail-header">
          <div>
            <p class="detail-code">{{ m.code }}</p>
            <h1 id="manuscript-detail-title">{{ m.title || 'Sin título' }}</h1>
          </div>
          <div class="detail-badges">
            <app-status-badge [status]="m.status" />
            @if (!m.is_active) {
              <app-status-badge status="WITHDRAWN" />
            }
            <app-round-counter [round]="m.current_round" />
            <span class="badge badge--neutral">
              {{ m.current_version > 0 ? 'Versión v' + m.current_version : 'Sin versión formal' }}
            </span>
          </div>
        </header>

        @if (!m.is_active) {
          <div class="callout callout--neutral" role="status">
            <p>
              <strong>Dado de baja</strong>
              @if (m.withdrawn_at) {
                el {{ m.withdrawn_at | date: 'dd/MM/yyyy HH:mm' : offset }}.
              }
              Se conserva en solo lectura con todo su historial.
            </p>
            @if (m.withdrawal_reason) {
              <p>Motivo: {{ m.withdrawal_reason }}</p>
            }
          </div>
        }

        <div class="callout callout--info" role="status" aria-labelledby="next-action-title">
          <h2 id="next-action-title">Siguiente acción</h2>
          <p>{{ action().detail }}</p>
        </div>

        @if (m.feedback; as feedback) {
          <section class="card" aria-labelledby="feedback-title">
            <h2 id="feedback-title">Resultado de la evaluación</h2>
            <p>Veredicto: <app-status-badge [status]="feedback.decision" /></p>
            @if (feedback.observations) {
              <h3>Observaciones del Editor</h3>
              <p class="prose">{{ feedback.observations }}</p>
            }
            @if (feedback.comments_for_author) {
              <h3>Comentarios para el autor</h3>
              <p class="prose">{{ feedback.comments_for_author }}</p>
            }
          </section>
        }

        @if (notice(); as message) {
          <p class="callout callout--success" role="status">{{ message }}</p>
        }

        <div class="actions">
          @if (editable()) {
            <a class="btn btn--primary" [routerLink]="['/app/author/manuscripts', m.id, 'edit']">
              Editar manuscrito
            </a>
          }
          <a class="btn btn--ghost" [routerLink]="['/app/author/manuscripts', m.id, 'history']">
            Historial de versiones
          </a>
          @if (m.is_active) {
            <button type="button" class="btn btn--danger" (click)="openWithdraw()">
              Dar de baja
            </button>
          }
        </div>

        <app-withdraw-dialog
          [open]="withdrawOpen()"
          [status]="m.status"
          [manuscriptCode]="m.code"
          [busy]="withdrawing()"
          [error]="withdrawError()"
          (confirmed)="confirmWithdraw($event)"
          (cancelled)="cancelWithdraw()"
        />

        <section class="card" aria-labelledby="metadata-title">
          <h2 id="metadata-title">Datos generales</h2>
          <dl class="data">
            <dt>Área de conocimiento</dt>
            <dd>{{ m.area || '—' }}</dd>
            <dt>Idioma</dt>
            <dd>{{ m.language || '—' }}</dd>
            <dt>Palabras clave</dt>
            <dd>{{ m.keywords.length > 0 ? m.keywords.join(', ') : '—' }}</dd>
            <dt>Registrado</dt>
            <dd>{{ m.created_at | date: 'dd/MM/yyyy HH:mm' : offset }}</dd>
            <dt>Última actualización</dt>
            <dd>{{ m.updated_at | date: 'dd/MM/yyyy HH:mm' : offset }}</dd>
          </dl>
          <h3>Resumen</h3>
          <p class="prose">{{ m.abstract || 'Sin resumen.' }}</p>
        </section>

        <section class="card" aria-labelledby="authors-title">
          <h2 id="authors-title">Autores</h2>
          <table class="authors">
            <caption class="visually-hidden">
              Autores del manuscrito
            </caption>
            <thead>
              <tr>
                <th scope="col">#</th>
                <th scope="col">Nombre</th>
                <th scope="col">Correo</th>
                <th scope="col">Filiación</th>
              </tr>
            </thead>
            <tbody>
              @for (author of m.authors; track author.email; let i = $index) {
                <tr>
                  <td>{{ author.author_order ?? i + 1 }}</td>
                  <td>
                    {{ author.full_name }}
                    @if (author.is_corresponding) {
                      <span class="badge badge--info">Responsable</span>
                    }
                  </td>
                  <td>{{ author.email }}</td>
                  <td>{{ author.affiliation }}</td>
                </tr>
              }
            </tbody>
          </table>
        </section>

        @if (canUpload()) {
          <app-pdf-uploader
            [manuscriptId]="m.id"
            [current]="m.draft_file"
            (uploaded)="onDraftUploaded($event)"
          />
        } @else if (m.draft_file; as draft) {
          <section class="card" aria-labelledby="draft-title">
            <h2 id="draft-title">PDF de borrador</h2>
            <p>
              {{ draft.filename }} · {{ draft.size_bytes | fileSize }} · adjuntado el
              {{ draft.uploaded_at | date: 'dd/MM/yyyy HH:mm' : offset }}
            </p>
          </section>
        }
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
    .callout h2,
    .callout p {
      margin: 0 0 0.25rem;
    }
    .callout h2 {
      font-size: 1rem;
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
    .actions {
      display: flex;
      flex-wrap: wrap;
      gap: 0.75rem;
      margin: 1rem 0;
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
    .authors {
      width: 100%;
      border-collapse: collapse;
    }
    .authors th,
    .authors td {
      padding: 0.5rem 0.625rem;
      border-bottom: 1px solid var(--gpc-border);
      text-align: left;
    }
  `,
})
export class ManuscriptDetailComponent {
  private readonly service = inject(ManuscriptService);
  private readonly route = inject(ActivatedRoute);

  protected readonly offset = INSTITUTIONAL_OFFSET;
  private readonly id = this.route.snapshot.paramMap.get('id') ?? '';

  protected readonly loading = signal(true);
  protected readonly error = signal<ApiError | null>(null);
  protected readonly manuscript = signal<Manuscript | null>(null);

  protected readonly withdrawOpen = signal(false);
  protected readonly withdrawing = signal(false);
  protected readonly withdrawError = signal('');
  protected readonly notice = signal('');

  protected readonly editable = computed(() => {
    const manuscript = this.manuscript();
    return manuscript !== null && isEditable(manuscript);
  });

  /**
   * El PDF de borrador solo se adjunta o reemplaza mientras el manuscrito
   * es un borrador activo; en correcciones la carga es la de una nueva
   * versión (TSK-44).
   */
  protected readonly canUpload = computed(() => {
    const manuscript = this.manuscript();
    return manuscript !== null && manuscript.is_active && manuscript.status === 'DRAFT';
  });

  protected readonly action = computed(() => {
    const manuscript = this.manuscript();
    return manuscript ? nextAction(manuscript) : { short: '', detail: '' };
  });

  constructor() {
    this.load();
  }

  protected openWithdraw(): void {
    this.withdrawError.set('');
    this.notice.set('');
    this.withdrawOpen.set(true);
  }

  protected cancelWithdraw(): void {
    this.withdrawOpen.set(false);
    this.withdrawError.set('');
  }

  /** Baja lógica: el servidor marca el manuscrito y conserva todo su historial. */
  protected confirmWithdraw(reason: string | null): void {
    if (this.withdrawing()) {
      return;
    }
    this.withdrawing.set(true);
    this.withdrawError.set('');
    this.service.withdraw(this.id, reason).subscribe({
      next: ({ manuscript }) => {
        this.manuscript.set(manuscript);
        this.withdrawing.set(false);
        this.withdrawOpen.set(false);
        this.notice.set(
          'El manuscrito fue dado de baja. Su historial, sus versiones y su auditoría se conservan, y puede consultarlo en la vista de archivados.',
        );
      },
      error: (error: ApiError) => {
        this.withdrawing.set(false);
        if (error.status === 409) {
          // Ya estaba dado de baja o su estado cambió: se muestra el estado real.
          this.withdrawOpen.set(false);
          this.load();
          return;
        }
        this.withdrawError.set(withdrawalMessage(error));
      },
    });
  }

  /** El servidor ya guardó el PDF: se refleja sin recargar el manuscrito. */
  protected onDraftUploaded(draft: DraftFileSummary): void {
    this.manuscript.update((manuscript) =>
      manuscript ? { ...manuscript, draft_file: draft } : manuscript,
    );
  }

  protected load(): void {
    this.loading.set(true);
    this.error.set(null);
    this.service.get(this.id).subscribe({
      next: ({ manuscript }) => {
        this.manuscript.set(manuscript);
        this.loading.set(false);
      },
      error: (error: ApiError) => {
        this.error.set(error);
        this.loading.set(false);
      },
    });
  }
}

/** El motivo faltante lo explica el servidor; el resto usa el mensaje accionable. */
function withdrawalMessage(error: ApiError): string {
  const details = error.details as { reason?: unknown } | null;
  const reason = Array.isArray(details?.reason) ? details?.reason[0] : details?.reason;
  return typeof reason === 'string' && reason ? reason : error.userMessage;
}
