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
  Assignment,
  REVOCATION_CAUSES,
  RevocationCause,
  isOverdue,
} from '../../../core/models/editor.model';

/** Máximo del motivo que acepta la API. */
export const REVOCATION_REASON_MAX_LENGTH = 2000;

/** Fechas y horas se muestran en la zona institucional (UTC-5, sin horario de verano). */
const INSTITUTIONAL_OFFSET = '-0500';

let nextId = 0;

/** Lo que el diálogo entrega al confirmar: la causa y el motivo escrito. */
export interface RevocationRequest {
  cause: RevocationCause;
  reason: string;
}

/**
 * Confirmación de la revocación de una asignación (plan sección 3.5, HU-11).
 *
 * * Distingue la causa: conflicto de interés, error de asignación, cuenta
 *   inhabilitada o plazo vencido. Con el plazo vigente solo se ofrecen las
 *   tres primeras; «plazo vencido» aparece únicamente cuando la asignación
 *   ya venció (el servidor aplica la misma regla).
 * * El motivo escrito es obligatorio.
 * * Aclara las consecuencias: el manuscrito sigue en revisión pendiente de
 *   un nuevo Revisor y las evaluaciones ya escritas se conservan.
 * * Es presentacional: emite `confirmed` con la causa y el motivo y quien
 *   lo usa hace la llamada, indicando `busy` y mostrando `error`.
 *
 * La acción es destructiva, por eso el botón de confirmar es rojo.
 */
@Component({
  selector: 'app-revoke-assignment-dialog',
  imports: [FormsModule, DatePipe],
  template: `
    <dialog
      #dialog
      class="revoke-dialog"
      [attr.aria-labelledby]="titleId"
      [attr.aria-describedby]="descriptionId"
      (cancel)="onCancelRequested($event)"
    >
      <h2 [id]="titleId">Revocar asignación</h2>

      <div [id]="descriptionId" class="revoke-dialog__body">
        @if (assignment(); as current) {
          <p>
            Revisor: <strong>{{ current.reviewer.full_name }}</strong> ({{
              current.reviewer.email
            }}).
            @if (overdue()) {
              <span class="badge badge--warning">Vencida</span>
              Su plazo terminó el {{ current.due_at | date: 'dd/MM/yyyy HH:mm' : offset }}.
            } @else {
              Su plazo vence el {{ current.due_at | date: 'dd/MM/yyyy HH:mm' : offset }}.
            }
          </p>
        }
        <p>
          El manuscrito seguirá en revisión, a la espera de un nuevo Revisor. Las evaluaciones ya
          escritas se conservan.
        </p>
      </div>

      <fieldset class="revoke-dialog__field" [disabled]="busy()">
        <legend>
          Causa <span class="revoke-dialog__hint">(obligatoria)</span>
        </legend>
        @for (option of causes(); track option.value) {
          <label class="revoke-dialog__option">
            <input
              type="radio"
              name="revocation-cause"
              [value]="option.value"
              [checked]="cause() === option.value"
              (change)="cause.set(option.value)"
            />
            <span>
              <strong>{{ option.label }}</strong>
              <span class="revoke-dialog__hint">{{ option.hint }}</span>
            </span>
          </label>
        }
        @if (causeMissing()) {
          <p class="revoke-dialog__error" role="alert">Seleccione la causa de la revocación.</p>
        }
        @if (!overdue()) {
          <p class="revoke-dialog__hint">
            «Plazo vencido» solo está disponible cuando la asignación ya venció.
          </p>
        }
      </fieldset>

      <div class="revoke-dialog__field">
        <label [for]="reasonId">
          Motivo <span class="revoke-dialog__hint">(obligatorio)</span>
        </label>
        <textarea
          [id]="reasonId"
          rows="4"
          [maxlength]="maxLength"
          aria-required="true"
          [attr.aria-invalid]="reasonMissing() ? 'true' : null"
          [attr.aria-describedby]="reasonMissing() ? reasonErrorId : null"
          [disabled]="busy()"
          [ngModel]="reason()"
          (ngModelChange)="reason.set($event)"
        ></textarea>
        @if (reasonMissing()) {
          <p class="revoke-dialog__error" role="alert" [id]="reasonErrorId">
            Indique el motivo de la revocación.
          </p>
        }
      </div>

      @if (error()) {
        <p class="revoke-dialog__error" role="alert">{{ error() }}</p>
      }

      <div class="revoke-dialog__actions">
        <button type="button" class="btn btn--ghost" [disabled]="busy()" (click)="dismiss()">
          Cancelar
        </button>
        <button type="button" class="btn btn--danger" [disabled]="busy()" (click)="confirm()">
          {{ busy() ? 'Revocando…' : 'Revocar asignación' }}
        </button>
      </div>
    </dialog>
  `,
  styles: `
    .revoke-dialog {
      width: min(34rem, calc(100vw - 2rem));
      padding: 1.5rem;
      border: 1px solid var(--gpc-border);
      border-radius: var(--gpc-radius);
      box-shadow: var(--gpc-shadow);
    }
    .revoke-dialog::backdrop {
      background: rgba(23, 42, 74, 0.45);
    }
    .revoke-dialog h2 {
      margin: 0 0 0.75rem;
      font-size: 1.125rem;
    }
    .revoke-dialog__body p {
      margin: 0 0 0.75rem;
    }
    fieldset.revoke-dialog__field {
      margin: 0 0 1rem;
      padding: 0;
      border: 0;
    }
    fieldset.revoke-dialog__field legend {
      padding: 0;
      margin-bottom: 0.25rem;
      font-weight: 600;
      font-size: 0.9rem;
    }
    .revoke-dialog__option {
      display: flex;
      align-items: flex-start;
      gap: 0.5rem;
      margin: 0.25rem 0;
    }
    .revoke-dialog__option span {
      display: flex;
      flex-direction: column;
    }
    div.revoke-dialog__field {
      display: flex;
      flex-direction: column;
      gap: 0.25rem;
      margin-bottom: 1rem;
    }
    div.revoke-dialog__field label {
      font-weight: 600;
      font-size: 0.9rem;
    }
    .revoke-dialog__hint {
      font-weight: 400;
      font-size: 0.8125rem;
      color: var(--gpc-text-muted);
    }
    .revoke-dialog__field textarea {
      padding: 0.5rem 0.625rem;
      border: 1px solid var(--gpc-border);
      border-radius: var(--gpc-radius);
      font: inherit;
      resize: vertical;
    }
    .revoke-dialog__field textarea[aria-invalid='true'] {
      border-color: var(--gpc-danger-700);
    }
    .revoke-dialog__error {
      margin: 0;
      color: var(--gpc-danger-700);
      font-size: 0.875rem;
    }
    .revoke-dialog__actions {
      display: flex;
      justify-content: flex-end;
      gap: 0.5rem;
    }
  `,
})
export class RevokeAssignmentDialogComponent {
  /** Abre o cierra el diálogo. */
  readonly open = input(false, { transform: booleanAttribute });

  /** Asignación que se revocaría. */
  readonly assignment = input<Assignment | null>(null);

  /** La revocación está en curso: se bloquean los controles. */
  readonly busy = input(false, { transform: booleanAttribute });

  /** Mensaje de error del servidor, si rechazó la revocación. */
  readonly error = input('');

  /** Se dispara al confirmar, con la causa y el motivo. */
  readonly confirmed = output<RevocationRequest>();

  /** Se dispara al cancelar, incluido el cierre con Esc. */
  readonly cancelled = output<void>();

  protected readonly offset = INSTITUTIONAL_OFFSET;
  protected readonly maxLength = REVOCATION_REASON_MAX_LENGTH;
  protected readonly cause = signal<RevocationCause | null>(null);
  protected readonly reason = signal('');
  private readonly attempted = signal(false);

  protected readonly overdue = computed(() => {
    const current = this.assignment();
    return current !== null && isOverdue(current);
  });

  /** Con el plazo vigente no se ofrece «plazo vencido». */
  protected readonly causes = computed(() =>
    REVOCATION_CAUSES.filter((option) => option.early || this.overdue()),
  );

  protected readonly causeMissing = computed(() => this.attempted() && this.cause() === null);
  protected readonly reasonMissing = computed(
    () => this.attempted() && this.reason().trim() === '',
  );

  protected readonly titleId = `revoke-dialog-title-${nextId}`;
  protected readonly descriptionId = `revoke-dialog-description-${nextId}`;
  protected readonly reasonId = `revoke-dialog-reason-${nextId}`;
  protected readonly reasonErrorId = `revoke-dialog-reason-error-${nextId++}`;

  private readonly dialogRef = viewChild.required<ElementRef<HTMLDialogElement>>('dialog');

  constructor() {
    effect(() => {
      const dialog = this.dialogRef().nativeElement;
      if (this.open()) {
        if (!dialog.open) {
          // Cada apertura empieza limpia; vencida sugiere su causa natural.
          this.cause.set(this.overdue() ? 'OVERDUE' : null);
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
    const cause = this.cause();
    const reason = this.reason().trim();
    if (cause === null || reason === '') {
      return;
    }
    this.confirmed.emit({ cause, reason });
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
