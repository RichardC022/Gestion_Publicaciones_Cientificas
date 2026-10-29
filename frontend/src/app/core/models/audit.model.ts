import { ParamMap } from '@angular/router';

import { Role } from './role.model';

/**
 * Auditoría global del Administrador (plan secciones 2.7 y 2.8, HU-17).
 *
 * Es lo que el backend deja ver de un evento: quién (id opaco, nunca
 * nombre ni correo), con qué rol, qué hizo, sobre qué entidad, con qué
 * resultado y cuándo, más los hashes de la cadena. No hay contenido de
 * manuscritos, comentarios confidenciales, texto libre, IP ni agente de
 * usuario; `details` ya viene filtrado por una lista blanca.
 */
export type AuditResult = 'SUCCESS' | 'DENIED' | 'FAILURE';

export interface AuditEvent {
  /** Identificador público del evento (`event_id`). */
  id: string;
  occurred_at: string;
  actor_id: string | null;
  actor_role: Role | null;
  action: string;
  entity_type: string;
  entity_id: string | null;
  manuscript_id: string | null;
  manuscript_code: string | null;
  result: AuditResult;
  request_id: string | null;
  details: Record<string, string | number | boolean | null>;
  previous_hash: string | null;
  entry_hash: string;
}

/** Resumen mínimo del veredicto de un evento de veredicto (código, decisión, fecha). */
export interface AuditVerdict {
  id: string;
  manuscript_code: string;
  decision: string;
  decided_at: string;
}

/**
 * Detalle de un evento. `can_authorize_correction` solo llega en los eventos
 * de veredicto y lo decide el backend con la misma regla del endpoint de
 * autorización: la SPA nunca lo infiere.
 */
export interface AuditEventDetail extends AuditEvent {
  can_authorize_correction?: boolean;
  verdict?: AuditVerdict;
}

/** Filtros del listado; todos opcionales y combinables. */
export interface AuditFilters {
  date_from?: string;
  date_to?: string;
  actor?: string;
  action?: string;
  manuscript?: string;
  result?: AuditResult;
}

export const AUDIT_RESULTS: ReadonlyArray<{ value: AuditResult; label: string }> = [
  { value: 'SUCCESS', label: 'Éxito' },
  { value: 'DENIED', label: 'Denegado' },
  { value: 'FAILURE', label: 'Fallo' },
];

/** Acciones auditadas que el sistema registra, con su etiqueta en español. */
export const AUDIT_ACTIONS: ReadonlyArray<{ value: string; label: string }> = [
  { value: 'LOGIN', label: 'Inicio de sesión' },
  { value: 'LOGOUT', label: 'Cierre de sesión' },
  { value: 'MANUSCRIPT_CREATED', label: 'Manuscrito creado' },
  { value: 'MANUSCRIPT_UPDATED', label: 'Manuscrito actualizado' },
  { value: 'MANUSCRIPT_DRAFT_FILE_UPLOADED', label: 'Archivo del borrador cargado' },
  { value: 'MANUSCRIPT_DRAFT_FILE_REPLACED', label: 'Archivo del borrador reemplazado' },
  { value: 'MANUSCRIPT_SUBMITTED', label: 'Manuscrito enviado' },
  { value: 'MANUSCRIPT_VERSION_SUBMITTED', label: 'Nueva versión enviada' },
  { value: 'MANUSCRIPT_WITHDRAWN', label: 'Manuscrito retirado' },
  { value: 'MANUSCRIPT_FILE_DOWNLOADED', label: 'Archivo del manuscrito descargado' },
  { value: 'ASSIGNMENT_CREATED', label: 'Revisor asignado' },
  { value: 'ASSIGNMENT_REVOKED', label: 'Asignación revocada' },
  { value: 'ASSIGNMENT_EXPIRED', label: 'Asignación vencida' },
  { value: 'EVALUATION_SUBMITTED', label: 'Evaluación enviada' },
  { value: 'CONFLICT_OF_INTEREST_DECLARED', label: 'Conflicto de interés declarado' },
  { value: 'IDENTITY_LEAK_REPORTED', label: 'Incidente reportado' },
  { value: 'INCIDENT_RESOLVED', label: 'Incidente resuelto' },
  { value: 'VERDICT_REGISTERED', label: 'Veredicto registrado' },
  { value: 'VERDICT_CORRECTION_AUTHORIZED', label: 'Corrección de veredicto autorizada' },
  { value: 'VERDICT_CORRECTED', label: 'Veredicto corregido' },
  { value: 'CATALOG_DOCUMENT_DOWNLOADED', label: 'PDF del catálogo descargado' },
  { value: 'AUDIT_QUERIED', label: 'Auditoría consultada' },
  { value: 'AUDIT_DETAIL_VIEWED', label: 'Detalle de auditoría consultado' },
];

/** Etiquetas de los campos de `details` (la lista blanca del backend). */
const DETAIL_LABELS: Readonly<Record<string, string>> = {
  assignment_id: 'Asignación',
  assignment_revoked: 'Asignación revocada',
  cause: 'Causa',
  code: 'Código',
  decision: 'Decisión',
  due_at: 'Plazo',
  is_active: 'Activo',
  lock_version: 'Versión de bloqueo',
  manuscript_id: 'Manuscrito',
  previous_status: 'Estado anterior',
  report_type: 'Tipo de reporte',
  resolution: 'Resolución',
  round_number: 'Ronda',
  status: 'Estado',
  verdict_id: 'Veredicto',
  version_number: 'Versión',
};

export const DECISION_LABELS: Readonly<Record<string, string>> = {
  ACCEPTED: 'Aceptado',
  REJECTED: 'Rechazado',
  REQUIRES_CORRECTIONS: 'Requiere correcciones',
};

export function actionLabel(action: string): string {
  return AUDIT_ACTIONS.find((option) => option.value === action)?.label ?? action;
}

export function resultLabel(result: string): string {
  return AUDIT_RESULTS.find((option) => option.value === result)?.label ?? result;
}

export function detailLabel(key: string): string {
  return DETAIL_LABELS[key] ?? key;
}

/** Valor de `details` listo para mostrar: booleanos en español y vacío como guion. */
export function detailValue(value: string | number | boolean | null): string {
  if (value === null || value === '') {
    return '—';
  }
  if (typeof value === 'boolean') {
    return value ? 'Sí' : 'No';
  }
  return String(value);
}

/** Los primeros caracteres de un hash, para la tabla (el detalle lo muestra entero). */
export function shortHash(hash: string | null): string {
  return hash ? hash.slice(0, 12) : '—';
}

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const ACTION = /^[A-Z0-9_]{1,64}$/;

/**
 * Filtros de la URL. Un valor manipulado a mano que el backend rechazaría
 * (`400`) se descarta aquí, de modo que una URL editada nunca rompe la vista.
 */
export function toAuditFilters(params: ParamMap): AuditFilters {
  const filters: AuditFilters = {};
  const dateFrom = params.get('date_from');
  const dateTo = params.get('date_to');
  if (dateFrom && ISO_DATE.test(dateFrom)) {
    filters.date_from = dateFrom;
  }
  if (dateTo && ISO_DATE.test(dateTo)) {
    filters.date_to = dateTo;
  }
  if (filters.date_from && filters.date_to && filters.date_from > filters.date_to) {
    delete filters.date_to;
  }
  for (const key of ['actor', 'manuscript'] as const) {
    const value = (params.get(key) ?? '').trim();
    if (UUID.test(value)) {
      filters[key] = value.toLowerCase();
    }
  }
  const action = (params.get('action') ?? '').trim();
  if (ACTION.test(action)) {
    filters.action = action;
  }
  const result = params.get('result');
  if (AUDIT_RESULTS.some((option) => option.value === result)) {
    filters.result = result as AuditResult;
  }
  return filters;
}

export function hasAuditFilters(filters: AuditFilters): boolean {
  return Object.keys(filters).length > 0;
}
