import { Role } from './role.model';
import { SessionUser } from './session-user.model';

/** Estado independiente de cada sección del panel (plan sección 2.2). */
export type DashboardSectionStatus = 'ok' | 'error';

/**
 * Una sección del panel unificado por rol activo.
 *
 * ``data`` llega poblada por el proveedor del dominio correspondiente
 * (Autor: TSK-32+; Revisor: TSK-60+; Editor: TSK-47+; Admin: TSK-73+)
 * y ``message`` lleva el aviso reintentable cuando la sección falló.
 */
export interface DashboardSection {
  status: DashboardSectionStatus;
  data: Record<string, unknown> | null;
  message: string | null;
}

/** Claves de sección en el orden de renderizado del panel. */
export type DashboardSectionKey = 'author' | 'reviewer' | 'editor' | 'admin';

export const DASHBOARD_SECTION_KEYS: readonly DashboardSectionKey[] = [
  'author',
  'reviewer',
  'editor',
  'admin',
];

/** Etiquetas en español de cada sección (plan sección 3.4). */
export const DASHBOARD_SECTION_LABELS: Readonly<
  Record<DashboardSectionKey, string>
> = {
  author: 'Autor',
  reviewer: 'Revisor',
  editor: 'Editor',
  admin: 'Administrador',
};

/** Respuesta única de `GET /api/dashboard/` (plan sección 2.2). */
export interface DashboardResponse {
  user: SessionUser;
  roles: Role[];
  sections: Partial<Record<DashboardSectionKey, DashboardSection>>;
}
