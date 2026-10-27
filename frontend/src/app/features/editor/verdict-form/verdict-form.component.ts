import { DatePipe } from '@angular/common';
import { Component, computed, inject, input, output, signal } from '@angular/core';
import { takeUntilDestroyed, toObservable } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { BehaviorSubject, catchError, combineLatest, forkJoin, map, of, switchMap, tap } from 'rxjs';

import { newIdempotencyKey } from '../../../core/http/idempotency-key';
import { ApiError, toApiError } from '../../../core/models/api-error.model';
import {
  EditorEvaluation,
  RECOMMENDATION_LABELS,
  Recommendation,
  Verdict,
  VerdictDecision,
  VerdictRegistered,
  VerdictRequest,
  departsFromRecommendation,
} from '../../../core/models/editor.model';
import { EditorService } from '../../../core/services/editor.service';
import { ConfirmDialogComponent } from '../../../shared/components/confirm-dialog.component';
import { ErrorStateComponent } from '../../../shared/components/error-state.component';
import { LoadingSpinnerComponent } from '../../../shared/components/loading-spinner.component';
import { StatusBadgeComponent } from '../../../shared/components/status-badge.component';

/** Máximo de cada texto que acepta la API. */
export const VERDICT_TEXT_MAX_LENGTH = 5000;

/** Fechas y horas se muestran en la zona institucional (UTC-5, sin horario de verano). */
const INSTITUTIONAL_OFFSET = '-0500';

/** Códigos de conflicto tras los cuales lo que el Editor ve ya no es lo vigente. */
const STALE_CODES = ['STATE_CONFLICT', 'VERSION_CONFLICT', 'VERDICT_CONFLICT'];

let nextId = 0;

/** Las opciones de decisión, con el color que la constitución asigna a cada acción. */
export const DECISION_OPTIONS: readonly {
  value: VerdictDecision;
  label: string;
  hint: string;
  tone: 'success' | 'danger' | 'warning';
}[] = [
  {
    value: 'ACCEPTED',
    label: 'Aceptado',
    hint: 'El artículo se publica de inmediato en el catálogo público.',
    tone: 'success',
  },
  {
    value: 'REQUIRES_CORRECTIONS',
    label: 'Requiere correcciones',
    hint: 'Se abre la siguiente ronda para que el Autor envíe una nueva versión.',
    tone: 'warning',
  },
  {
    value: 'REJECTED',
    label: 'Rechazado',
    hint: 'El manuscrito no se publica.',
    tone: 'danger',
  },
];

export interface VerdictFormValue {
  decision: VerdictDecision | null;
  justification: string;
  observations: string;
}

export interface VerdictFormErrors {
  decision?: string;
  justification?: string;
  observations?: string;
}

/** La justificación es obligatoria al rechazar o al apartarse de la recomendación. */
export function justificationRequired(
  decision: VerdictDecision | null,
  recommendation: Recommendation | null,
): boolean {
  if (decision === null) {
    return false;
  }
  return (
    decision === 'REJECTED' ||
    (recommendation !== null && departsFromRecommendation(decision, recommendation))
  );
}

/**
 * Validación del formulario, espejo de las reglas del servidor (HU-13):
 * decisión obligatoria; justificación al rechazar o al apartarse de la
 * recomendación del Revisor; observaciones al pedir correcciones.
 */
export function verdictFormErrors(
  value: VerdictFormValue,
  recommendation: Recommendation | null,
): VerdictFormErrors {
  const errors: VerdictFormErrors = {};
  if (value.decision === null) {
    errors.decision = 'Seleccione una decisión.';
    return errors;
  }
  if (justificationRequired(value.decision, recommendation) && value.justification.trim() === '') {
    errors.justification =
      value.decision === 'REJECTED'
        ? 'Indique la justificación del rechazo.'
        : 'Justifique por qué se aparta de la recomendación del Revisor.';
  }
  if (value.decision === 'REQUIRES_CORRECTIONS' && value.observations.trim() === '') {
    errors.observations = 'Indique las observaciones para el Autor.';
  }
  return errors;
}

/**
 * Evaluación final del Revisor y veredicto del Editor (plan sección 3.5,
 * HU-13).
 *
 * * Muestra la evaluación final de la versión vigente —con la identidad del
 *   Revisor y los comentarios confidenciales, que solo el Editor ve— y la
 *   **recomendación en solo lectura**: el Editor decide, no la edita.
 * * Ofrece Aceptado, Requiere correcciones o Rechazado. Exige la
 *   justificación al rechazar o al apartarse de la recomendación (y lo
 *   advierte), y las observaciones al pedir correcciones. Con campos
 *   obligatorios vacíos no se envía nada.
 * * Pide confirmación antes de registrar: un veredicto no se puede editar.
 * * Los veredictos registrados se listan **solo en lectura**: no hay forma
 *   de editarlos ni de sobrescribirlos desde la interfaz, y con la versión
 *   ya juzgada el formulario desaparece.
 * * Envía `If-Match` con el `ETag` del manuscrito e `Idempotency-Key`: un
 *   reintento tras un corte de red devuelve lo ya registrado, y la clave
 *   cambia si el Editor modifica el contenido.
 */
@Component({
  selector: 'app-verdict-form',
  imports: [
    DatePipe,
    FormsModule,
    LoadingSpinnerComponent,
    ErrorStateComponent,
    StatusBadgeComponent,
    ConfirmDialogComponent,
  ],
  template: `
    <section class="verdict" [attr.aria-labelledby]="titleId">
      <h2 [id]="titleId">Evaluación y veredicto</h2>

      @switch (viewState()) {
        @case ('loading') {
          <app-loading-spinner label="Cargando evaluación…" />
        }
        @case ('error') {
          <app-error-state [message]="loadError()?.userMessage ?? ''" (retry)="reload()" />
        }
        @default {
          @if (evaluation(); as ev) {
            <article class="verdict__evaluation" aria-label="Evaluación final del Revisor">
              <h3>Evaluación final de la versión v{{ ev.version_number }}</h3>
              <p>
                <strong>{{ ev.reviewer.full_name }}</strong> ({{ ev.reviewer.email }})
                @if (ev.submitted_at) {
                  · enviada el {{ ev.submitted_at | date: 'dd/MM/yyyy HH:mm' : offset }}
                }
              </p>
              <p class="verdict__recommendation">
                Recomendación del Revisor:
                <span class="badge badge--info">{{ recommendationLabel() }}</span>
                <span class="verdict__hint">(solo lectura)</span>
              </p>
              <ul class="verdict__scores" aria-label="Puntuaciones">
                @for (score of scores(); track score.label) {
                  <li>{{ score.label }}: <strong>{{ score.value ?? '—' }}</strong> / 5</li>
                }
              </ul>
              @if (ev.comments_for_author) {
                <h4>Comentarios para el Autor</h4>
                <p class="verdict__prose">{{ ev.comments_for_author }}</p>
              }
              @if (ev.confidential_comments) {
                <h4>Comentarios confidenciales <span class="verdict__hint">(solo el Editor)</span></h4>
                <p class="verdict__prose">{{ ev.confidential_comments }}</p>
              }
              @if (ev.conflict_declared) {
                <p class="verdict__note" role="note">El Revisor declaró un conflicto de interés.</p>
              }
            </article>
          } @else if (canRegister()) {
            <p class="verdict__note" role="status">
              Aún no hay una evaluación final de la versión vigente. El veredicto se habilita
              cuando el Revisor la envíe.
            </p>
          }

          @if (verdicts().length > 0) {
            <section class="verdict__history" [attr.aria-labelledby]="historyId">
              <h3 [id]="historyId">Veredictos registrados</h3>
              <p class="verdict__hint">
                Un veredicto registrado no se edita ni se sobrescribe.
              </p>
              <ol>
                @for (verdict of verdicts(); track verdict.id) {
                  <li>
                    <time [attr.datetime]="verdict.created_at">
                      {{ verdict.created_at | date: 'dd/MM/yyyy HH:mm' : offset }}
                    </time>
                    <app-status-badge [status]="verdict.decision" />
                    versión v{{ verdict.version_number }} · {{ verdict.editor.full_name }}
                    @if (verdict.previous_verdict) {
                      <span class="verdict__hint">(sustituye a un veredicto anterior)</span>
                    }
                    @if (verdict.justification) {
                      <p class="verdict__prose">Justificación: {{ verdict.justification }}</p>
                    }
                    @if (verdict.observations) {
                      <p class="verdict__prose">Observaciones: {{ verdict.observations }}</p>
                    }
                  </li>
                }
              </ol>
            </section>
          }

          @if (showForm()) {
            <form class="verdict__form" (ngSubmit)="submit()" novalidate>
              <fieldset [disabled]="busy()">
                <legend>Decisión</legend>
                @for (option of options; track option.value) {
                  <label class="verdict__option verdict__option--{{ option.tone }}">
                    <input
                      type="radio"
                      name="verdict-decision"
                      [value]="option.value"
                      [checked]="decision() === option.value"
                      (change)="chooseDecision(option.value)"
                    />
                    <span>
                      <strong>{{ option.label }}</strong>
                      <span class="verdict__hint">{{ option.hint }}</span>
                    </span>
                  </label>
                }
                @if (errors().decision; as message) {
                  <p class="verdict__error" role="alert">{{ message }}</p>
                }
              </fieldset>

              @if (departs()) {
                <p class="verdict__warning" role="alert">
                  Su decisión se aparta de la recomendación del Revisor
                  ({{ recommendationLabel() }}). Debe justificarla.
                </p>
              }

              @if (needsJustification()) {
                <div class="verdict__field">
                  <label [for]="justificationId">
                    Justificación <span class="verdict__hint">(obligatoria)</span>
                  </label>
                  <textarea
                    [id]="justificationId"
                    rows="4"
                    [maxlength]="maxLength"
                    aria-required="true"
                    [attr.aria-invalid]="errors().justification ? 'true' : null"
                    [attr.aria-describedby]="errors().justification ? justificationErrorId : null"
                    [disabled]="busy()"
                    [ngModel]="justification()"
                    (ngModelChange)="editJustification($event)"
                    name="justification"
                  ></textarea>
                  @if (errors().justification; as message) {
                    <p class="verdict__error" role="alert" [id]="justificationErrorId">
                      {{ message }}
                    </p>
                  }
                </div>
              }

              @if (decision() === 'REQUIRES_CORRECTIONS') {
                <div class="verdict__field">
                  <label [for]="observationsId">
                    Observaciones para el Autor <span class="verdict__hint">(obligatorias)</span>
                  </label>
                  <textarea
                    [id]="observationsId"
                    rows="5"
                    [maxlength]="maxLength"
                    aria-required="true"
                    [attr.aria-invalid]="errors().observations ? 'true' : null"
                    [attr.aria-describedby]="errors().observations ? observationsErrorId : null"
                    [disabled]="busy()"
                    [ngModel]="observations()"
                    (ngModelChange)="editObservations($event)"
                    name="observations"
                  ></textarea>
                  @if (errors().observations; as message) {
                    <p class="verdict__error" role="alert" [id]="observationsErrorId">
                      {{ message }}
                    </p>
                  }
                </div>
              }

              @if (submitError()) {
                <p class="verdict__error" role="alert">{{ submitError() }}</p>
              }

              <button type="submit" class="btn btn--primary" [disabled]="busy()">
                {{ busy() ? 'Registrando…' : 'Registrar veredicto' }}
              </button>
            </form>
          }

          <app-confirm-dialog
            title="Registrar veredicto"
            [message]="confirmMessage()"
            confirmLabel="Registrar veredicto"
            [destructive]="decision() === 'REJECTED'"
            [open]="confirmOpen()"
            (confirmed)="send()"
            (cancelled)="confirmOpen.set(false)"
          />
        }
      }
    </section>
  `,
  styles: `
    .verdict__evaluation,
    .verdict__history {
      margin: 0 0 1rem;
      padding: 0.75rem 1rem;
      background: var(--gpc-surface);
      border: 1px solid var(--gpc-border);
      border-radius: var(--gpc-radius);
    }
    .verdict h3 {
      margin: 0 0 0.5rem;
      font-size: 1.0625rem;
    }
    .verdict h4 {
      margin: 0.75rem 0 0.25rem;
      font-size: 0.9375rem;
    }
    .verdict__hint {
      font-weight: 400;
      font-size: 0.8125rem;
      color: var(--gpc-text-muted);
    }
    .verdict__scores {
      display: flex;
      flex-wrap: wrap;
      gap: 0.25rem 1.25rem;
      margin: 0.5rem 0;
      padding: 0;
      list-style: none;
    }
    .verdict__prose {
      margin: 0.25rem 0;
      white-space: pre-line;
      overflow-wrap: anywhere;
    }
    .verdict__note {
      padding: 0.5rem 0.75rem;
      background: var(--gpc-primary-50);
      border: 1px solid var(--gpc-primary-700);
      border-radius: var(--gpc-radius);
    }
    .verdict__history ol {
      margin: 0;
      padding-left: 1.25rem;
    }
    .verdict__history li {
      margin-bottom: 0.5rem;
    }
    .verdict__history time {
      margin-right: 0.5rem;
      color: var(--gpc-text-muted);
      font-variant-numeric: tabular-nums;
    }
    .verdict__form fieldset {
      margin: 0 0 1rem;
      padding: 0;
      border: 0;
    }
    .verdict__form legend {
      padding: 0;
      margin-bottom: 0.25rem;
      font-weight: 600;
    }
    .verdict__option {
      display: flex;
      align-items: flex-start;
      gap: 0.5rem;
      margin: 0.375rem 0;
      padding: 0.5rem 0.75rem;
      border: 1px solid var(--gpc-border);
      border-left-width: 4px;
      border-radius: var(--gpc-radius);
    }
    .verdict__option span {
      display: flex;
      flex-direction: column;
    }
    .verdict__option--success {
      border-left-color: var(--gpc-success-700);
    }
    .verdict__option--warning {
      border-left-color: var(--gpc-warning-800);
    }
    .verdict__option--danger {
      border-left-color: var(--gpc-danger-700);
    }
    .verdict__warning {
      margin: 0 0 1rem;
      padding: 0.5rem 0.75rem;
      background: var(--gpc-warning-100);
      border: 1px solid var(--gpc-warning-800);
      border-radius: var(--gpc-radius);
      color: var(--gpc-warning-800);
    }
    .verdict__field {
      display: flex;
      flex-direction: column;
      gap: 0.25rem;
      margin-bottom: 1rem;
    }
    .verdict__field label {
      font-weight: 600;
      font-size: 0.9rem;
    }
    .verdict__field textarea {
      padding: 0.5rem 0.625rem;
      border: 1px solid var(--gpc-border);
      border-radius: var(--gpc-radius);
      font: inherit;
      resize: vertical;
    }
    .verdict__field textarea[aria-invalid='true'] {
      border-color: var(--gpc-danger-700);
    }
    .verdict__error {
      margin: 0.25rem 0;
      color: var(--gpc-danger-700);
      font-size: 0.875rem;
    }
  `,
})
export class VerdictFormComponent {
  private readonly service = inject(EditorService);

  /** Manuscrito que se juzga. */
  readonly manuscriptId = input.required<string>();

  /** Versión vigente: la que evalúa el Revisor y la que se juzga. */
  readonly version = input.required<number>();

  /** `ETag` del manuscrito al leerlo; viaja en `If-Match`. */
  readonly etag = input<string | null>(null);

  /** El manuscrito está en revisión y activo: solo entonces se puede registrar. */
  readonly canRegister = input(false);

  /** Se dispara cuando el veredicto quedó registrado. */
  readonly registered = output<VerdictRegistered>();

  /** Lo que el Editor ve ya no es lo vigente (otro Editor actuó): hay que releer el detalle. */
  readonly stale = output<void>();

  protected readonly options = DECISION_OPTIONS;
  protected readonly offset = INSTITUTIONAL_OFFSET;
  protected readonly maxLength = VERDICT_TEXT_MAX_LENGTH;
  protected readonly titleId = `verdict-title-${nextId}`;
  protected readonly historyId = `verdict-history-${nextId}`;
  protected readonly justificationId = `verdict-justification-${nextId}`;
  protected readonly justificationErrorId = `verdict-justification-error-${nextId}`;
  protected readonly observationsId = `verdict-observations-${nextId}`;
  protected readonly observationsErrorId = `verdict-observations-error-${nextId++}`;

  protected readonly viewState = signal<'loading' | 'ready' | 'error'>('loading');
  protected readonly loadError = signal<ApiError | null>(null);
  private readonly evaluations = signal<EditorEvaluation[]>([]);
  protected readonly verdicts = signal<Verdict[]>([]);

  protected readonly decision = signal<VerdictDecision | null>(null);
  protected readonly justification = signal('');
  protected readonly observations = signal('');
  private readonly attempted = signal(false);
  protected readonly confirmOpen = signal(false);
  protected readonly busy = signal(false);
  protected readonly submitError = signal('');

  /** Identifica esta intención de veredicto; cambia si el Editor modifica el contenido. */
  private idempotencyKey: string | null = null;

  /** Evaluación final de la versión vigente. */
  protected readonly evaluation = computed(
    () => this.evaluations().find((ev) => ev.version_number === this.version()) ?? null,
  );

  protected readonly recommendation = computed<Recommendation | null>(
    () => this.evaluation()?.recommendation ?? null,
  );

  protected readonly recommendationLabel = computed(() => {
    const recommendation = this.recommendation();
    return recommendation ? RECOMMENDATION_LABELS[recommendation] : '—';
  });

  protected readonly scores = computed(() => {
    const ev = this.evaluation();
    return [
      { label: 'Originalidad', value: ev?.originality_score ?? null },
      { label: 'Metodología', value: ev?.methodology_score ?? null },
      { label: 'Claridad', value: ev?.clarity_score ?? null },
      { label: 'Relevancia', value: ev?.relevance_score ?? null },
      { label: 'Ética', value: ev?.ethics_score ?? null },
    ];
  });

  /** Ya existe el veredicto normal de la versión vigente: no se vuelve a juzgar. */
  private readonly judged = computed(() =>
    this.verdicts().some((v) => v.version_number === this.version() && v.previous_verdict === null),
  );

  protected readonly showForm = computed(
    () => this.canRegister() && this.evaluation() !== null && !this.judged(),
  );

  protected readonly departs = computed(() => {
    const decision = this.decision();
    const recommendation = this.recommendation();
    return (
      decision !== null &&
      recommendation !== null &&
      departsFromRecommendation(decision, recommendation)
    );
  });

  protected readonly needsJustification = computed(() =>
    justificationRequired(this.decision(), this.recommendation()),
  );

  protected readonly errors = computed<VerdictFormErrors>(() =>
    this.attempted()
      ? verdictFormErrors(
          {
            decision: this.decision(),
            justification: this.justification(),
            observations: this.observations(),
          },
          this.recommendation(),
        )
      : {},
  );

  protected readonly confirmMessage = computed(() => {
    const base = 'El veredicto no se puede editar ni sobrescribir una vez registrado. ';
    switch (this.decision()) {
      case 'ACCEPTED':
        return `${base}El manuscrito pasará a «Aceptado» y se publicará de inmediato en el catálogo público.`;
      case 'REJECTED':
        return `${base}El manuscrito pasará a «Rechazado» y no se publicará.`;
      case 'REQUIRES_CORRECTIONS':
        return `${base}El manuscrito pasará a «Requiere correcciones» y se abrirá la siguiente ronda para que el Autor envíe una nueva versión.`;
      default:
        return base;
    }
  });

  private readonly retry$ = new BehaviorSubject<void>(undefined);

  constructor() {
    combineLatest([toObservable(this.manuscriptId), toObservable(this.version), this.retry$])
      .pipe(
        map(([id]) => id),
        tap(() => this.viewState.set('loading')),
        switchMap((id) =>
          forkJoin({
            evaluations: this.service.listEvaluations(id),
            verdicts: this.service.listVerdicts(id),
          }).pipe(
            map((data) => ({ data, error: null as ApiError | null })),
            catchError((error: unknown) => of({ data: null, error: toApiError(error) })),
          ),
        ),
        takeUntilDestroyed(),
      )
      .subscribe(({ data, error }) => {
        this.evaluations.set(data?.evaluations.results ?? []);
        this.verdicts.set(data?.verdicts.results ?? []);
        this.loadError.set(error);
        this.viewState.set(error ? 'error' : 'ready');
      });
  }

  protected reload(): void {
    this.retry$.next();
  }

  protected chooseDecision(decision: VerdictDecision): void {
    this.decision.set(decision);
    this.touched();
  }

  protected editJustification(value: string): void {
    this.justification.set(value);
    this.touched();
  }

  protected editObservations(value: string): void {
    this.observations.set(value);
    this.touched();
  }

  /** Un cambio de contenido es otra intención: la clave de idempotencia ya no sirve. */
  private touched(): void {
    this.idempotencyKey = null;
    this.submitError.set('');
  }

  protected submit(): void {
    if (this.busy()) {
      return;
    }
    this.attempted.set(true);
    if (Object.keys(this.errors()).length > 0) {
      return;
    }
    this.confirmOpen.set(true);
  }

  protected send(): void {
    this.confirmOpen.set(false);
    const decision = this.decision();
    const etag = this.etag();
    if (decision === null || this.busy()) {
      return;
    }
    if (etag === null) {
      this.submitError.set('No se pudo identificar la versión del manuscrito; recargue e intente de nuevo.');
      this.stale.emit();
      return;
    }
    const request: VerdictRequest = {
      decision,
      justification: this.needsJustification() ? this.justification().trim() || null : null,
      observations:
        decision === 'REQUIRES_CORRECTIONS' ? this.observations().trim() || null : null,
    };
    this.idempotencyKey ??= newIdempotencyKey();
    this.busy.set(true);
    this.submitError.set('');
    this.service
      .createVerdict(this.manuscriptId(), request, etag, this.idempotencyKey)
      .subscribe({
        next: (registered) => {
          this.busy.set(false);
          this.idempotencyKey = null;
          this.verdicts.set(registered.result.history);
          this.decision.set(null);
          this.justification.set('');
          this.observations.set('');
          this.attempted.set(false);
          this.registered.emit(registered);
        },
        error: (error: ApiError) => {
          this.busy.set(false);
          this.submitError.set(error.userMessage);
          if (STALE_CODES.includes(error.code)) {
            // Lo que se ve ya no es lo vigente: se relee todo, también el detalle.
            this.idempotencyKey = null;
            this.reload();
            this.stale.emit();
          }
        },
      });
  }
}
