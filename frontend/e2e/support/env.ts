/** Cuentas que siembra `scripts/e2e/seed_e2e.py` (misma lista, misma contraseña de la corrida). */
export type Who = 'authorReviewer' | 'author' | 'editor' | 'reviewer' | 'admin';

export const PASSWORD = process.env['E2E_PASSWORD'] ?? '';

export const ACCOUNTS: Record<Who, { id: string; name: string }> = {
  authorReviewer: { id: 'e2e-autor-revisor', name: 'Elena Cabrera Rojas' },
  author: { id: 'e2e-autor', name: 'Marcela Quizhpe Ordóñez' },
  editor: { id: 'e2e-editor', name: 'Esteban Aguirre Mora' },
  reviewer: { id: 'e2e-revisor', name: 'Rodrigo Valarezo Cueva' },
  admin: { id: 'e2e-admin', name: 'Adriana Paredes León' },
};

/** Fragmentos de identidad que jamás deben cruzar de un lado al otro del doble ciego. */
export const AUTHOR_TOKENS = ['Marcela', 'Quizhpe', 'Ordóñez', 'e2e-autor'];
export const REVIEWER_TOKENS = ['Rodrigo', 'Valarezo', 'Cueva', 'e2e-revisor'];

export const AREA = 'Agronomía';

if (!PASSWORD) {
  throw new Error('Falta E2E_PASSWORD: ejecute las pruebas con scripts/e2e.sh.');
}

/** Sufijo único por corrida para que los títulos no choquen con datos previos. */
export const RUN = Date.now().toString(36);
