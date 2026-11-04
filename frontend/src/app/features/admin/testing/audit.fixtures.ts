import { AuditEvent, AuditEventDetail } from '../../../core/models/audit.model';
import { Paginated } from '../../../core/models/paginated.model';

export const ACTOR_ID = '3f2b1c9e-8a4d-4c1e-9b7a-1d2e3f4a5b6c';
export const MANUSCRIPT_ID = '7a1d9c52-0b3e-4f6a-8c21-5e9d4b7a3f10';
export const EVENT_ID = 'c0ffee00-1234-4abc-8def-0123456789ab';
export const HASH = 'a'.repeat(64);
export const PREVIOUS_HASH = 'b'.repeat(64);

/** Evento de auditoría de ejemplo (lo que el backend deja ver al Administrador). */
export function buildEvent(overrides: Partial<AuditEvent> = {}): AuditEvent {
  return {
    id: EVENT_ID,
    occurred_at: '2026-10-22T15:30:45Z',
    actor_id: ACTOR_ID,
    actor_role: 'EDITOR',
    action: 'VERDICT_REGISTERED',
    entity_type: 'VERDICT',
    entity_id: '9d8c7b6a-5f4e-4d3c-8b2a-1f0e9d8c7b6a',
    manuscript_id: MANUSCRIPT_ID,
    manuscript_code: 'GPC-2026-000001',
    result: 'SUCCESS',
    request_id: 'req-123',
    details: { decision: 'ACCEPTED', version_number: 1, manuscript_id: MANUSCRIPT_ID },
    previous_hash: PREVIOUS_HASH,
    entry_hash: HASH,
    ...overrides,
  };
}

export function buildEventDetail(overrides: Partial<AuditEventDetail> = {}): AuditEventDetail {
  return { ...buildEvent(), ...overrides };
}

export function buildEventPage(
  results: AuditEvent[],
  count: number = results.length,
): Paginated<AuditEvent> {
  return { count, next: null, previous: null, results };
}
