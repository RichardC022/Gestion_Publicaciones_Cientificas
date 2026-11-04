import { DatePipe } from '@angular/common';
import {
  Component,
  ElementRef,
  booleanAttribute,
  computed,
  effect,
  input,
  output,
  signal,
  viewChild,
} from '@angular/core';
import { FormsModule } from '@angular/forms';

import {
  AuditVerdict,
  CORRECTION_REASON_MAX_LENGTH,
  CORRECTION_REASON_MIN_LENGTH,
  DECISION_LABELS,
} from '../../../core/models/audit.model';

/** Fechas y horas se muestran en la zona institucional (UTC-5, sin horario de verano). */
const INSTITUTIONAL_OFFSET = '-0500';

let nextId = 0;

/** Error del motivo según las reglas del servidor (10 a 1000 caracteres, sin espacios sobrantes). */
export function correctionReasonError(reason: string): string | null {
  const length = reason.trim().length;
  if (length === 0) {
    return 'Indique el motivo de la habilitación.';
  }
  if (length < CORRECTION_REASON_MIN_LENGTH) {
    return `El motivo debe tener al menos ${CORRECTION_REASON_MIN_LENGTH} caracteres.`;
  }
  if (length > CORRECTION_REASON_MAX_LENGTH) {
    return `El motivo no puede superar ${CORRECTION_REASON_MAX_LENGTH} caracteres.`;
  }
  return null;
}

/**
 * Habilitación administrativa de la corrección de un veredicto (HU-13,
 * CA-HU-13-12, plan sección 3.5).
 *
 * * Pide un motivo obligatorio de 10 a 1000 caracteres.
 * * Aclara el efecto: la decisión anterior se conserva intacta y el Editor
 *   registrará una nueva; el Administrador no decide ni edita nada.
 * * Muestra solo lo mínimo del veredicto (código, decisión y fecha).
 * * Es presentacional: emite `confirmed` con el motivo y quien lo usa hace la
 *   llamada, indicando `busy` y mostrando `error`.
 */
@Component({
  selector: 'app-verdict-correction-dialog',
  imports: [FormsModule, DatePipe],
  template: `
    <dialog
      #dialog
      class="correction-dialog"
      [attr.aria-labelledby]="titleId"
      [attr.aria-describedby]="descriptionId"
      (cancel)="onCancelRequested($event)"
    >
      <h2 [id]="titleId">Habilitar corrección</h2>

      <div [id]="descriptionId" class="correction-dialog__body">
        @if (verdict(); as current) {
          <p>
            Manuscrito <strong>{{ current.manuscript_code }}</strong
            >: decisión <strong>{{ decisionLabel() }}</strong> registrada el
            {{ current.decided_at | date: 'dd/MM/yyyy HH:mm' : offset }}.
          </p>
        }
        <p>
          La decisión anterior se conserva y no se modifica. El Editor podrá registrar una nueva
          decisión una sola vez; usted no la toma.
        </p>
      </div>

      <div class="correction-dialog__field">
        <label [for]="reasonId">
          Motivo
          <span class="correction-dialog__hint"
            >(obligatorio, {{ min }} a {{ max }} caracteres)</span
          >
        </label>
        <textarea
          [id]="reasonId"
          rows="4"
          [maxlength]="max"
          aria-required="true"
          [attr.aria-invalid]="reasonError() ? 'true' : null"
          [attr.aria-describedby]="reasonError() ? reasonErrorId : null"
          [disabled]="busy()"
          [ngModel]="reason()"
          (ngModelChange)="reason.set($event)"
        ></textarea>
        @if (reasonError(); as message) {
          <p class="correction-dialog__error" role="alert" [id]="reasonErrorId">{{ message }}</p>
        }
      </div>

      @if (error()) {
        <p class="correction-dialog__error" role="alert">{{ error() }}</p>
      }

      <div class="correction-dialog__actions">
        <button type="button" class="btn btn--ghost" [disabled]="busy()" (click)="dismiss()">
          Cancelar
        </button>
        <button type="button" class="btn btn--primary" [disabled]="busy()" (click)="confirm()">
          {{ busy() ? 'Habilitando…' : 'Habilitar corrección' }}
        </button>
      </div>
    </dialog>
  `,
  styles: `
    .correction-dialog {
      width: min(34rem, calc(100vw - 2rem));
      padding: 1.5rem;
      border: 1px solid var(--gpc-border);
      border-radius: var(--gpc-radius);
      box-shadow: var(--gpc-shadow);
    }
    .correction-dialog::backdrop {
      background: rgba(23, 42, 74, 0.45);
    }
    .correction-dialog h2 {
      margin: 0 0 0.75rem;
      font-size: 1.125rem;
    }
    .correction-dialog__body p {
      margin: 0 0 0.75rem;
    }
    .correction-dialog__field {
      display: flex;
      flex-direction: column;
      gap: 0.25rem;
      margin-bottom: 1rem;
    }
    .correction-dialog__field label {
      font-weight: 600;
      font-size: 0.9rem;
    }
    .correction-dialog__hint {
      font-weight: 400;
      font-size: 0.8125rem;
      color: var(--gpc-text-muted);
    }
    .correction-dialog__field textarea {
      padding: 0.5rem 0.625rem;
      border: 1px solid var(--gpc-border);
      border-radius: var(--gpc-radius);
      font: inherit;
      resize: vertical;
    }
    .correction-dialog__field textarea[aria-invalid='true'] {
      border-color: var(--gpc-danger-700);
    }
    .correction-dialog__error {
      margin: 0 0 0.75rem;
      color: var(--gpc-danger-700);
      font-size: 0.875rem;
    }
    .correction-dialog__actions {
      display: flex;
      justify-content: flex-end;
      gap: 0.5rem;
    }
  `,
})
export class VerdictCorrectionDialogComponent {
  /** Abre o cierra el diálogo. */
  readonly open = input(false, { transform: booleanAttribute });

  /** Veredicto sobre el que se habilita la corrección. */
  readonly verdict = input<AuditVerdict | null>(null);

  /** La habilitación está en curso: se bloquean los controles. */
  readonly busy = input(false, { transform: booleanAttribute });

  /** Mensaje de error del servidor, si rechazó la habilitación. */
  readonly error = input('');

  /** Se dispara al confirmar, con el motivo ya sin espacios sobrantes. */
  readonly confirmed = output<string>();

  /** Se dispara al cancelar, incluido el cierre con Esc. */
  readonly cancelled = output<void>();

  protected readonly offset = INSTITUTIONAL_OFFSET;
  protected readonly min = CORRECTION_REASON_MIN_LENGTH;
  protected readonly max = CORRECTION_REASON_MAX_LENGTH;
  protected readonly reason = signal('');
  private readonly attempted = signal(false);

  protected readonly decisionLabel = computed(() => {
    const decision = this.verdict()?.decision ?? '';
    return DECISION_LABELS[decision] ?? decision;
  });

  protected readonly reasonError = computed(() =>
    this.attempted() ? correctionReasonError(this.reason()) : null,
  );

  protected readonly titleId = `correction-dialog-title-${nextId}`;
  protected readonly descriptionId = `correction-dialog-description-${nextId}`;
  protected readonly reasonId = `correction-dialog-reason-${nextId}`;
  protected readonly reasonErrorId = `correction-dialog-reason-error-${nextId++}`;

  private readonly dialogRef = viewChild.required<ElementRef<HTMLDialogElement>>('dialog');

  constructor() {
    effect(() => {
      const dialog = this.dialogRef().nativeElement;
      if (this.open()) {
        if (!dialog.open) {
          // Cada apertura empieza limpia.
          this.reason.set('');
          this.attempted.set(false);
          dialog.showModal();
        }
      } else if (dialog.open) {
        dialog.close();
      }
    });
  }

  protected confirm(): void {
    if (this.busy()) {
      return;
    }
    this.attempted.set(true);
    if (correctionReasonError(this.reason()) !== null) {
      return;
    }
    this.confirmed.emit(this.reason().trim());
  }

  protected dismiss(): void {
    if (this.busy()) {
      return;
    }
    this.cancelled.emit();
  }

  protected onCancelRequested(event: Event): void {
    // Esc: el contenedor decide cuándo cerrar (a través de `open`).
    event.preventDefault();
    this.dismiss();
  }
}
