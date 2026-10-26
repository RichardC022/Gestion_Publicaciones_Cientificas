import { DatePipe } from '@angular/common';
import { Component, ElementRef, inject, input, output, signal, viewChild } from '@angular/core';
import { Subscription } from 'rxjs';

import { ApiError } from '../../../core/models/api-error.model';
import { DraftFileSummary } from '../../../core/models/manuscript.model';
import { ManuscriptService } from '../../../core/services/manuscript.service';
import { FileSizePipe } from '../../../shared/pipes/file-size.pipe';
import { validatePdfFile } from './pdf-file.validation';

/** Fechas y horas se muestran en la zona institucional (UTC-5, sin horario de verano). */
const INSTITUTIONAL_OFFSET = '-0500';

/** Respuestas en las que el archivo elegido no tiene arreglo: se descarta la selección. */
const REJECTED_STATUSES = [400, 413, 415];

/**
 * Cargador del PDF de borrador (plan sección 3.5, HU-04/HU-05).
 *
 * * Valida extensión `.pdf`, tipo MIME y 50 MB **antes** de enviar. Es
 *   solo ayuda de UX: el backend vuelve a validar todo, incluido el
 *   contenido real del archivo, y es la barrera de seguridad.
 * * Muestra el progreso y permite cancelar la carga en curso (se aborta
 *   la solicitud, sin dejar nada en el servidor).
 * * Permite **reemplazar** el borrador mientras el manuscrito sea un
 *   borrador. Subir el PDF no envía el manuscrito ni crea una versión:
 *   eso es el envío formal.
 * * Un archivo inválido o rechazado explica el motivo y deja el
 *   cargador listo para elegir otro; nunca bloquea la pantalla.
 * * El archivo nunca se guarda en el almacenamiento del navegador.
 */
@Component({
  selector: 'app-pdf-uploader',
  imports: [DatePipe, FileSizePipe],
  template: `
    <section class="uploader" aria-labelledby="pdf-uploader-title">
      <h2 id="pdf-uploader-title">PDF del manuscrito</h2>

      @if (current(); as draft) {
        <p class="uploader__current">
          Borrador actual: <strong>{{ draft.filename }}</strong> ·
          {{ draft.size_bytes | fileSize }} · adjuntado el
          {{ draft.uploaded_at | date: 'dd/MM/yyyy HH:mm' : offset }}
        </p>
      } @else {
        <p class="uploader__current">Aún no hay un PDF adjunto.</p>
      }

      <div class="uploader__picker">
        <label for="pdf-file">{{ current() ? 'Reemplazar el PDF' : 'Adjuntar el PDF' }}</label>
        <input
          #picker
          id="pdf-file"
          type="file"
          accept=".pdf,application/pdf"
          aria-describedby="pdf-file-hint"
          [attr.aria-invalid]="problem() ? 'true' : null"
          [disabled]="uploading()"
          (change)="pick($event)"
        />
        <p class="uploader__hint" id="pdf-file-hint">Solo archivos PDF, de hasta 50 MB.</p>
      </div>

      @if (problem()) {
        <p class="uploader__error" role="alert">{{ problem() }}</p>
      }

      @if (selected(); as file) {
        <div class="uploader__selected">
          <p>
            Archivo elegido: <strong>{{ file.name }}</strong> · {{ file.size | fileSize }}
          </p>
          @if (current()) {
            <p class="uploader__warning" role="note">
              Reemplazará el borrador actual ({{ current()?.filename }}). Subir el PDF no envía el
              manuscrito ni crea una versión.
            </p>
          }
          <div class="uploader__actions">
            <button
              type="button"
              class="btn btn--success"
              [disabled]="uploading()"
              (click)="upload()"
            >
              {{ uploading() ? 'Subiendo…' : current() ? 'Reemplazar PDF' : 'Subir PDF' }}
            </button>
            <button type="button" class="btn btn--ghost" (click)="cancel()">
              {{ uploading() ? 'Cancelar carga' : 'Quitar selección' }}
            </button>
          </div>
        </div>
      }

      @if (uploading()) {
        <div class="uploader__progress">
          <progress
            max="100"
            [value]="progress() ?? 0"
            [attr.aria-label]="'Progreso de la carga del PDF'"
          ></progress>
          <span aria-live="polite">{{
            progress() === null ? 'Subiendo…' : progress() + ' %'
          }}</span>
        </div>
      }

      @if (uploadError()) {
        <p class="uploader__error" role="alert">{{ uploadError() }}</p>
      }
      @if (success()) {
        <p class="uploader__success" role="status">{{ success() }}</p>
      }
    </section>
  `,
  styles: `
    .uploader {
      margin: 1rem 0;
      padding: 1rem 1.25rem;
      background: var(--gpc-surface-alt);
      border: 1px solid var(--gpc-border);
      border-radius: var(--gpc-radius);
    }
    .uploader h2 {
      margin-top: 0;
      font-size: 1.125rem;
    }
    .uploader__current {
      margin: 0 0 0.75rem;
      overflow-wrap: anywhere;
    }
    .uploader__picker {
      display: flex;
      flex-direction: column;
      gap: 0.25rem;
    }
    .uploader__picker label {
      font-weight: 600;
      font-size: 0.9rem;
    }
    .uploader__hint {
      margin: 0;
      font-size: 0.8125rem;
      color: var(--gpc-text-muted);
    }
    .uploader__selected {
      margin-top: 0.75rem;
      padding: 0.75rem 1rem;
      background: var(--gpc-primary-50);
      border: 1px solid var(--gpc-border);
      border-radius: var(--gpc-radius);
    }
    .uploader__selected p {
      margin: 0 0 0.5rem;
      overflow-wrap: anywhere;
    }
    .uploader__warning {
      padding: 0.5rem 0.75rem;
      background: var(--gpc-warning-100);
      border: 1px solid var(--gpc-warning-800);
      border-radius: var(--gpc-radius);
      color: var(--gpc-warning-800);
      font-size: 0.875rem;
    }
    .uploader__actions {
      display: flex;
      flex-wrap: wrap;
      gap: 0.5rem;
    }
    .uploader__progress {
      display: flex;
      align-items: center;
      gap: 0.75rem;
      margin-top: 0.75rem;
    }
    .uploader__progress progress {
      flex: 1;
      height: 0.75rem;
    }
    .uploader__error {
      margin: 0.75rem 0 0;
      color: var(--gpc-danger-700);
      font-size: 0.9rem;
    }
    .uploader__success {
      margin: 0.75rem 0 0;
      padding: 0.5rem 0.75rem;
      background: var(--gpc-success-100);
      border: 1px solid var(--gpc-success-700);
      border-radius: var(--gpc-radius);
      color: var(--gpc-success-700);
    }
  `,
})
export class PdfUploaderComponent {
  private readonly service = inject(ManuscriptService);

  /** Manuscrito al que se adjunta el borrador. */
  readonly manuscriptId = input.required<string>();

  /** Borrador ya adjunto, si lo hay. */
  readonly current = input<DraftFileSummary | null>(null);

  /** Se emite con el resumen del borrador cuando el servidor lo guardó. */
  readonly uploaded = output<DraftFileSummary>();

  protected readonly offset = INSTITUTIONAL_OFFSET;

  protected readonly selected = signal<File | null>(null);
  protected readonly problem = signal('');
  protected readonly uploading = signal(false);
  protected readonly progress = signal<number | null>(null);
  protected readonly uploadError = signal('');
  protected readonly success = signal('');

  private readonly picker = viewChild<ElementRef<HTMLInputElement>>('picker');
  private subscription: Subscription | null = null;

  /** Valida el archivo elegido; uno inválido se explica y se descarta. */
  protected pick(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0] ?? null;
    this.problem.set('');
    this.uploadError.set('');
    this.success.set('');

    if (file === null) {
      this.selected.set(null);
      return;
    }
    const check = validatePdfFile(file);
    if (check !== null) {
      this.selected.set(null);
      this.problem.set(check.message);
      this.resetPicker();
      return;
    }
    this.selected.set(file);
  }

  protected upload(): void {
    const file = this.selected();
    if (file === null || this.uploading()) {
      return;
    }
    this.uploading.set(true);
    this.progress.set(0);
    this.uploadError.set('');
    this.success.set('');

    this.subscription = this.service.uploadDraft(this.manuscriptId(), file).subscribe({
      next: (event) => {
        if (event.kind === 'progress') {
          this.progress.set(event.percent);
          return;
        }
        this.finish();
        this.selected.set(null);
        this.resetPicker();
        this.success.set(
          event.replaced
            ? `PDF reemplazado: ${event.draft.filename}.`
            : `PDF adjuntado: ${event.draft.filename}.`,
        );
        this.uploaded.emit(event.draft);
      },
      error: (error: ApiError) => {
        this.finish();
        this.uploadError.set(errorMessage(error));
        if (REJECTED_STATUSES.includes(error.status)) {
          // El archivo no tiene arreglo: se descarta para elegir otro.
          this.selected.set(null);
          this.resetPicker();
        }
      },
    });
  }

  /** Durante la carga la aborta; fuera de ella quita la selección. */
  protected cancel(): void {
    if (this.uploading()) {
      this.subscription?.unsubscribe();
      this.finish();
      this.uploadError.set('Carga cancelada. El PDF no se adjuntó.');
      return;
    }
    this.selected.set(null);
    this.problem.set('');
    this.resetPicker();
  }

  private finish(): void {
    this.subscription = null;
    this.uploading.set(false);
    this.progress.set(null);
  }

  /** Vacía el selector nativo para poder elegir de nuevo el mismo archivo. */
  private resetPicker(): void {
    const input = this.picker()?.nativeElement;
    if (input) {
      input.value = '';
    }
  }
}

/**
 * Mensaje del rechazo. Para un PDF inválido el backend explica el
 * motivo exacto (cifrado, sin páginas, contenido activo…); se usa tal
 * cual. El resto usa el mensaje accionable por código (413, 415…).
 */
function errorMessage(error: ApiError): string {
  if (error.code === 'PDF_INVALID' && error.message) {
    return error.message;
  }
  return error.userMessage;
}
