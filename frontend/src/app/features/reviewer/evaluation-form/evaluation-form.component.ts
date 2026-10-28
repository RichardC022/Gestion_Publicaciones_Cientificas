import { DatePipe } from '@angular/common';
import { Component, computed, inject, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { forkJoin, map, of, switchMap, tap } from 'rxjs';

import { UnsavedChangesAware } from '../../../core/auth/unsaved-changes.guard';
import { ApiError } from '../../../core/models/api-error.model';
import { Recommendation } from '../../../core/models/editor.model';
import {
  COMMENT_MAX_LENGTH,
  EvaluationSnapshot,
  RECOMMENDATION_OPTIONS,
  ReviewerAssignmentDetail,
  ReviewerEvaluation,
  SCORE_CRITERIA,
  MAX_SCORE,
  MIN_SCORE,
  ScoreField,
} from '../../../core/models/reviewer.model';
import { ReviewerService } from '../../../core/services/reviewer.service';
import { ConfirmDialogComponent } from '../../../shared/components/confirm-dialog.component';
import { ErrorStateComponent } from '../../../shared/components/error-state.component';
import { LoadingSpinnerComponent } from '../../../shared/components/loading-spinner.component';
import { DeadlineCountdownComponent } from '../deadline-countdown/deadline-countdown.component';
import {
  EMPTY_VALUES,
  EvaluationErrors,
  EvaluationField,
  EvaluationValues,
  isDirty,
  serverFieldErrors,
  submitErrors,
  toDraft,
  toValues,
} from './evaluation-form.rules';

/** Fechas y horas se muestran en la zona institucional (UTC-5, sin horario de verano). */
const INSTITUTIONAL_OFFSET = '-0500';

const SUBMITTED_NOTICE = 'Esta evaluación ya fue enviada y no admite cambios.';
const CONFLICT_NOTICE =
  'Declaró un conflicto de interés: la evaluación está bloqueada y el Editor decidirá cómo continuar.';
const OVERDUE_NOTICE =
  'El plazo de evaluación venció. Su texto sigue en pantalla y el último borrador guardado se conserva, pero ya no puede guardarse ni enviarse.';

let nextId = 0;

/**
 * Formulario de evaluación estructurado (plan sección 3.5, HU-15 y HU-16).
 *
 * * Cinco puntajes (1–5), recomendación, comentarios para el Autor,
 *   comentarios confidenciales y la declaración de no tener conflicto de
 *   interés. El borrador se guarda con huecos y es privado: no se comparte
 *   con el Autor. El envío final exige todo salvo los comentarios
 *   confidenciales y es irreversible, por eso pide confirmación.
 * * Bloqueo optimista: el `ETag` de la última lectura viaja en `If-Match`.
 *   Un `409` por versión no borra nada: el Revisor elige entre usar lo
 *   guardado o conservar su texto sobre la versión más reciente. Un `409`
 *   de estado o un `410` (plazo vencido, asignación revocada, evaluación ya
 *   enviada) bloquean los campos pero **dejan el texto a la vista**.
 * * Si había cambios sin guardar, «Enviar» los guarda primero y envía con
 *   el `ETag` resultante. Si el guardado falla, no se envía nada.
 * * El contador cuenta contra el plazo del backend y al vencer bloquea
 *   guardado y envío; el corte definitivo lo aplica el servidor.
 * * Implementa `UnsavedChangesAware`: el `unsavedChangesGuard` advierte
 *   antes de abandonar el formulario con cambios sin guardar.
 */
@Component({
  selector: 'app-evaluation-form',
  imports: [
    DatePipe,
    RouterLink,
    LoadingSpinnerComponent,
    ErrorStateComponent,
    ConfirmDialogComponent,
    DeadlineCountdownComponent,
  ],
  template: `
    <section aria-labelledby="evaluation-form-title">
      <nav aria-label="Navegación de la evaluación">
        <a [routerLink]="['/app/reviewer/assignments', assignmentId]"
          >← Volver al detalle de la asignación</a
        >
      </nav>

      @if (loading()) {
        <app-loading-spinner label="Cargando la evaluación…" />
      } @else if (loadError()) {
        <app-error-state [message]="loadError()?.userMessage ?? ''" (retry)="load()" />
      } @else if (assignment(); as a) {
        <header class="form-header">
          <div>
            <p class="form-code">{{ a.manuscript.code }}</p>
            <h1 id="evaluation-form-title">Evaluación: {{ a.manuscript.title || 'Sin título' }}</h1>
          </div>
          @if (a.status === 'ACTIVE') {
            <app-deadline-countdown
              [dueAt]="a.due_at"
              [serverOffsetMs]="serverOffsetMs()"
              [overdue]="a.is_overdue"
              (expired)="deadlinePassed.set(true)"
            />
          }
        </header>

        <p class="callout callout--info" role="note">
          Revisión a doble ciego. Su borrador es privado: no se comparte con el Autor hasta que lo
          envíe, y los comentarios confidenciales solo los ve el Editor.
        </p>

        @if (lockNotice(); as notice) {
          <p class="callout callout--warning" role="status">{{ notice }}</p>
        }

        @if (submitted()) {
          <section class="callout callout--success" role="status" aria-labelledby="sent-title">
            <h2 id="sent-title">Evaluación enviada</h2>
            @if (evaluation().submitted_at; as at) {
              <p>Se registró el {{ at | date: 'dd/MM/yyyy HH:mm' : offset }}.</p>
            }
            <p>
              <a routerLink="/app/reviewer/assignments">Volver a mis asignaciones</a>
            </p>
          </section>
        }

        @if (stale()) {
          <section class="callout callout--warning" role="alert" aria-labelledby="stale-title">
            <h2 id="stale-title">El borrador cambió desde que lo abrió</h2>
            <p>
              Se guardó otra versión (por ejemplo, desde otra pestaña). Su texto sigue aquí; elija
              cómo continuar.
            </p>
            <div class="actions">
              <button type="button" class="btn btn--primary" (click)="keepMine()">
                Conservar mi texto
              </button>
              <button type="button" class="btn btn--ghost" (click)="useSaved()">
                Usar la versión guardada
              </button>
            </div>
          </section>
        }

        <form
          class="evaluation"
          novalidate
          (submit)="$event.preventDefault(); requestSubmit()"
          [attr.aria-busy]="busy()"
        >
          @if (summary().length > 0) {
            <div class="callout callout--error" role="alert" tabindex="-1">
              <p>Revise los campos marcados antes de enviar:</p>
              <ul>
                @for (item of summary(); track item.id) {
                  <li>
                    <a [href]="'#' + item.id" (click)="focus($event, item.id)">{{
                      item.message
                    }}</a>
                  </li>
                }
              </ul>
            </div>
          }

          <h2>Puntuación</h2>
          <p class="hint">
            {{ min }} = muy bajo · {{ max }} = muy alto. Puede guardar sin completar todo.
          </p>
          @for (criterion of criteria; track criterion.field) {
            <fieldset
              class="field"
              [attr.aria-describedby]="describedBy(criterion.field)"
              [attr.aria-invalid]="errorOf(criterion.field) ? 'true' : null"
            >
              <legend>{{ criterion.label }}</legend>
              <p class="hint" [id]="hintId(criterion.field)">{{ criterion.hint }}</p>
              <div class="scale">
                @for (score of scale; track score) {
                  <label class="scale__option">
                    <input
                      type="radio"
                      [id]="fieldId(criterion.field) + (score === min ? '' : '-' + score)"
                      [name]="fieldId(criterion.field)"
                      [value]="score"
                      [checked]="values()[criterion.field] === score"
                      [disabled]="readOnly()"
                      (change)="setScore(criterion.field, score)"
                    />
                    <span>{{ score }}</span>
                  </label>
                }
              </div>
              @if (errorOf(criterion.field); as message) {
                <p class="field__error" [id]="errorId(criterion.field)">{{ message }}</p>
              }
            </fieldset>
          }

          <h2>Recomendación</h2>
          <fieldset
            class="field"
            [attr.aria-describedby]="describedBy('recommendation')"
            [attr.aria-invalid]="errorOf('recommendation') ? 'true' : null"
          >
            <legend>Recomendación al Editor</legend>
            <div class="options">
              @for (option of recommendations; track option.value; let first = $first) {
                <label class="option">
                  <input
                    type="radio"
                    [id]="fieldId('recommendation') + (first ? '' : '-' + option.value)"
                    [name]="fieldId('recommendation')"
                    [value]="option.value"
                    [checked]="values().recommendation === option.value"
                    [disabled]="readOnly()"
                    (change)="setRecommendation(option.value)"
                  />
                  <span>{{ option.label }}</span>
                </label>
              }
            </div>
            @if (errorOf('recommendation'); as message) {
              <p class="field__error" [id]="errorId('recommendation')">{{ message }}</p>
            }
          </fieldset>

          <h2>Comentarios</h2>
          <div class="field">
            <label [for]="fieldId('comments_for_author')">Comentarios para el Autor</label>
            <p class="hint" [id]="hintId('comments_for_author')">
              El Autor los leerá de forma anónima. Obligatorios para enviar.
            </p>
            <textarea
              [id]="fieldId('comments_for_author')"
              rows="8"
              [maxLength]="commentMax"
              [value]="values().comments_for_author"
              [readOnly]="readOnly()"
              [attr.aria-invalid]="errorOf('comments_for_author') ? 'true' : null"
              [attr.aria-describedby]="describedBy('comments_for_author')"
              (input)="setText('comments_for_author', $any($event.target).value)"
            ></textarea>
            @if (errorOf('comments_for_author'); as message) {
              <p class="field__error" [id]="errorId('comments_for_author')">{{ message }}</p>
            }
          </div>

          <div class="field">
            <label [for]="confidentialId">Comentarios confidenciales para el Editor</label>
            <p class="hint">Solo el Editor los ve; nunca llegan al Autor. Opcionales.</p>
            <textarea
              [id]="confidentialId"
              rows="5"
              [maxLength]="commentMax"
              [value]="values().confidential_comments"
              [readOnly]="readOnly()"
              (input)="setText('confidential_comments', $any($event.target).value)"
            ></textarea>
          </div>

          <h2>Conflicto de interés</h2>
          <div class="field">
            <label class="option">
              <input
                type="checkbox"
                [id]="declarationId"
                [checked]="declared()"
                [disabled]="readOnly()"
                [attr.aria-invalid]="errorOf('declaration') ? 'true' : null"
                [attr.aria-describedby]="errorOf('declaration') ? declarationErrorId : null"
                (change)="declared.set($any($event.target).checked)"
              />
              <span>Declaro que no tengo ningún conflicto de interés con este manuscrito.</span>
            </label>
            @if (errorOf('declaration'); as message) {
              <p class="field__error" [id]="declarationErrorId">{{ message }}</p>
            }
          </div>

          @if (actionError(); as message) {
            <p class="callout callout--error" role="alert">{{ message }}</p>
          }
          @if (savedNotice(); as message) {
            <p class="callout callout--success" role="status">{{ message }}</p>
          }

          <div class="actions">
            <button
              type="button"
              class="btn btn--ghost"
              [disabled]="!canSave()"
              (click)="saveDraft()"
            >
              {{ saving() ? 'Guardando…' : 'Guardar borrador' }}
            </button>
            <button type="submit" class="btn btn--primary" [disabled]="!canSubmit()">
              {{ submitting() ? 'Enviando…' : 'Enviar evaluación' }}
            </button>
          </div>
        </form>

        <app-confirm-dialog
          title="Enviar la evaluación"
          message="El envío es definitivo: no podrá modificar la evaluación después y la asignación quedará completada. El Autor recibirá sus comentarios de forma anónima."
          confirmLabel="Enviar evaluación"
          [open]="confirmOpen()"
          (confirmed)="send()"
          (cancelled)="confirmOpen.set(false)"
        />
      }
    </section>
  `,
  styles: `
    .form-header {
      display: flex;
      flex-wrap: wrap;
      align-items: flex-start;
      justify-content: space-between;
      gap: 0.75rem;
      margin: 1rem 0;
    }
    .form-code {
      margin: 0;
      font-weight: 700;
      color: var(--gpc-primary-700);
    }
    .form-header h1 {
      margin: 0.25rem 0 0;
      overflow-wrap: anywhere;
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
    .callout--warning {
      background: var(--gpc-warning-100);
      border-color: var(--gpc-warning-800);
      color: var(--gpc-warning-800);
    }
    .callout--error {
      background: var(--gpc-danger-100);
      border-color: var(--gpc-danger-700);
      color: var(--gpc-danger-700);
    }
    .evaluation h2 {
      margin: 1.5rem 0 0.5rem;
      font-size: 1.125rem;
    }
    .field {
      display: block;
      margin: 0 0 1rem;
      padding: 0;
      border: 0;
    }
    .field legend,
    .field > label:not(.option) {
      display: block;
      padding: 0;
      font-weight: 600;
    }
    .hint {
      margin: 0.125rem 0 0.375rem;
      font-size: 0.8125rem;
      color: var(--gpc-text-muted);
    }
    .scale,
    .options {
      display: flex;
      flex-wrap: wrap;
      gap: 0.5rem 1rem;
    }
    .scale__option,
    .option {
      display: inline-flex;
      align-items: center;
      gap: 0.375rem;
      font-weight: 400;
    }
    textarea {
      display: block;
      width: 100%;
      padding: 0.5rem 0.625rem;
      border: 1px solid var(--gpc-border);
      border-radius: var(--gpc-radius);
      font: inherit;
      resize: vertical;
    }
    textarea[aria-invalid='true'] {
      border-color: var(--gpc-danger-700);
    }
    .field__error {
      margin: 0.25rem 0 0;
      color: var(--gpc-danger-700);
      font-size: 0.875rem;
    }
    .actions {
      display: flex;
      flex-wrap: wrap;
      gap: 0.75rem;
      margin: 1rem 0;
    }
  `,
})
export class EvaluationFormComponent implements UnsavedChangesAware {
  private readonly service = inject(ReviewerService);
  private readonly route = inject(ActivatedRoute);

  protected readonly assignmentId = this.route.snapshot.paramMap.get('id') ?? '';
  protected readonly offset = INSTITUTIONAL_OFFSET;
  protected readonly criteria = SCORE_CRITERIA;
  protected readonly recommendations = RECOMMENDATION_OPTIONS;
  protected readonly min = MIN_SCORE;
  protected readonly max = MAX_SCORE;
  protected readonly scale = Array.from(
    { length: MAX_SCORE - MIN_SCORE + 1 },
    (_, i) => MIN_SCORE + i,
  );
  protected readonly commentMax = COMMENT_MAX_LENGTH;

  private readonly uid = nextId++;
  protected readonly confidentialId = `evaluation-confidential-${this.uid}`;
  protected readonly declarationId = `evaluation-declaration-${this.uid}`;
  protected readonly declarationErrorId = `evaluation-declaration-error-${this.uid}`;

  protected readonly loading = signal(true);
  protected readonly loadError = signal<ApiError | null>(null);
  protected readonly assignment = signal<ReviewerAssignmentDetail | null>(null);
  protected readonly serverOffsetMs = signal(0);

  /** Último estado del servidor: sus marcas (`FINAL`, conflicto) mandan sobre lo local. */
  protected readonly evaluation = signal<ReviewerEvaluation>(emptyEvaluation());
  private readonly etag = signal<string | null>(null);

  protected readonly values = signal<EvaluationValues>(EMPTY_VALUES);
  /** Lo último guardado en el servidor; contra esto se mide «sin guardar». */
  private readonly saved = signal<EvaluationValues>(EMPTY_VALUES);
  protected readonly declared = signal(false);

  protected readonly attempted = signal(false);
  protected readonly serverErrors = signal<EvaluationErrors>({});
  protected readonly saving = signal(false);
  protected readonly submitting = signal(false);
  protected readonly confirmOpen = signal(false);
  protected readonly actionError = signal('');
  protected readonly savedNotice = signal('');

  /** El servidor rechazó por versión (`409`): hay otra versión guardada. */
  protected readonly stale = signal(false);
  /** Mensaje de un rechazo definitivo (`409` de estado o `410`): el formulario queda bloqueado. */
  private readonly serverLock = signal<string | null>(null);
  protected readonly deadlinePassed = signal(false);

  protected readonly busy = computed(() => this.saving() || this.submitting());

  protected readonly submitted = computed(
    () => this.evaluation().status === 'FINAL' || this.assignment()?.status === 'COMPLETED',
  );

  /** Por qué el formulario no admite cambios, si no los admite. */
  protected readonly lockNotice = computed<string | null>(() => {
    if (this.submitted()) {
      return this.evaluation().submitted_at ? null : SUBMITTED_NOTICE;
    }
    if (this.evaluation().conflict_declared) {
      return CONFLICT_NOTICE;
    }
    const lock = this.serverLock();
    if (lock !== null) {
      return lock;
    }
    return this.overdue() ? OVERDUE_NOTICE : null;
  });

  private readonly overdue = computed(
    () => this.deadlinePassed() || this.assignment()?.is_overdue === true,
  );

  protected readonly readOnly = computed(
    () => this.lockNotice() !== null || this.submitted() || this.busy(),
  );

  protected readonly dirty = computed(() => isDirty(this.values(), this.saved()));

  protected readonly canSave = computed(() => !this.readOnly() && !this.stale() && this.dirty());

  protected readonly canSubmit = computed(() => !this.readOnly() && !this.stale());

  private readonly localErrors = computed<EvaluationErrors>(() =>
    this.attempted() ? submitErrors(this.values(), this.declared()) : {},
  );

  protected readonly errors = computed<EvaluationErrors>(() => ({
    ...this.localErrors(),
    ...this.serverErrors(),
  }));

  /** Resumen de errores en el orden del formulario, para enlazarlos. */
  protected readonly summary = computed(() => {
    const errors = this.errors();
    const order: (EvaluationField | 'declaration')[] = [
      ...SCORE_CRITERIA.map((c) => c.field),
      'recommendation',
      'comments_for_author',
      'declaration',
    ];
    return order
      .filter((field) => errors[field])
      .map((field) => ({ id: this.fieldId(field), message: errors[field] as string }));
  });

  constructor() {
    this.load();
  }

  hasUnsavedChanges(): boolean {
    return !this.submitted() && this.dirty();
  }

  protected load(): void {
    this.loading.set(true);
    this.loadError.set(null);
    forkJoin({
      assignment: this.service.getAssignment(this.assignmentId),
      evaluation: this.service.getEvaluation(this.assignmentId),
    }).subscribe({
      next: ({ assignment, evaluation }) => {
        this.assignment.set(assignment.assignment);
        this.serverOffsetMs.set(assignment.serverOffsetMs);
        this.adopt(evaluation);
        this.loading.set(false);
      },
      error: (error: ApiError) => {
        this.loadError.set(error);
        this.loading.set(false);
      },
    });
  }

  protected fieldId(field: EvaluationField | 'declaration'): string {
    return field === 'declaration' ? this.declarationId : `evaluation-${field}-${this.uid}`;
  }

  protected errorId(field: EvaluationField): string {
    return `${this.fieldId(field)}-error`;
  }

  protected hintId(field: EvaluationField): string {
    return `${this.fieldId(field)}-hint`;
  }

  protected errorOf(field: EvaluationField | 'declaration'): string | undefined {
    return this.errors()[field];
  }

  protected describedBy(field: EvaluationField): string | null {
    const ids = [
      field === 'comments_for_author' || SCORE_CRITERIA.some((c) => c.field === field)
        ? this.hintId(field)
        : null,
      this.errorOf(field) ? this.errorId(field) : null,
    ].filter((id) => id !== null);
    return ids.length > 0 ? ids.join(' ') : null;
  }

  protected focus(event: Event, id: string): void {
    event.preventDefault();
    document.getElementById(id)?.focus();
  }

  protected setScore(field: ScoreField, score: number): void {
    this.edit({ ...this.values(), [field]: score }, field);
  }

  protected setRecommendation(value: Recommendation): void {
    this.edit({ ...this.values(), recommendation: value }, 'recommendation');
  }

  protected setText(field: 'comments_for_author' | 'confidential_comments', value: string): void {
    this.edit({ ...this.values(), [field]: value }, field);
  }

  private edit(next: EvaluationValues, field: EvaluationField | 'confidential_comments'): void {
    this.values.set(next);
    this.savedNotice.set('');
    this.actionError.set('');
    if (field !== 'confidential_comments' && this.serverErrors()[field]) {
      this.serverErrors.update(({ [field]: _removed, ...rest }) => rest);
    }
  }

  /** Guarda el borrador tal como esté: los huecos son válidos. */
  protected saveDraft(): void {
    const etag = this.etag();
    if (!this.canSave() || etag === null) {
      return;
    }
    this.saving.set(true);
    this.actionError.set('');
    this.service.saveDraft(this.assignmentId, toDraft(this.values()), etag).subscribe({
      next: (snapshot) => {
        this.saving.set(false);
        this.adopt(snapshot);
        this.savedNotice.set('Borrador guardado.');
      },
      error: (error: ApiError) => {
        this.saving.set(false);
        this.onWriteError(error);
      },
    });
  }

  /** Valida lo que exige el envío final y pide confirmación. */
  protected requestSubmit(): void {
    if (!this.canSubmit()) {
      return;
    }
    this.attempted.set(true);
    this.actionError.set('');
    if (Object.keys(this.localErrors()).length > 0) {
      return;
    }
    this.confirmOpen.set(true);
  }

  /** Guarda lo pendiente y envía con el `ETag` resultante; si guardar falla, no envía. */
  protected send(): void {
    this.confirmOpen.set(false);
    const etag = this.etag();
    if (!this.canSubmit() || etag === null) {
      return;
    }
    this.submitting.set(true);
    this.actionError.set('');
    const saved$ = this.dirty()
      ? this.service.saveDraft(this.assignmentId, toDraft(this.values()), etag).pipe(
          tap((snapshot) => this.adopt(snapshot)),
          map((snapshot) => snapshot.etag ?? etag),
        )
      : of(etag);
    saved$
      .pipe(switchMap((current) => this.service.submitEvaluation(this.assignmentId, current)))
      .subscribe({
        next: (snapshot) => {
          this.submitting.set(false);
          this.adopt(snapshot);
          this.savedNotice.set('');
        },
        error: (error: ApiError) => {
          this.submitting.set(false);
          this.onWriteError(error);
        },
      });
  }

  /** «Conservar mi texto»: toma el `ETag` vigente y deja que el Revisor vuelva a guardar. */
  protected keepMine(): void {
    this.service.getEvaluation(this.assignmentId).subscribe({
      next: (snapshot) => {
        this.etag.set(snapshot.etag);
        this.evaluation.set(snapshot.evaluation);
        this.stale.set(false);
        this.savedNotice.set('Ya puede guardar sus cambios sobre la versión más reciente.');
      },
      error: (error: ApiError) => this.actionError.set(error.userMessage),
    });
  }

  /** «Usar la versión guardada»: descarta el texto local a petición expresa del Revisor. */
  protected useSaved(): void {
    this.service.getEvaluation(this.assignmentId).subscribe({
      next: (snapshot) => {
        this.adopt(snapshot);
        this.stale.set(false);
        this.serverErrors.set({});
        this.attempted.set(false);
      },
      error: (error: ApiError) => this.actionError.set(error.userMessage),
    });
  }

  /** Toma lo que dice el servidor como lo último guardado. */
  private adopt(snapshot: EvaluationSnapshot): void {
    const values = toValues(snapshot.evaluation);
    this.evaluation.set(snapshot.evaluation);
    this.etag.set(snapshot.etag);
    this.values.set(values);
    this.saved.set(values);
    this.serverErrors.set({});
  }

  private onWriteError(error: ApiError): void {
    if (error.status === 409 && error.code === 'VERSION_CONFLICT') {
      this.stale.set(true);
      return;
    }
    if (error.status === 410) {
      this.serverLock.set(OVERDUE_NOTICE);
      return;
    }
    if (error.status === 409) {
      this.serverLock.set(error.message || error.userMessage);
      return;
    }
    if (error.status === 400) {
      this.serverErrors.set(serverFieldErrors(error.details));
      this.attempted.set(true);
      this.actionError.set(error.userMessage);
      return;
    }
    this.actionError.set(error.userMessage);
  }
}

function emptyEvaluation(): ReviewerEvaluation {
  return {
    id: null,
    status: 'DRAFT',
    originality_score: null,
    methodology_score: null,
    clarity_score: null,
    relevance_score: null,
    ethics_score: null,
    recommendation: null,
    comments_for_author: null,
    confidential_comments: null,
    conflict_declared: false,
    submitted_at: null,
  };
}
