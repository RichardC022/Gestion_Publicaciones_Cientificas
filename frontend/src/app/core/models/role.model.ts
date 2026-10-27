/**
 * Códigos de rol del sistema (`users_role.code`).
 * Los roles se revalidan contra PostgreSQL en cada solicitud; el claim
 * del JWT no autoriza por sí solo.
 */
export type Role = 'AUTHOR' | 'REVIEWER' | 'EDITOR' | 'ADMIN';

/** Etiquetas en español para mostrar en la interfaz. */
export const ROLE_LABELS: Record<Role, string> = {
  AUTHOR: 'Autor',
  REVIEWER: 'Revisor',
  EDITOR: 'Editor',
  ADMIN: 'Administrador',
};
