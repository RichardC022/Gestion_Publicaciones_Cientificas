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

let nextDialogId = 0;

/**
 * Diálogo de confirmación reutilizable para acciones críticas,
 * incluidas las destructivas (baja lógica, revocación).
 *
 * Usa el elemento nativo `<dialog>`: el foco queda contenido, la tecla
 * Esc dispara `cancelled` y el fondo no es interactivo.
 */
@Component({
  selector: 'app-confirm-dialog',
  template: `
    <dialog
      #dialog
      class="confirm-dialog"
      [attr.aria-labelledby]="titleId"
      (cancel)="onCancelRequested($event)"
    >
      <h2 class="confirm-dialog__title" [id]="titleId">{{ title() }}</h2>
      <p class="confirm-dialog__message">{{ message() }}</p>
      <div class="confirm-dialog__actions">
        <button type="button" class="btn btn--ghost" (click)="dismiss()">
          {{ cancelLabel() }}
        </button>
        <button type="button" [class]="confirmClass()" (click)="confirm()">
          {{ confirmLabel() }}
        </button>
      </div>
    </dialog>
  `,
  styles: `
    .confirm-dialog {
      width: min(28rem, calc(100vw - 2rem));
      padding: 1.5rem;
      border: 1px solid var(--gpc-border);
      border-radius: var(--gpc-radius);
      box-shadow: var(--gpc-shadow);
    }
    .confirm-dialog::backdrop {
      background: rgba(23, 42, 74, 0.45);
    }
    .confirm-dialog__title {
      margin: 0 0 0.5rem;
      font-size: 1.125rem;
    }
    .confirm-dialog__message {
      margin: 0 0 1.25rem;
      color: var(--gpc-text);
    }
    .confirm-dialog__actions {
      display: flex;
      justify-content: flex-end;
      gap: 0.5rem;
    }
  `,
})
export class ConfirmDialogComponent {
  /** Título del diálogo. */
  readonly title = input('Confirmar acción');

  /** Mensaje que describe la consecuencia de confirmar. */
  readonly message = input.required<string>();

  /** Etiqueta del botón de confirmación. */
  readonly confirmLabel = input('Confirmar');

  /** Etiqueta del botón de cancelación. */
  readonly cancelLabel = input('Cancelar');

  /** Marca la acción como destructiva (botón rojo). */
  readonly destructive = input(false, { transform: booleanAttribute });

  /** Abre o cierra el diálogo. */
  readonly open = input(false, { transform: booleanAttribute });

  /** Se dispara al confirmar la acción. */
  readonly confirmed = output<void>();

  /** Se dispara al cancelar, incluido el cierre con Esc. */
  readonly cancelled = output<void>();

  protected readonly titleId = `confirm-dialog-title-${nextDialogId++}`;

  private readonly dialogRef = viewChild.required<ElementRef<HTMLDialogElement>>('dialog');

  protected readonly confirmClass = computed(() =>
    this.destructive() ? 'btn btn--danger' : 'btn btn--primary',
  );

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
    this.dialogRef().nativeElement.close();
    this.confirmed.emit();
  }

  protected dismiss(): void {
    this.dialogRef().nativeElement.close();
    this.cancelled.emit();
  }

  protected onCancelRequested(event: Event): void {
    // Esc: evita el cierre automático para emitir el evento de cancelación.
    event.preventDefault();
    this.cancelled.emit();
    this.dialogRef().nativeElement.close();
  }
}
