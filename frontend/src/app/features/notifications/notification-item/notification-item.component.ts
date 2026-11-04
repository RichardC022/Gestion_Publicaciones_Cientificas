import { DatePipe } from '@angular/common';
import { Component, computed, input, output } from '@angular/core';
import { RouterLink } from '@angular/router';

import { Notice, internalLink } from '../../../core/models/notification.model';

/** Fechas y horas se muestran en la zona institucional (UTC-5, sin horario de verano). */
const INSTITUTIONAL_OFFSET = '-0500';

/**
 * Un aviso del panel (HU-18). Presentacional: muestra solo el contenido
 * sanitizado que envía el backend y avisa cuando el usuario lo abre o lo
 * marca como leído; quien lo usa hace la llamada.
 *
 * El enlace del aviso solo se activa si es una ruta interna de la SPA. Los
 * no leídos se distinguen por texto («Nuevo») y no solo por color.
 */
@Component({
  selector: 'app-notification-item',
  imports: [DatePipe, RouterLink],
  template: `
    <article class="notice" [class.notice--unread]="!notice().is_read">
      <header class="notice__header">
        <h2 class="notice__title">{{ notice().payload.title }}</h2>
        @if (!notice().is_read) {
          <span class="badge badge--info">Nuevo</span>
        }
        <time class="notice__time" [attr.datetime]="notice().created_at">
          {{ notice().created_at | date: 'dd/MM/yyyy HH:mm' : offset }}
        </time>
      </header>

      <p class="notice__message">{{ notice().payload.message }}</p>

      @if (hasDetails()) {
        <p class="notice__meta">
          @if (notice().payload.manuscript_code; as code) {
            <span
              >Manuscrito <strong>{{ code }}</strong>
              @if (notice().payload.manuscript_title; as title) {
                · {{ title }}
              }
            </span>
          }
          @if (notice().payload.action; as action) {
            <span>Acción: {{ action }}</span>
          }
          @if (notice().payload.due_at; as due) {
            <span>Plazo: {{ due | date: 'dd/MM/yyyy HH:mm' : offset }}</span>
          }
        </p>
      }

      <div class="notice__actions">
        @if (link(); as target) {
          <a class="btn btn--ghost" [routerLink]="target" (click)="opened.emit(notice())"
            >Ver detalle</a
          >
        }
        @if (!notice().is_read) {
          <button
            type="button"
            class="btn btn--ghost"
            [disabled]="busy()"
            (click)="markRead.emit(notice())"
          >
            Marcar como leído
          </button>
        }
      </div>
    </article>
  `,
  styles: `
    .notice {
      padding: 0.75rem 1rem;
      background: var(--gpc-surface);
      border: 1px solid var(--gpc-border);
      border-radius: var(--gpc-radius);
    }
    .notice--unread {
      border-left: 4px solid var(--gpc-primary-700);
      background: var(--gpc-primary-50);
    }
    .notice__header {
      display: flex;
      flex-wrap: wrap;
      align-items: baseline;
      gap: 0.5rem;
    }
    .notice__title {
      margin: 0;
      font-size: 1.0625rem;
    }
    .notice__time {
      margin-left: auto;
      color: var(--gpc-text-muted);
      font-size: 0.8125rem;
      font-variant-numeric: tabular-nums;
    }
    .notice__message {
      margin: 0.5rem 0;
      overflow-wrap: anywhere;
    }
    .notice__meta {
      display: flex;
      flex-wrap: wrap;
      gap: 0.25rem 1rem;
      margin: 0 0 0.5rem;
      color: var(--gpc-text-muted);
      font-size: 0.875rem;
    }
    .notice__actions {
      display: flex;
      flex-wrap: wrap;
      gap: 0.5rem;
    }
  `,
})
export class NotificationItemComponent {
  /** Aviso que se muestra. */
  readonly notice = input.required<Notice>();

  /** Marcar como leído está en curso. */
  readonly busy = input(false);

  /** El usuario abrió el enlace del aviso. */
  readonly opened = output<Notice>();

  /** El usuario pidió marcarlo como leído. */
  readonly markRead = output<Notice>();

  protected readonly offset = INSTITUTIONAL_OFFSET;

  protected readonly link = computed(() => internalLink(this.notice().payload.link));

  protected readonly hasDetails = computed(() => {
    const payload = this.notice().payload;
    return Boolean(payload.manuscript_code || payload.action || payload.due_at);
  });
}
