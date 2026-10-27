import { Injectable, computed, signal } from '@angular/core';

import { ApiError } from '../models/api-error.model';

export type ApiFeedbackKind = 'error' | 'warning';

/** Mensaje accionable listo para renderizar (amarillo en 429, rojo en el resto). */
export interface ApiFeedback {
  status: number;
  message: string;
  kind: ApiFeedbackKind;
  retryAfterSeconds: number | null;
  requestId: string | null;
}

/**
 * Mensajes accionables de la API: el interceptor de errores publica
 * aquí los fallos de dominio (403, 404, 409, 413, 429, 5xx) y el shell
 * los renderiza (TSK-26). Los `400` se muestran junto a los formularios
 * y los `401` pertenecen al flujo de sesión, por lo que no pasan por
 * aquí.
 */
@Injectable({ providedIn: 'root' })
export class ApiFeedbackStore {
  private readonly current = signal<ApiFeedback | null>(null);

  /** Último mensaje sin cerrar; null cuando no hay ninguno. */
  readonly feedback = this.current.asReadonly();

  /** `true` mientras exista un mensaje visible. */
  readonly hasFeedback = computed(() => this.current() !== null);

  show(apiError: ApiError): void {
    this.current.set({
      status: apiError.status,
      message: apiError.userMessage,
      // 429 usa el amarillo de advertencia de la paleta institucional.
      kind: apiError.status === 429 ? 'warning' : 'error',
      retryAfterSeconds: apiError.retryAfterSeconds,
      requestId: apiError.requestId,
    });
  }

  dismiss(): void {
    this.current.set(null);
  }
}
