import { DatePipe } from '@angular/common';
import { Component, inject, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { forkJoin } from 'rxjs';

import { ApiError } from '../../../core/models/api-error.model';
import {
  HistoryEntry,
  Manuscript,
  VersionHistoryEntry,
} from '../../../core/models/manuscript.model';
import { ManuscriptService } from '../../../core/services/manuscript.service';
import { ErrorStateComponent } from '../../../shared/components/error-state.component';
import { LoadingSpinnerComponent } from '../../../shared/components/loading-spinner.component';
import { RoundCounterComponent } from '../../../shared/components/round-counter.component';
import { StatusBadgeComponent } from '../../../shared/components/status-badge.component';
import { FileSizePipe } from '../../../shared/pipes/file-size.pipe';
import { saveBlob } from '../../../shared/utils/save-blob';

/** Fechas y horas se muestran en la zona institucional (UTC-5, sin horario de verano). */
const INSTITUTIONAL_OFFSET = '-0500';

/**
 * Línea de tiempo inmutable de un manuscrito (plan sección 3.5, HU-23).
 *
 * * Cada iteración formal muestra su versión, ronda, fecha, el **sello
 *   de integridad** (SHA-256 del PDF exacto) y el sello de los metadatos
 *   enviados con ella, y permite descargar el PDF exacto.
 * * Todo se presenta en solo lectura: las versiones anteriores no
 *   ofrecen ninguna acción de edición ni de reemplazo.
 * * Incluye creación, rondas, cambios de estado y la baja lógica, en
 *   orden cronológico. No muestra actores ni rutas internas.
 * * La descarga usa `Blob`; el archivo no se guarda en el navegador.
 */
@Component({
  selector: 'app-version-history',
  imports: [
    DatePipe,
    RouterLink,
    LoadingSpinnerComponent,
    ErrorStateComponent,
    StatusBadgeComponent,
    RoundCounterComponent,
    FileSizePipe,
  ],
  template: `
    <section aria-labelledby="version-history-title">
      <nav aria-label="Navegación del manuscrito">
        <a [routerLink]="['/app/author/manuscripts', id]">← Volver al manuscrito</a>
      </nav>

      <h1 id="version-history-title">Historial de versiones</h1>

      @if (loading()) {
        <app-loading-spinner label="Cargando historial…" />
      } @else if (error()) {
        <app-error-state [message]="error()?.userMessage ?? ''" (retry)="load()" />
      } @else if (manuscript(); as m) {
        <p class="history-subject">
          <strong>{{ m.code }}</strong> · {{ m.title || 'Sin título' }}
          <app-status-badge [status]="m.status" />
          @if (!m.is_active) {
            <app-status-badge status="WITHDRAWN" />
          }
        </p>

        <p class="history-note" role="note">
          Este historial es inmutable: cada versión conserva su PDF exacto y los metadatos tal como
          se enviaron. Los registros anteriores nunca se modifican.
        </p>

        @if (downloadError()) {
          <p class="history-error" role="alert">{{ downloadError() }}</p>
        }

        @if (entries().length === 0) {
          <p class="history-empty" role="status">Aún no hay eventos registrados.</p>
        } @else {
          <ol class="timeline" aria-label="Línea de tiempo del manuscrito">
            @for (entry of entries(); track $index) {
              <li class="timeline__item">
                <time class="timeline__date" [attr.datetime]="entry.occurred_at">
                  {{ entry.occurred_at | date: 'dd/MM/yyyy HH:mm' : offset }}
                </time>

                @if (entry.type === 'VERSION_SUBMITTED') {
                  <article
                    class="timeline__card timeline__card--version"
                    [attr.aria-label]="'Versión v' + entry.version_number"
                  >
                    <h2>
                      Versión v{{ entry.version_number }}
                      <app-round-counter [round]="entry.round_number" />
                      @if (entry.version_number === m.current_version) {
                        <span class="badge badge--success">Vigente</span>
                      }
                    </h2>
                    <dl class="seal">
                      <dt>Archivo</dt>
                      <dd>
                        {{ entry.original_filename }} · {{ entry.original_size_bytes | fileSize }}
                      </dd>
                      <dt>Sello de integridad del PDF</dt>
                      <dd>
                        <code>{{ entry.integrity_seal }}</code>
                      </dd>
                      <dt>Sello de los metadatos</dt>
                      <dd>
                        <code>sha256:{{ entry.metadata_sha256 }}</code>
                      </dd>
                    </dl>
                    <button
                      type="button"
                      class="btn btn--primary"
                      [disabled]="downloading() === entry.version_id"
                      [attr.aria-label]="
                        'Descargar el PDF exacto de la versión v' + entry.version_number
                      "
                      (click)="download(entry)"
                    >
                      {{
                        downloading() === entry.version_id ? 'Descargando…' : 'Descargar PDF exacto'
                      }}
                    </button>
                  </article>
                } @else if (entry.type === 'ROUND_OPENED') {
                  <article class="timeline__card">
                    <h2>Ronda {{ entry.round_number }}</h2>
                    <p>
                      @if (entry.closed_by_version_number !== null) {
                        Cerrada con la versión v{{ entry.closed_by_version_number }}
                        @if (entry.closed_at) {
                          el {{ entry.closed_at | date: 'dd/MM/yyyy HH:mm' : offset }}
                        }
                        .
                      } @else {
                        Abierta: a la espera de la nueva versión.
                      }
                    </p>
                  </article>
                } @else if (entry.type === 'WITHDRAWN') {
                  <article class="timeline__card timeline__card--withdrawn">
                    <h2>Dado de baja</h2>
                    <p>El manuscrito se archivó; todo su historial se conserva.</p>
                    @if (entry.reason) {
                      <p>Motivo: {{ entry.reason }}</p>
                    }
                  </article>
                } @else if (entry.type === 'CREATED') {
                  <article class="timeline__card">
                    <h2>Borrador creado</h2>
                  </article>
                } @else {
                  <article class="timeline__card">
                    <h2>Cambio de estado</h2>
                    <p>
                      @if (entry.from_status) {
                        <app-status-badge [status]="entry.from_status" /> →
                      }
                      <app-status-badge [status]="entry.to_status" />
                    </p>
                    @if (entry.version_number !== null) {
                      <p>Versión v{{ entry.version_number }}</p>
                    }
                    @if (entry.reason) {
                      <p>{{ entry.reason }}</p>
                    }
                  </article>
                }
              </li>
            }
          </ol>

          @if (hasMore()) {
            <button
              type="button"
              class="btn btn--ghost"
              [disabled]="loadingMore()"
              (click)="loadMore()"
            >
              {{ loadingMore() ? 'Cargando…' : 'Mostrar más eventos' }}
            </button>
          }
        }
      }
    </section>
  `,
  styles: `
    .history-subject {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 0.5rem;
    }
    .history-note {
      padding: 0.625rem 0.875rem;
      background: var(--gpc-primary-50);
      border: 1px solid var(--gpc-primary-700);
      border-radius: var(--gpc-radius);
    }
    .history-error {
      color: var(--gpc-danger-700);
    }
    .timeline {
      list-style: none;
      margin: 1.5rem 0;
      padding: 0 0 0 1.25rem;
      border-left: 3px solid var(--gpc-primary-100);
    }
    .timeline__item {
      position: relative;
      margin: 0 0 1.25rem;
    }
    .timeline__item::before {
      content: '';
      position: absolute;
      left: -1.65rem;
      top: 0.35rem;
      width: 0.75rem;
      height: 0.75rem;
      border-radius: 50%;
      background: var(--gpc-primary-700);
    }
    .timeline__date {
      display: block;
      margin-bottom: 0.25rem;
      font-size: 0.8125rem;
      color: var(--gpc-text-muted);
      font-variant-numeric: tabular-nums;
    }
    .timeline__card {
      padding: 0.75rem 1rem;
      background: var(--gpc-surface-alt);
      border: 1px solid var(--gpc-border);
      border-radius: var(--gpc-radius);
    }
    .timeline__card h2 {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 0.5rem;
      margin: 0 0 0.5rem;
      font-size: 1.0625rem;
    }
    .timeline__card p {
      margin: 0 0 0.25rem;
    }
    .timeline__card--version {
      border-color: var(--gpc-primary-700);
    }
    .timeline__card--withdrawn {
      background: var(--gpc-surface);
    }
    .seal {
      display: grid;
      grid-template-columns: max-content 1fr;
      gap: 0.25rem 1rem;
      margin: 0 0 0.75rem;
    }
    .seal dt {
      font-weight: 600;
    }
    .seal dd {
      margin: 0;
      min-width: 0;
    }
    .seal code {
      font-size: 0.8125rem;
      overflow-wrap: anywhere;
      user-select: all;
    }
  `,
})
export class VersionHistoryComponent {
  private readonly service = inject(ManuscriptService);
  private readonly route = inject(ActivatedRoute);

  protected readonly offset = INSTITUTIONAL_OFFSET;
  protected readonly id = this.route.snapshot.paramMap.get('id') ?? '';

  protected readonly loading = signal(true);
  protected readonly error = signal<ApiError | null>(null);
  protected readonly manuscript = signal<Manuscript | null>(null);
  protected readonly entries = signal<HistoryEntry[]>([]);
  protected readonly hasMore = signal(false);
  protected readonly loadingMore = signal(false);
  protected readonly downloading = signal<string | null>(null);
  protected readonly downloadError = signal('');

  private page = 1;

  constructor() {
    this.load();
  }

  protected load(): void {
    this.loading.set(true);
    this.error.set(null);
    this.downloadError.set('');
    this.page = 1;
    forkJoin({
      snapshot: this.service.get(this.id),
      history: this.service.getHistory(this.id),
    }).subscribe({
      next: ({ snapshot, history }) => {
        this.manuscript.set(snapshot.manuscript);
        this.entries.set(history.results);
        this.hasMore.set(history.next !== null);
        this.loading.set(false);
      },
      error: (error: ApiError) => {
        this.error.set(error);
        this.loading.set(false);
      },
    });
  }

  protected loadMore(): void {
    if (this.loadingMore()) {
      return;
    }
    this.loadingMore.set(true);
    this.service.getHistory(this.id, this.page + 1).subscribe({
      next: (history) => {
        this.page += 1;
        this.entries.update((current) => [...current, ...history.results]);
        this.hasMore.set(history.next !== null);
        this.loadingMore.set(false);
      },
      error: (error: ApiError) => {
        this.downloadError.set(error.userMessage);
        this.loadingMore.set(false);
      },
    });
  }

  /** Descarga el PDF exacto de la versión; el servidor audita cada descarga. */
  protected download(entry: VersionHistoryEntry): void {
    if (this.downloading() !== null) {
      return;
    }
    this.downloading.set(entry.version_id);
    this.downloadError.set('');
    const code = this.manuscript()?.code ?? 'manuscrito';
    this.service
      .downloadVersion(this.id, entry.version_id, `${code}-v${entry.version_number}.pdf`)
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
