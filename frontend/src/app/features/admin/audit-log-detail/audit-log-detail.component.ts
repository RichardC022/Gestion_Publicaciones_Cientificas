import { DatePipe } from '@angular/common';
import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { BehaviorSubject, catchError, combineLatest, map, of, switchMap, tap } from 'rxjs';

import { ApiError, toApiError } from '../../../core/models/api-error.model';
import {
  AuditEventDetail,
  DECISION_LABELS,
  actionLabel,
  detailLabel,
  detailValue,
  resultLabel,
} from '../../../core/models/audit.model';
import { ROLE_LABELS } from '../../../core/models/role.model';
import { AuditService } from '../../../core/services/audit.service';
import { ErrorStateComponent } from '../../../shared/components/error-state.component';
import { LoadingSpinnerComponent } from '../../../shared/components/loading-spinner.component';

/** Las fechas se muestran en la zona institucional (UTC-5, sin horario de verano). */
const INSTITUTIONAL_OFFSET = '-0500';

/**
 * Detalle de un evento de auditoría (plan sección 3.5, HU-17).
 *
 * Muestra solo lo que el backend minimiza para el Administrador: ids
 * opacos, rol, acción, entidad, resultado, fecha, los dos hashes de la
 * cadena y los campos de `details` de la lista blanca. Nunca hay contenido
 * del manuscrito, comentarios, texto libre, IP ni agente de usuario.
 *
 * «Habilitar corrección» aparece solo si el backend lo autoriza
 * (`can_authorize_correction`, que llega únicamente en eventos de
 * veredicto): la SPA no lo deduce del tipo de evento ni del rol.
 */
@Component({
  selector: 'app-audit-log-detail',
  imports: [DatePipe, RouterLink, LoadingSpinnerComponent, ErrorStateComponent],
  template: `
    <section aria-labelledby="audit-log-detail-title">
      <p><a [routerLink]="['/app/admin/audit']">← Volver a la auditoría</a></p>
      <h1 id="audit-log-detail-title">Detalle del evento</h1>

      @switch (viewState()) {
        @case ('loading') {
          <app-loading-spinner label="Cargando el evento…" />
        }
        @case ('missing') {
          <div class="notice" role="alert">
            <p>El evento solicitado no existe.</p>
            <a [routerLink]="['/app/admin/audit']">Ir a la lista de eventos</a>
          </div>
        }
        @case ('error') {
          <app-error-state [message]="error()?.userMessage ?? ''" (retry)="reload()" />
        }
        @default {
          @if (event(); as entry) {
            <dl class="facts">
              <div>
                <dt>Fecha</dt>
                <dd>{{ entry.occurred_at | date: 'dd/MM/yyyy HH:mm:ss' : offset }}</dd>
              </div>
              <div>
                <dt>Acción</dt>
                <dd>
                  {{ action() }} <span class="facts__code">{{ entry.action }}</span>
                </dd>
              </div>
              <div>
                <dt>Resultado</dt>
                <dd>{{ result() }}</dd>
              </div>
              <div>
                <dt>Actor</dt>
                <dd class="facts__mono">{{ entry.actor_id ?? 'Sistema' }}</dd>
              </div>
              <div>
                <dt>Rol</dt>
                <dd>{{ role() }}</dd>
              </div>
              <div>
                <dt>Entidad</dt>
                <dd>
                  {{ entry.entity_type }}
                  @if (entry.entity_id) {
                    <span class="facts__mono"> · {{ entry.entity_id }}</span>
                  }
                </dd>
              </div>
              <div>
                <dt>Manuscrito</dt>
                <dd>
                  @if (entry.manuscript_id) {
                    <a
                      [routerLink]="['/app/admin/audit']"
                      [queryParams]="{ manuscript: entry.manuscript_id }"
                      >{{ entry.manuscript_code ?? entry.manuscript_id }}</a
                    >
                  } @else {
                    —
                  }
                </dd>
              </div>
              <div>
                <dt>Solicitud</dt>
                <dd class="facts__mono">{{ entry.request_id ?? '—' }}</dd>
              </div>
            </dl>

            @if (detailKeys().length > 0) {
              <h2>Datos del evento</h2>
              <dl class="facts" aria-label="Datos del evento">
                @for (key of detailKeys(); track key) {
                  <div>
                    <dt>{{ label(key) }}</dt>
                    <dd>{{ value(key) }}</dd>
                  </div>
                }
              </dl>
            }

            @if (entry.verdict; as verdict) {
              <h2>Veredicto</h2>
              <dl class="facts" aria-label="Veredicto">
                <div>
                  <dt>Manuscrito</dt>
                  <dd>{{ verdict.manuscript_code }}</dd>
                </div>
                <div>
                  <dt>Decisión</dt>
                  <dd>{{ decision(verdict.decision) }}</dd>
                </div>
                <div>
                  <dt>Registrado</dt>
                  <dd>{{ verdict.decided_at | date: 'dd/MM/yyyy HH:mm' : offset }}</dd>
                </div>
              </dl>
            }

            @if (entry.can_authorize_correction === true) {
              <div class="correction">
                <button
                  type="button"
                  class="btn btn--primary"
                  aria-haspopup="dialog"
                  (click)="requestCorrection()"
                >
                  Habilitar corrección
                </button>
                <p class="correction__hint">
                  La decisión anterior se conserva; el Editor registrará una nueva.
                </p>
                @if (correctionRequested()) {
                  <p role="status">
                    La habilitación de la corrección aún no está disponible en esta pantalla.
                  </p>
                }
              </div>
            }

            <h2>Integridad</h2>
            <dl class="facts" aria-label="Integridad de la cadena">
              <div>
                <dt>Hash del evento</dt>
                <dd class="facts__mono facts__hash">{{ entry.entry_hash }}</dd>
              </div>
              <div>
                <dt>Hash anterior</dt>
                <dd class="facts__mono facts__hash">{{ entry.previous_hash ?? '—' }}</dd>
              </div>
            </dl>
          }
        }
      }
    </section>
  `,
  styles: `
    .facts {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(16rem, 1fr));
      gap: 0.75rem 1.5rem;
      margin: 0 0 1rem;
      padding: 1rem 1.25rem;
      background: var(--gpc-surface-alt);
      border: 1px solid var(--gpc-border);
      border-radius: var(--gpc-radius);
    }
    .facts dt {
      font-size: 0.8125rem;
      color: var(--gpc-text-muted);
    }
    .facts dd {
      margin: 0;
      overflow-wrap: anywhere;
    }
    .facts__code {
      display: block;
      font-size: 0.75rem;
      color: var(--gpc-text-muted);
    }
    .facts__mono {
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 0.875rem;
    }
    .facts__hash {
      word-break: break-all;
    }
    .correction {
      margin: 0 0 1rem;
    }
    .correction__hint {
      margin: 0.5rem 0 0;
      color: var(--gpc-text-muted);
      font-size: 0.875rem;
    }
    .notice {
      padding: 1rem 1.25rem;
      background: var(--gpc-surface-alt);
      border: 1px solid var(--gpc-border);
      border-radius: var(--gpc-radius);
    }
  `,
})
export class AuditLogDetailComponent {
  private readonly service = inject(AuditService);
  private readonly route = inject(ActivatedRoute);
  private readonly destroyRef = inject(DestroyRef);

  protected readonly offset = INSTITUTIONAL_OFFSET;

  protected readonly viewState = signal<'loading' | 'ready' | 'missing' | 'error'>('loading');
  protected readonly event = signal<AuditEventDetail | null>(null);
  protected readonly error = signal<ApiError | null>(null);
  protected readonly correctionRequested = signal(false);

  private readonly retry$ = new BehaviorSubject<void>(undefined);

  constructor() {
    combineLatest([this.route.paramMap, this.retry$])
      .pipe(
        map(([params]) => params.get('id') ?? ''),
        tap(() => {
          this.viewState.set('loading');
          this.correctionRequested.set(false);
        }),
        switchMap((id) =>
          this.service.get(id).pipe(
            map((data) => ({ data, error: null as ApiError | null })),
            catchError((error: unknown) => of({ data: null, error: toApiError(error) })),
          ),
        ),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe(({ data, error }) => {
        this.event.set(data);
        this.error.set(error);
        this.viewState.set(error ? (error.status === 404 ? 'missing' : 'error') : 'ready');
      });
  }

  protected action(): string {
    return actionLabel(this.event()?.action ?? '');
  }

  protected result(): string {
    return resultLabel(this.event()?.result ?? '');
  }

  protected role(): string {
    const role = this.event()?.actor_role;
    return role ? ROLE_LABELS[role] : '—';
  }

  /** Campos de `details` que se muestran; el manuscrito ya tiene su fila propia. */
  protected detailKeys(): string[] {
    return Object.keys(this.event()?.details ?? {}).filter((key) => key !== 'manuscript_id');
  }

  protected label(key: string): string {
    return detailLabel(key);
  }

  protected value(key: string): string {
    return detailValue(this.event()?.details[key] ?? null);
  }

  protected decision(code: string): string {
    return DECISION_LABELS[code] ?? code;
  }

  protected requestCorrection(): void {
    this.correctionRequested.set(true);
  }

  protected reload(): void {
    this.retry$.next();
  }
}
