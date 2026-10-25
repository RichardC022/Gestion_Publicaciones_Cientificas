import { Component, computed, input } from '@angular/core';

/** Tonos semánticos disponibles para las insignias. */
export type BadgeTone = 'neutral' | 'info' | 'success' | 'warning' | 'danger';

/** Etiquetas en español de los estados editoriales y operativos. */
export const STATUS_LABELS: Record<string, string> = {
  DRAFT: 'Borrador',
  SUBMITTED: 'Enviado',
  UNDER_REVIEW: 'En revisión',
  REQUIRES_CORRECTIONS: 'Requiere correcciones',
  ACCEPTED: 'Aceptado',
  REJECTED: 'Rechazado',
  WITHDRAWN: 'Dado de baja',
  ACTIVE: 'Activa',
  COMPLETED: 'Completada',
  REVOKED: 'Revocada',
  EXPIRED: 'Vencida',
  OPEN: 'Abierto',
  RESOLVED: 'Resuelto',
  PENDING: 'Pendiente',
  SENT: 'Enviado',
  FAILED: 'Fallido',
  FINAL: 'Final',
};

/** Tono visual de cada estado según la paleta institucional. */
const STATUS_TONES: Record<string, BadgeTone> = {
  DRAFT: 'neutral',
  SUBMITTED: 'info',
  UNDER_REVIEW: 'info',
  REQUIRES_CORRECTIONS: 'warning',
  ACCEPTED: 'success',
  REJECTED: 'danger',
  WITHDRAWN: 'neutral',
  ACTIVE: 'success',
  COMPLETED: 'success',
  REVOKED: 'danger',
  EXPIRED: 'warning',
  OPEN: 'warning',
  RESOLVED: 'success',
  PENDING: 'neutral',
  SENT: 'success',
  FAILED: 'danger',
  FINAL: 'success',
};

/**
 * Insignia semántica para estados editoriales y operativos, con
 * etiquetas en español y color consistente (plan §3.5).
 */
@Component({
  selector: 'app-status-badge',
  template: `<span [class]="'badge badge--' + tone()">{{ label() }}</span>`,
})
export class StatusBadgeComponent {
  readonly status = input.required<string>();

  protected readonly label = computed(() => STATUS_LABELS[this.status()] ?? this.status());
  protected readonly tone = computed(() => STATUS_TONES[this.status()] ?? 'neutral');
}
