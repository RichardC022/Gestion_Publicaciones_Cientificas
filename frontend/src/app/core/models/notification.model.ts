import { ParamMap } from '@angular/router';

import { Paginated } from './paginated.model';

/**
 * Aviso del panel tal como lo recibe su destinatario (plan sección 2.8,
 * HU-18).
 *
 * El backend arma el `payload` con una lista blanca de campos de texto: el
 * título y el mensaje, el código y el título públicos del manuscrito, la
 * acción esperada, el plazo y un enlace dentro de la SPA. Nunca trae el id
 * del destinatario, nombres de otras personas ni comentarios confidenciales.
 */
export interface NoticePayload {
  title: string;
  message: string;
  manuscript_code: string | null;
  manuscript_title: string | null;
  action: string | null;
  due_at: string | null;
  link: string;
}

export interface Notice {
  id: string;
  event_type: string;
  payload: NoticePayload;
  is_read: boolean;
  read_at: string | null;
  created_at: string;
}

/** Página de avisos; `unread_count` cuenta todos los no leídos, aunque el filtro oculte algunos. */
export interface NoticePage extends Paginated<Notice> {
  unread_count: number;
}

/** Filtro de la lista: todos los avisos propios o solo los no leídos. */
export type NoticeFilter = 'ALL' | 'UNREAD';

export const NOTICE_FILTERS: readonly { value: NoticeFilter; label: string }[] = [
  { value: 'ALL', label: 'Todos' },
  { value: 'UNREAD', label: 'No leídos' },
];

export const DEFAULT_NOTICE_FILTER: NoticeFilter = 'ALL';

/** Filtro de la URL (`?filter=unread`); cualquier otro valor vuelve al predeterminado. */
export function toNoticeFilter(params: ParamMap): NoticeFilter {
  return params.get('filter') === 'unread' ? 'UNREAD' : DEFAULT_NOTICE_FILTER;
}

/**
 * Enlace del aviso solo si es una ruta interna de la SPA (`/app/...`). Un
 * valor ajeno —otro sitio, un esquema, una ruta relativa al protocolo— no se
 * convierte en enlace.
 */
export function internalLink(link: string | null | undefined): string | null {
  return typeof link === 'string' && /^\/app\/[^\s]*$/.test(link) && !link.includes('//')
    ? link
    : null;
}
