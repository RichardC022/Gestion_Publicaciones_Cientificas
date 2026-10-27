import { DatePipe } from '@angular/common';
import {
  Component,
  ElementRef,
  booleanAttribute,
  computed,
  effect,
  input,
  output,
  viewChild,
} from '@angular/core';

import { Assignment, EligibleReviewer, isOpenAssignment } from '../../../core/models/editor.model';

/** Días calendario que tiene el Revisor para evaluar (RN-05). */
export const REVIEW_DEADLINE_DAYS = 20;

/** Fechas y horas se muestran en la zona institucional (UTC-5, sin horario de verano). */
const INSTITUTIONAL_OFFSET = '-0500';

let nextId = 0;

/**
 * Confirmación de la asignación de un Revisor (plan sección 3.5, HU-11).
 *
 * * Explica que cada manuscrito tiene **un solo Revisor** y que el plazo
 *   es de 20 días calendario.
 * * El servidor fija la fecha límite al asignar; el navegador no la
 *   calcula. Por eso el diálogo anuncia el plazo y, **una vez asignado**,
 *   muestra la fecha límite exacta que devolvió el servidor
 *   (`assignment`): es la misma que verá el Revisor.
 * * Si ya hay una asignación vigente o vencida sin revocar, lo advierte y
 *   no permite confirmar: primero hay que revocarla. Un `409` del servidor
 *   (por ejemplo, otro Editor asignó antes) llega en `error`.
 * * Es presentacional: emite `confirmed`, `cancelled` o `finished` y
 *   quien lo usa hace la llamada, indicando `busy` y mostrando `error`.
 *
 * Usa el elemento nativo `<dialog>`: el foco queda contenido y Esc cancela.
 */
@Component({
  selector: 'app-assign-reviewer-dialog',
  imports: [DatePipe],
  template: `
    <dialog
      #dialog
      class="assign-dialog"
      [attr.aria-labelledby]="titleId"
      [attr.aria-describedby]="descriptionId"
      (cancel)="onCancelRequested($event)"
    >
      @if (assignment(); as done) {
        <h2 [id]="titleId">Revisor asignado</h2>
        <div [id]="descriptionId" class="assign-dialog__body">
          <p>
            <strong>{{ done.reviewer.full_name }}</strong> evaluará {{ manuscriptCode() }}.
          </p>
          <p class="assign-dialog__deadline" role="status">
            Fecha límite:
            <strong>{{ done.due_at | date: 'dd/MM/yyyy HH:mm' : offset }}</strong>
            ({{ days }} días calendario desde la asignación).
          </p>
        </div>
        <div class="assign-dialog__actions">
          <button type="button" class="btn btn--primary" (click)="finished.emit()">Entendido</button>
        </div>
      } @else {
        <h2 [id]="titleId">Asignar Revisor</h2>

        <div [id]="descriptionId" class="assign-dialog__body">
          @if (reviewer(); as selected) {
            <p>
              Va a asignar a <strong>{{ selected.full_name }}</strong> ({{ selected.email }}) como
              único Revisor de {{ manuscriptCode() || 'este manuscrito' }}.
            </p>
          }
          <p>
            El plazo para evaluar es de <strong>{{ days }} días calendario</strong>. El servidor
            fija la fecha límite al confirmar y se la mostrará aquí.
          </p>
        </div>

        @if (existingBlocksAssignment()) {
          <p class="assign-dialog__warning" role="alert">
            @if (existing()?.status === 'EXPIRED') {
              La asignación de {{ existing()?.reviewer?.full_name }} está vencida y debe revocarse
              antes de asignar a otro Revisor.
            } @else {
              Este manuscrito ya tiene un Revisor activo ({{ existing()?.reviewer?.full_name }}).
              Solo puede haber uno: revoque su asignación antes de asignar a otro.
            }
          </p>
        }

        @if (error()) {
          <p class="assign-dialog__error" role="alert">{{ error() }}</p>
        }

        <div class="assign-dialog__actions">
          <button type="button" class="btn btn--ghost" [disabled]="busy()" (click)="dismiss()">
            Cancelar
          </button>
          <button
            type="button"
            class="btn btn--primary"
            [disabled]="busy() || existingBlocksAssignment()"
            (click)="confirm()"
          >
            {{ busy() ? 'Asignando…' : 'Confirmar asignación' }}
          </button>
        </div>
      }
    </dialog>
  `,
  styles: `
    .assign-dialog {
      width: min(30rem, calc(100vw - 2rem));
      padding: 1.5rem;
      border: 1px solid var(--gpc-border);
      border-radius: var(--gpc-radius);
      box-shadow: var(--gpc-shadow);
    }
    .assign-dialog::backdrop {
      background: rgba(23, 42, 74, 0.45);
    }
    .assign-dialog h2 {
      margin: 0 0 0.75rem;
      font-size: 1.125rem;
    }
    .assign-dialog__body p {
      margin: 0 0 0.75rem;
    }
    .assign-dialog__deadline {
      padding: 0.5rem 0.75rem;
      background: var(--gpc-success-100);
      border: 1px solid var(--gpc-success-700);
      border-radius: var(--gpc-radius);
      color: var(--gpc-success-700);
    }
    .assign-dialog__warning {
      margin: 0 0 0.75rem;
      padding: 0.5rem 0.75rem;
      background: var(--gpc-warning-100);
      border: 1px solid var(--gpc-warning-800);
      border-radius: var(--gpc-radius);
      color: var(--gpc-warning-800);
    }
    .assign-dialog__error {
      margin: 0 0 0.75rem;
      color: var(--gpc-danger-700);
      font-size: 0.875rem;
    }
    .assign-dialog__actions {
      display: flex;
      justify-content: flex-end;
      gap: 0.5rem;
    }
  `,
})
export class AssignReviewerDialogComponent {
  /** Abre o cierra el diálogo. */
  readonly open = input(false, { transform: booleanAttribute });

  /** Revisor elegido. */
  readonly reviewer = input<EligibleReviewer | null>(null);

  /** Código del manuscrito, para el texto. */
  readonly manuscriptCode = input('');

  /** Asignación vigente o vencida que ya existe, si la hay. */
  readonly existing = input<Assignment | null>(null);

  /** La asignación está en curso: se bloquean los controles. */
  readonly busy = input(false, { transform: booleanAttribute });

  /** Mensaje de error del servidor, incluido el `409`. */
  readonly error = input('');

  /** Resultado de la asignación: trae la fecha límite fijada por el servidor. */
  readonly assignment = input<Assignment | null>(null);

  /** Se dispara al confirmar la asignación. */
  readonly confirmed = output<void>();

  /** Se dispara al cancelar, incluido el cierre con Esc. */
  readonly cancelled = output<void>();

  /** Se dispara al cerrar el resultado de una asignación hecha. */
  readonly finished = output<void>();

  protected readonly days = REVIEW_DEADLINE_DAYS;
  protected readonly offset = INSTITUTIONAL_OFFSET;
  protected readonly titleId = `assign-dialog-title-${nextId}`;
  protected readonly descriptionId = `assign-dialog-description-${nextId++}`;

  protected readonly existingBlocksAssignment = computed(() => {
    const existing = this.existing();
    return existing !== null && isOpenAssignment(existing);
  });

  private readonly dialogRef = viewChild.required<ElementRef<HTMLDialogElement>>('dialog');

  constructor() {
    effect(() => {
      const dialog = this.dialogRef().nativeElement;
      if (this.open()) {
        if (!dialog.open) {
          dialog.showModal();
        }
      } else if (dialog.open) {
        dialog.close();
      }
    });
  }

  protected confirm(): void {
    if (this.busy() || this.existingBlocksAssignment()) {
      return;
    }
    this.confirmed.emit();
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
    if (this.assignment()) {
      this.finished.emit();
    } else {
      this.dismiss();
    }
  }
}
