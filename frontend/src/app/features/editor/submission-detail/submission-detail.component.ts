import { DatePipe } from '@angular/common';
import { Component, computed, inject, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';

import { ApiError } from '../../../core/models/api-error.model';
import { SubmissionDetail, SubmissionVersion } from '../../../core/models/editor.model';
import { EditorService } from '../../../core/services/editor.service';
import { ManuscriptService } from '../../../core/services/manuscript.service';
import { ConfirmDialogComponent } from '../../../shared/components/confirm-dialog.component';
import { ErrorStateComponent } from '../../../shared/components/error-state.component';
import { LoadingSpinnerComponent } from '../../../shared/components/loading-spinner.component';
import { RoundCounterComponent } from '../../../shared/components/round-counter.component';
import { StatusBadgeComponent } from '../../../shared/components/status-badge.component';
import { FileSizePipe } from '../../../shared/pipes/file-size.pipe';
import { saveBlob } from '../../../shared/utils/save-blob';

/** Fechas y horas se muestran en la zona institucional (UTC-5, sin horario de verano). */
const INSTITUTIONAL_OFFSET = '-0500';

/**
 * Detalle editorial de un envío (plan sección 3.5, HU-10).
 *
 * * Metadatos completos, autores con su contacto y filiación, cada
 *   versión con el sello de integridad de su PDF, e historial.
 * * El PDF exacto se descarga con `Blob` desde el endpoint autorizado;
 *   el servidor audita cada descarga y la interfaz nunca ve rutas del
 *   volumen.
 * * «Pasar a revisión» solo aparece para un envío `SUBMITTED` activo, pide
 *   confirmación y, al terminar, vuelve a leer el detalle: el estado que
 *   se muestra es siempre el del servidor, también si otro Editor se
 *   adelantó (`409`).
 * * La ruta exige el rol `EDITOR`; el backend vuelve a validarlo y deja
 *   fuera los manuscritos con conflicto de interés (`404`). No hay datos
 *   de auditoría global ni acciones de Administrador.
 */
@Component({
  selector: 'app-submission-detail',
  imports: [
    DatePipe,
    RouterLink,
    LoadingSpinnerComponent,
    ErrorStateComponent,
    StatusBadgeComponent,
    RoundCounterComponent,
    ConfirmDialogComponent,
    FileSizePipe,
  ],
  template: `
    <section aria-labelledby="submission-detail-title">
      <nav aria-label="Navegación del envío">
        <a routerLink="/app/editor/submissions">← Volver a nuevos envíos</a>
      </nav>

      @if (loading()) {
        <app-loading-spinner label="Cargando envío…" />
      } @else if (error()) {
        <app-error-state [message]="error()?.userMessage ?? ''" (retry)="load()" />
      } @else if (submission(); as m) {
        <header class="detail-header">
          <div>
            <p class="detail-code">{{ m.code }}</p>
            <h1 id="submission-detail-title">{{ m.title || 'Sin título' }}</h1>
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
          </div>
        }

        @if (notice(); as message) {
          <p class="callout callout--success" role="status">{{ message }}</p>
        }
        @if (startError(); as message) {
          <p class="callout callout--danger" role="alert">{{ message }}</p>
        }

        @if (canStartReview()) {
          <div class="callout callout--info actions" role="group" aria-label="Acciones del envío">
            <p>Este envío espera que lo pase a revisión.</p>
            <button
              type="button"
              class="btn btn--primary"
              [disabled]="starting()"
              (click)="dialogOpen.set(true)"
            >
              {{ starting() ? 'Pasando a revisión…' : 'Pasar a revisión' }}
            </button>
          </div>
        } @else if (m.status === 'UNDER_REVIEW' && m.is_active) {
          <div class="callout callout--info" role="status">
            @if (m.open_assignment; as assignment) {
              <p>
                En revisión con <strong>{{ assignment.reviewer.full_name }}</strong>
                ({{ assignment.reviewer.email }}). Plazo:
                {{ assignment.due_at | date: 'dd/MM/yyyy HH:mm' : offset }}.
              </p>
            } @else {
              <p>En revisión, a la espera de asignar un Revisor.</p>
            }
          </div>
        }

        <section class="card" aria-labelledby="metadata-title">
          <h2 id="metadata-title">Metadatos</h2>
          <dl class="data">
            <dt>Área</dt>
            <dd>{{ m.area || '—' }}</dd>
            <dt>Idioma</dt>
            <dd>{{ m.language || '—' }}</dd>
            <dt>Palabras clave</dt>
            <dd>{{ m.keywords.length ? m.keywords.join(', ') : '—' }}</dd>
          </dl>
          <h3>Resumen</h3>
          <p class="prose">{{ m.abstract || 'Sin resumen.' }}</p>
        </section>

        <section class="card" aria-labelledby="authors-title">
          <h2 id="authors-title">Autores</h2>
          <div class="table-wrap">
            <table class="plain">
              <caption class="visually-hidden">
                Autores del envío con su contacto y filiación
              </caption>
              <thead>
                <tr>
                  <th scope="col">Nombre</th>
                  <th scope="col">Correo</th>
                  <th scope="col">Filiación</th>
                </tr>
              </thead>
              <tbody>
                @for (author of m.authors; track author.email) {
                  <tr>
                    <td>
                      {{ author.full_name }}
                      @if (author.is_corresponding) {
                        <span class="badge badge--info">Correspondencia</span>
                      }
                    </td>
                    <td>{{ author.email }}</td>
                    <td>{{ author.affiliation }}</td>
                  </tr>
                }
              </tbody>
            </table>
          </div>
        </section>

        <section class="card" aria-labelledby="versions-title">
          <h2 id="versions-title">Versiones y PDF</h2>
          @if (downloadError(); as message) {
            <p class="callout callout--danger" role="alert">{{ message }}</p>
          }
          @if (m.versions.length === 0) {
            <p>Aún no hay versiones formales.</p>
          } @else {
            <ul class="versions">
              @for (version of m.versions; track version.id) {
                <li class="versions__item">
                  <div>
                    <strong>Versión v{{ version.version_number }}</strong>
                    <app-round-counter [round]="version.round_number" />
                    @if (version.version_number === m.current_version) {
                      <span class="badge badge--success">Vigente</span>
                    }
                    <p class="versions__meta">
                      {{ version.original_filename }} ·
                      {{ version.original_size_bytes | fileSize }} · enviada
                      {{ version.submitted_at | date: 'dd/MM/yyyy HH:mm' : offset }}
                    </p>
                    <p class="versions__meta">
                      Sello de integridad: <code>sha256:{{ version.original_sha256 }}</code>
                    </p>
                  </div>
                  <button
                    type="button"
                    class="btn btn--ghost"
                    [disabled]="downloading() === version.id"
                    [attr.aria-label]="'Descargar el PDF de la versión v' + version.version_number"
                    (click)="download(m, version)"
                  >
                    {{ downloading() === version.id ? 'Descargando…' : 'Descargar PDF' }}
                  </button>
                </li>
              }
            </ul>
          }
        </section>

        <section class="card" aria-labelledby="history-title">
          <h2 id="history-title">Historial</h2>
          @if (m.history.length === 0) {
            <p>Aún no hay eventos registrados.</p>
          } @else {
            <ol class="timeline" aria-label="Historial del envío">
              @for (entry of m.history; track $index) {
                <li>
                  <time [attr.datetime]="entry.occurred_at">
                    {{ entry.occurred_at | date: 'dd/MM/yyyy HH:mm' : offset }}
                  </time>
                  @switch (entry.type) {
                    @case ('CREATED') {
                      Borrador creado.
                    }
                    @case ('VERSION_SUBMITTED') {
                      Versión v{{ entry.version_number }} enviada (ronda {{ entry.round_number }}).
                    }
                    @case ('ROUND_OPENED') {
                      Ronda {{ entry.round_number }}
                      {{ entry.closed_by_version_number === null ? 'abierta.' : 'cerrada.' }}
                    }
                    @case ('WITHDRAWN') {
                      Dado de baja.
                    }
                    @default {
                      @if (entry.type === 'STATUS_CHANGED') {
                        @if (entry.from_status) {
                          <app-status-badge [status]="entry.from_status" /> →
                        }
                        <app-status-badge [status]="entry.to_status" />
                      }
                    }
                  }
                </li>
              }
            </ol>
          }
        </section>

        <app-confirm-dialog
          title="Pasar a revisión"
          [message]="confirmMessage()"
          confirmLabel="Pasar a revisión"
          [open]="dialogOpen()"
          (confirmed)="confirmStart()"
          (cancelled)="dialogOpen.set(false)"
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
    }
    .detail-code {
      margin: 0;
      color: var(--gpc-text-muted);
      font-variant-numeric: tabular-nums;
    }
    .detail-badges {
      display: flex;
      flex-wrap: wrap;
      gap: 0.5rem;
    }
    .actions {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 0.75rem;
    }
    .actions p {
      margin: 0;
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
    .data {
      display: grid;
      grid-template-columns: max-content 1fr;
      gap: 0.25rem 1rem;
    }
    .data dt {
      font-weight: 600;
    }
    .data dd {
      margin: 0;
    }
    .table-wrap {
      overflow-x: auto;
    }
    .plain {
      width: 100%;
      border-collapse: collapse;
    }
    .plain th,
    .plain td {
      padding: 0.5rem 0.75rem;
      border-bottom: 1px solid var(--gpc-border);
      text-align: left;
    }
    .versions {
      list-style: none;
      margin: 0;
      padding: 0;
    }
    .versions__item {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 0.75rem;
      padding: 0.75rem 0;
      border-bottom: 1px solid var(--gpc-border);
    }
    .versions__meta {
      margin: 0.25rem 0 0;
      font-size: 0.875rem;
      overflow-wrap: anywhere;
    }
    .timeline {
      margin: 0;
      padding-left: 1.25rem;
    }
    .timeline li {
      margin-bottom: 0.5rem;
    }
    .timeline time {
      margin-right: 0.5rem;
      color: var(--gpc-text-muted);
      font-variant-numeric: tabular-nums;
    }
  `,
})
export class SubmissionDetailComponent {
  private readonly editor = inject(EditorService);
  private readonly manuscripts = inject(ManuscriptService);
  private readonly route = inject(ActivatedRoute);

  protected readonly offset = INSTITUTIONAL_OFFSET;
  protected readonly id = this.route.snapshot.paramMap.get('id') ?? '';

  protected readonly loading = signal(true);
  protected readonly error = signal<ApiError | null>(null);
  protected readonly submission = signal<SubmissionDetail | null>(null);

  protected readonly dialogOpen = signal(false);
  protected readonly starting = signal(false);
  protected readonly startError = signal('');
  protected readonly notice = signal('');

  protected readonly downloading = signal<string | null>(null);
  protected readonly downloadError = signal('');

  protected readonly canStartReview = computed(() => {
    const current = this.submission();
    return current !== null && current.is_active && current.status === 'SUBMITTED';
  });

  protected readonly confirmMessage = computed(
    () =>
      `El envío ${this.submission()?.code ?? ''} pasará a «En revisión» y dejará de aparecer ` +
      'en la bandeja de nuevos envíos. Después podrá asignar al Revisor.',
  );

  constructor() {
    this.load();
  }

  /** Lee el detalle; `silent` conserva la pantalla mientras se actualiza. */
  protected load(silent = false): void {
    if (!silent) {
      this.loading.set(true);
    }
    this.error.set(null);
    this.editor.getSubmission(this.id).subscribe({
      next: ({ submission }) => {
        this.submission.set(submission);
        this.loading.set(false);
      },
      error: (error: ApiError) => {
        // Una actualización fallida no borra lo que ya se estaba mostrando.
        if (!silent || this.submission() === null) {
          this.error.set(error);
        }
        this.loading.set(false);
      },
    });
  }

  protected confirmStart(): void {
    this.dialogOpen.set(false);
    if (this.starting()) {
      return;
    }
    this.starting.set(true);
    this.startError.set('');
    this.notice.set('');
    this.editor.startReview(this.id).subscribe({
      next: () => {
        this.starting.set(false);
        this.notice.set('El envío pasó a revisión.');
        this.load(true);
      },
      error: (error: ApiError) => {
        this.starting.set(false);
        this.startError.set(error.userMessage);
        // Si otro Editor se adelantó, se muestra el estado real.
        this.load(true);
      },
    });
  }

  /** Descarga el PDF exacto de la versión; el servidor audita cada descarga. */
  protected download(submission: SubmissionDetail, version: SubmissionVersion): void {
    if (this.downloading() !== null) {
      return;
    }
    this.downloading.set(version.id);
    this.downloadError.set('');
    this.manuscripts
      .downloadVersion(submission.id, version.id, `${submission.code}-v${version.version_number}.pdf`)
      .subscribe({
        next: ({ blob, filename }) => {
          saveBlob(blob, filename);
          this.downloading.set(null);
        },
        error: (error: ApiError) => {
          this.downloadError.set(error.userMessage);
          this.downloading.set(null);
        },
      });
  }
}
