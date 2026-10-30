import { Notice, NoticePage, NoticePayload } from '../../../core/models/notification.model';

/** Datos de ejemplo de los avisos para las pruebas. */
export function buildNoticePayload(overrides: Partial<NoticePayload> = {}): NoticePayload {
  return {
    title: 'Nueva evaluación recibida',
    message: 'El Revisor envió su evaluación del manuscrito.',
    manuscript_code: 'GPC-2026-000001',
    manuscript_title: 'Efecto del clima en cultivos andinos',
    action: 'Registrar el veredicto',
    due_at: null,
    link: '/app/editor/submissions/s-1',
    ...overrides,
  };
}

export function buildNotice(overrides: Partial<Notice> = {}): Notice {
  return {
    id: 'n-1',
    event_type: 'EVALUATION_SUBMITTED',
    payload: buildNoticePayload(),
    is_read: false,
    read_at: null,
    created_at: '2026-11-06T15:00:00Z',
    ...overrides,
  };
}

export function buildNoticePage(
  results: Notice[],
  unreadCount: number = results.filter((n) => !n.is_read).length,
  count: number = results.length,
): NoticePage {
  return { count, next: null, previous: null, results, unread_count: unreadCount };
}
