import {
  Component,
  ElementRef,
  booleanAttribute,
  computed,
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
  INCIDENT_DESCRIPTION_MAX_LENGTH,
  INCIDENT_REPORT_TYPES,
  IncidentReceipt,
  IncidentReportType,
} from '../../../core/models/reviewer.model';
import { ReviewerService } from '../../../core/services/reviewer.service';

let nextId = 0;

/**
 * Reporte confidencial de una posible fuga de identidad (plan sección 3.5, HU-16).
 *
 * * Es un canal **confidencial**: solo el Editor lo lee. El Autor no se
 *   entera de que existe y nada del Revisor llega a él; el diálogo lo dice
 *   expresamente. Reportar no modifica la evaluación, el PDF ni el estado
 *   del manuscrito.
 * * Pide el tipo y una descripción obligatoria.
 * * **Solo da el reporte por enviado cuando el servidor lo confirma** (`201`).
 *   Ante un error de red, un `409` (ya hay un reporte abierto) o un `503`
 *   el diálogo sigue abierto, muestra que el reporte NO se envió y conserva
 *   el texto para reintentarlo.
 * * Emite `reported` con el acuse; quien lo aloja cierra el diálogo (`open`)
 *   y avisa al Revisor.
 */
@Component({
  selector: 'app-identity-leak-dialog',
  imports: [FormsModule],
  template: `
    <dialog
      #dialog
      class="leak-dialog"
      [attr.aria-labelledby]="titleId"
      [attr.aria-describedby]="descriptionId"
      (cancel)="onCancelRequested($event)"
    >
      <h2 [id]="titleId">Reportar una posible fuga de identidad</h2>

      <div [id]="descriptionId" class="leak-dialog__body">
        <p class="leak-dialog__confidential" role="note">
          <strong>Reporte confidencial.</strong> Solo lo verá el Editor. El Autor no será informado
          ni recibirá ningún dato suyo, y su evaluación no cambia.
        </p>
      </div>

      <fieldset class="leak-dialog__field" [disabled]="busy()">
        <legend>Tipo de reporte</legend>
        @for (option of types; track option.value) {
          <label class="leak-dialog__option">
            <input
              type="radio"
              name="leak-report-type"
              [value]="option.value"
              [checked]="type() === option.value"
              (change)="type.set(option.value)"
            />
            <span>
              <strong>{{ option.label }}</strong>
              <span class="leak-dialog__hint">{{ option.hint }}</span>
            </span>
          </label>
        }
      </fieldset>

      <div class="leak-dialog__field">
        <label [for]="descriptionFieldId">
          Descripción <span class="leak-dialog__hint">(obligatoria)</span>
        </label>
        <textarea
          [id]="descriptionFieldId"
          rows="5"
          [maxlength]="maxLength"
          aria-required="true"
          [attr.aria-invalid]="descriptionMissing() ? 'true' : null"
          [attr.aria-describedby]="descriptionMissing() ? descriptionErrorId : null"
          [disabled]="busy()"
          [ngModel]="description()"
          (ngModelChange)="description.set($event)"
        ></textarea>
        @if (descriptionMissing()) {
          <p class="leak-dialog__error" role="alert" [id]="descriptionErrorId">
            Describa qué observó.
          </p>
        }
      </div>

      @if (error()) {
        <p class="leak-dialog__error" role="alert">{{ error() }}</p>
      }

      <div class="leak-dialog__actions">
        <button type="button" class="btn btn--ghost" [disabled]="busy()" (click)="dismiss()">
          Cancelar
        </button>
        <button type="button" class="btn btn--primary" [disabled]="busy()" (click)="confirm()">
          {{ busy() ? 'Enviando…' : 'Enviar reporte confidencial' }}
        </button>
      </div>
    </dialog>
  `,
  styles: `
    .leak-dialog {
      width: min(34rem, calc(100vw - 2rem));
      padding: 1.5rem;
      border: 1px solid var(--gpc-border);
      border-radius: var(--gpc-radius);
      box-shadow: var(--gpc-shadow);
    }
    .leak-dialog::backdrop {
      background: rgba(23, 42, 74, 0.45);
    }
    .leak-dialog h2 {
      margin: 0 0 0.75rem;
      font-size: 1.125rem;
    }
    .leak-dialog__confidential {
      margin: 0 0 1rem;
      padding: 0.5rem 0.75rem;
      background: var(--gpc-primary-50);
      border: 1px solid var(--gpc-primary-700);
      border-radius: var(--gpc-radius);
    }
    fieldset.leak-dialog__field {
      margin: 0 0 1rem;
      padding: 0;
      border: 0;
    }
    fieldset.leak-dialog__field legend {
      padding: 0;
      margin-bottom: 0.25rem;
      font-weight: 600;
      font-size: 0.9rem;
    }
    .leak-dialog__option {
      display: flex;
      align-items: flex-start;
      gap: 0.5rem;
      margin: 0.25rem 0;
    }
    .leak-dialog__option span {
      display: flex;
      flex-direction: column;
    }
    div.leak-dialog__field {
      display: flex;
      flex-direction: column;
      gap: 0.25rem;
      margin-bottom: 1rem;
    }
    div.leak-dialog__field label {
      font-weight: 600;
      font-size: 0.9rem;
    }
    .leak-dialog__hint {
      font-weight: 400;
      font-size: 0.8125rem;
      color: var(--gpc-text-muted);
    }
    .leak-dialog__field textarea {
      padding: 0.5rem 0.625rem;
      border: 1px solid var(--gpc-border);
      border-radius: var(--gpc-radius);
      font: inherit;
      resize: vertical;
    }
    .leak-dialog__field textarea[aria-invalid='true'] {
      border-color: var(--gpc-danger-700);
    }
    .leak-dialog__error {
      margin: 0 0 0.75rem;
      color: var(--gpc-danger-700);
      font-size: 0.875rem;
    }
    .leak-dialog__actions {
      display: flex;
      justify-content: flex-end;
      gap: 0.5rem;
    }
  `,
})
export class IdentityLeakDialogComponent {
  private readonly service = inject(ReviewerService);

  /** Asignación sobre la que se reporta. */
  readonly assignmentId = input.required<string>();

  /** Abre o cierra el diálogo. */
  readonly open = input(false, { transform: booleanAttribute });

  /** El servidor registró el reporte: trae solo el acuse. */
  readonly reported = output<IncidentReceipt>();

  /** Se dispara al cancelar, incluido el cierre con Esc. */
  readonly cancelled = output<void>();

  protected readonly types = INCIDENT_REPORT_TYPES;
  protected readonly maxLength = INCIDENT_DESCRIPTION_MAX_LENGTH;
  protected readonly type = signal<IncidentReportType>('IDENTITY_LEAK');
  protected readonly description = signal('');
  protected readonly busy = signal(false);
  protected readonly error = signal('');
  private readonly attempted = signal(false);

  protected readonly descriptionMissing = computed(
    () => this.attempted() && this.description().trim() === '',
  );

  protected readonly titleId = `leak-dialog-title-${nextId}`;
  protected readonly descriptionId = `leak-dialog-description-${nextId}`;
  protected readonly descriptionFieldId = `leak-dialog-text-${nextId}`;
  protected readonly descriptionErrorId = `leak-dialog-text-error-${nextId++}`;

  private readonly dialogRef = viewChild.required<ElementRef<HTMLDialogElement>>('dialog');

  constructor() {
    effect(() => {
      const dialog = this.dialogRef().nativeElement;
      if (this.open()) {
        if (!dialog.open) {
          // Cada apertura empieza limpia.
          this.type.set('IDENTITY_LEAK');
          this.description.set('');
          this.error.set('');
          this.attempted.set(false);
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
    this.attempted.set(true);
    const description = this.description().trim();
    if (description === '') {
      return;
    }
    this.busy.set(true);
    this.error.set('');
    this.service.reportIdentityLeak(this.assignmentId(), this.type(), description).subscribe({
      next: (receipt) => {
        this.busy.set(false);
        this.reported.emit(receipt);
      },
      error: (error: ApiError) => {
        this.busy.set(false);
        const reason = error.status === 409 ? error.message : error.userMessage;
        this.error.set(`El reporte NO se envió. ${reason}`);
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
