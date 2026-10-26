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

import { ManuscriptStatus, requiresWithdrawalReason } from '../../../core/models/manuscript.model';

/** Máximo del motivo que acepta la API. */
export const WITHDRAWAL_REASON_MAX_LENGTH = 2000;

let nextId = 0;

/**
 * Confirmación de la baja lógica (plan sección 3.5, HU-08).
 *
 * * Explica qué hace la baja y, sobre todo, que **no borra nada**:
 *   versiones, evaluaciones, historial y auditoría se conservan.
 * * Pide un motivo, obligatorio cuando el manuscrito está en revisión
 *   o aceptado y opcional en los demás estados (CA-HU-08-02).
 * * Es presentacional: emite `confirmed` con el motivo y quien la usa
 *   hace la llamada, indicando `busy` y mostrando `error`.
 *
 * Usa el elemento nativo `<dialog>`: el foco queda contenido, Esc
 * cancela y el fondo no es interactivo. La acción es destructiva, por
 * eso el botón de confirmar es rojo.
 */
@Component({
  selector: 'app-withdraw-dialog',
  imports: [FormsModule],
  template: `
    <dialog
      #dialog
      class="withdraw-dialog"
      [attr.aria-labelledby]="titleId"
      [attr.aria-describedby]="descriptionId"
      (cancel)="onCancelRequested($event)"
    >
      <h2 [id]="titleId">Dar de baja {{ manuscriptCode() || 'el manuscrito' }}</h2>

      <div [id]="descriptionId" class="withdraw-dialog__body">
        <p>
          La baja lógica retira el manuscrito de los listados activos y del catálogo público.
          <strong>No se borra nada:</strong> sus versiones, evaluaciones, historial y auditoría se
          conservan, y podrá consultarlo en la vista de archivados.
        </p>
        @if (status() === 'UNDER_REVIEW') {
          <p class="withdraw-dialog__warning" role="note">
            El manuscrito está en revisión: dejará de poder evaluarse.
          </p>
        }
        @if (status() === 'ACCEPTED') {
          <p class="withdraw-dialog__warning" role="note">
            El manuscrito está aceptado: el artículo dejará de mostrarse en el catálogo público.
          </p>
        }
        <p>Esta acción no se puede deshacer desde la aplicación.</p>
      </div>

      <div class="withdraw-dialog__field">
        <label [for]="reasonId">
          Motivo de la baja
          <span class="withdraw-dialog__hint">
            ({{ reasonRequired() ? 'obligatorio' : 'opcional' }})
          </span>
        </label>
        <textarea
          [id]="reasonId"
          rows="4"
          [maxlength]="maxLength"
          [attr.aria-required]="reasonRequired()"
          [attr.aria-invalid]="reasonMissing() ? 'true' : null"
          [attr.aria-describedby]="reasonMissing() ? reasonErrorId : null"
          [disabled]="busy()"
          [ngModel]="reason()"
          (ngModelChange)="reason.set($event)"
        ></textarea>
        @if (reasonMissing()) {
          <p class="withdraw-dialog__error" role="alert" [id]="reasonErrorId">
            Indique el motivo de la baja: es obligatorio cuando el manuscrito está en revisión o ya
            fue aceptado.
          </p>
        }
      </div>

      @if (error()) {
        <p class="withdraw-dialog__error" role="alert">{{ error() }}</p>
      }

      <div class="withdraw-dialog__actions">
        <button type="button" class="btn btn--ghost" [disabled]="busy()" (click)="dismiss()">
          Cancelar
        </button>
        <button type="button" class="btn btn--danger" [disabled]="busy()" (click)="confirm()">
          {{ busy() ? 'Dando de baja…' : 'Confirmar baja' }}
        </button>
      </div>
    </dialog>
  `,
  styles: `
    .withdraw-dialog {
      width: min(32rem, calc(100vw - 2rem));
      padding: 1.5rem;
      border: 1px solid var(--gpc-border);
      border-radius: var(--gpc-radius);
      box-shadow: var(--gpc-shadow);
    }
    .withdraw-dialog::backdrop {
      background: rgba(23, 42, 74, 0.45);
    }
    .withdraw-dialog h2 {
      margin: 0 0 0.75rem;
      font-size: 1.125rem;
    }
    .withdraw-dialog__body p {
      margin: 0 0 0.75rem;
    }
    .withdraw-dialog__warning {
      padding: 0.5rem 0.75rem;
      background: var(--gpc-warning-100);
      border: 1px solid var(--gpc-warning-800);
      border-radius: var(--gpc-radius);
      color: var(--gpc-warning-800);
    }
    .withdraw-dialog__field {
      display: flex;
      flex-direction: column;
      gap: 0.25rem;
      margin-bottom: 1rem;
    }
    .withdraw-dialog__field label {
      font-weight: 600;
      font-size: 0.9rem;
    }
    .withdraw-dialog__hint {
      font-weight: 400;
      color: var(--gpc-text-muted);
    }
    .withdraw-dialog__field textarea {
      padding: 0.5rem 0.625rem;
      border: 1px solid var(--gpc-border);
      border-radius: var(--gpc-radius);
      font: inherit;
      resize: vertical;
    }
    .withdraw-dialog__field textarea[aria-invalid='true'] {
      border-color: var(--gpc-danger-700);
    }
    .withdraw-dialog__error {
      margin: 0;
      color: var(--gpc-danger-700);
      font-size: 0.875rem;
    }
    .withdraw-dialog__actions {
      display: flex;
      justify-content: flex-end;
      gap: 0.5rem;
    }
  `,
})
export class WithdrawDialogComponent {
  /** Abre o cierra el diálogo. */
  readonly open = input(false, { transform: booleanAttribute });

  /** Estado editorial del manuscrito: decide si el motivo es obligatorio. */
  readonly status = input.required<ManuscriptStatus>();

  /** Código del manuscrito, para el título. */
  readonly manuscriptCode = input('');

  /** La baja está en curso: se bloquean los controles. */
  readonly busy = input(false, { transform: booleanAttribute });

  /** Mensaje de error de la baja, si el servidor la rechazó. */
  readonly error = input('');

  /** Se dispara al confirmar, con el motivo (o `null` si no se escribió). */
  readonly confirmed = output<string | null>();

  /** Se dispara al cancelar, incluido el cierre con Esc. */
  readonly cancelled = output<void>();

  protected readonly maxLength = WITHDRAWAL_REASON_MAX_LENGTH;
  protected readonly reason = signal('');
  private readonly attempted = signal(false);

  protected readonly reasonRequired = computed(() => requiresWithdrawalReason(this.status()));
  protected readonly reasonMissing = computed(
    () => this.attempted() && this.reasonRequired() && this.reason().trim() === '',
  );

  protected readonly titleId = `withdraw-dialog-title-${nextId}`;
  protected readonly descriptionId = `withdraw-dialog-description-${nextId}`;
  protected readonly reasonId = `withdraw-dialog-reason-${nextId}`;
  protected readonly reasonErrorId = `withdraw-dialog-reason-error-${nextId++}`;

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
    const reason = this.reason().trim();
    if (this.reasonRequired() && reason === '') {
      return;
    }
    this.confirmed.emit(reason === '' ? null : reason);
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
