import {
  Component,
  ElementRef,
  booleanAttribute,
  effect,
  inject,
  input,
  output,
  signal,
  viewChild,
} from '@angular/core';
import { FormsModule } from '@angular/forms';

import { ApiError } from '../../../core/models/api-error.model';
import {
  CONFLICT_REASON_MAX_LENGTH,
  EvaluationSnapshot,
} from '../../../core/models/reviewer.model';
import { ReviewerService } from '../../../core/services/reviewer.service';

let nextId = 0;

/**
 * Declaración de conflicto de interés (plan sección 3.5, HU-16).
 *
 * * Explica las consecuencias antes de actuar: la evaluación queda
 *   bloqueada (no podrá guardar ni enviar), el Editor es avisado y decide, y
 *   la declaración no se puede deshacer. El motivo es opcional y solo lo
 *   conserva la auditoría.
 * * **Solo da el conflicto por declarado cuando el servidor lo confirma.**
 *   Ante un error (red, `409`, `503`) el diálogo sigue abierto, muestra el
 *   motivo del fallo y conserva el texto escrito.
 * * Emite `declared` con la evaluación ya bloqueada y su `ETag`; quien lo
 *   aloja cierra el diálogo (`open`) y actualiza su estado.
 * * Nunca toca datos de los autores: el conflicto se declara sin
 *   identificarlos.
 */
@Component({
  selector: 'app-conflict-dialog',
  imports: [FormsModule],
  template: `
    <dialog
      #dialog
      class="conflict-dialog"
      [attr.aria-labelledby]="titleId"
      [attr.aria-describedby]="descriptionId"
      (cancel)="onCancelRequested($event)"
    >
      <h2 [id]="titleId">Declarar conflicto de interés</h2>

      <div [id]="descriptionId" class="conflict-dialog__body">
        <p>
          Declare un conflicto si tiene un vínculo con el manuscrito o con quienes lo escribieron
          que le impida evaluarlo con imparcialidad.
        </p>
        <ul>
          <li>La evaluación quedará <strong>bloqueada</strong>: no podrá guardar ni enviar.</li>
          <li>El Editor será avisado y decidirá cómo continuar.</li>
          <li><strong>No se puede deshacer.</strong></li>
        </ul>
        @if (unsavedChanges()) {
          <p class="conflict-dialog__warning" role="note">
            Tiene cambios sin guardar en la evaluación: no se guardarán después de declarar el
            conflicto.
          </p>
        }
      </div>

      <div class="conflict-dialog__field">
        <label [for]="reasonId">
          Motivo <span class="conflict-dialog__hint">(opcional; solo lo ve el Editor)</span>
        </label>
        <textarea
          [id]="reasonId"
          rows="4"
          [maxlength]="maxLength"
          [disabled]="busy()"
          [ngModel]="reason()"
          (ngModelChange)="reason.set($event)"
        ></textarea>
      </div>

      @if (error()) {
        <p class="conflict-dialog__error" role="alert">{{ error() }}</p>
      }

      <div class="conflict-dialog__actions">
        <button type="button" class="btn btn--ghost" [disabled]="busy()" (click)="dismiss()">
          Cancelar
        </button>
        <button type="button" class="btn btn--danger" [disabled]="busy()" (click)="confirm()">
          {{ busy() ? 'Declarando…' : 'Declarar conflicto' }}
        </button>
      </div>
    </dialog>
  `,
  styles: `
    .conflict-dialog {
      width: min(32rem, calc(100vw - 2rem));
      padding: 1.5rem;
      border: 1px solid var(--gpc-border);
      border-radius: var(--gpc-radius);
      box-shadow: var(--gpc-shadow);
    }
    .conflict-dialog::backdrop {
      background: rgba(23, 42, 74, 0.45);
    }
    .conflict-dialog h2 {
      margin: 0 0 0.75rem;
      font-size: 1.125rem;
    }
    .conflict-dialog__body p {
      margin: 0 0 0.5rem;
    }
    .conflict-dialog__body ul {
      margin: 0 0 0.75rem;
      padding-left: 1.25rem;
    }
    .conflict-dialog__warning {
      padding: 0.5rem 0.75rem;
      background: var(--gpc-warning-100);
      border: 1px solid var(--gpc-warning-800);
      border-radius: var(--gpc-radius);
      color: var(--gpc-warning-800);
    }
    .conflict-dialog__field {
      display: flex;
      flex-direction: column;
      gap: 0.25rem;
      margin-bottom: 1rem;
    }
    .conflict-dialog__field label {
      font-weight: 600;
      font-size: 0.9rem;
    }
    .conflict-dialog__hint {
      font-weight: 400;
      font-size: 0.8125rem;
      color: var(--gpc-text-muted);
    }
    .conflict-dialog__field textarea {
      padding: 0.5rem 0.625rem;
      border: 1px solid var(--gpc-border);
      border-radius: var(--gpc-radius);
      font: inherit;
      resize: vertical;
    }
    .conflict-dialog__error {
      margin: 0 0 0.75rem;
      color: var(--gpc-danger-700);
      font-size: 0.875rem;
    }
    .conflict-dialog__actions {
      display: flex;
      justify-content: flex-end;
      gap: 0.5rem;
    }
  `,
})
export class ConflictDialogComponent {
  private readonly service = inject(ReviewerService);

  /** Asignación sobre la que se declara el conflicto. */
  readonly assignmentId = input.required<string>();

  /** Abre o cierra el diálogo. */
  readonly open = input(false, { transform: booleanAttribute });

  /** La evaluación tiene cambios sin guardar: se avisa de que se perderán. */
  readonly unsavedChanges = input(false, { transform: booleanAttribute });

  /** El servidor confirmó el conflicto: trae la evaluación ya bloqueada. */
  readonly declared = output<EvaluationSnapshot>();

  /** Se dispara al cancelar, incluido el cierre con Esc. */
  readonly cancelled = output<void>();

  protected readonly maxLength = CONFLICT_REASON_MAX_LENGTH;
  protected readonly reason = signal('');
  protected readonly busy = signal(false);
  protected readonly error = signal('');

  protected readonly titleId = `conflict-dialog-title-${nextId}`;
  protected readonly descriptionId = `conflict-dialog-description-${nextId}`;
  protected readonly reasonId = `conflict-dialog-reason-${nextId++}`;

  private readonly dialogRef = viewChild.required<ElementRef<HTMLDialogElement>>('dialog');

  constructor() {
    effect(() => {
      const dialog = this.dialogRef().nativeElement;
      if (this.open()) {
        if (!dialog.open) {
          // Cada apertura empieza limpia.
          this.reason.set('');
          this.error.set('');
          this.busy.set(false);
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
    this.busy.set(true);
    this.error.set('');
    this.service.declareConflict(this.assignmentId(), this.reason().trim() || null).subscribe({
      next: (snapshot) => {
        this.busy.set(false);
        this.declared.emit(snapshot);
      },
      error: (error: ApiError) => {
        this.busy.set(false);
        // El mensaje del servidor distingue «ya declarado» de «asignación cerrada».
        this.error.set(error.status === 409 ? error.message : error.userMessage);
      },
    });
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
