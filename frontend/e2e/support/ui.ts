import { expect, Page } from '@playwright/test';

import { ACCOUNTS, PASSWORD, Who } from './env';

/** Inicia sesión por la pantalla real y espera el panel. */
export async function loginUi(page: Page, who: Who): Promise<void> {
  await page.goto('/login');
  await page.getByLabel('Identificador institucional').fill(ACCOUNTS[who].id);
  await page.getByLabel('Contraseña').fill(PASSWORD);
  await page.getByRole('button', { name: 'Ingresar' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Panel unificado' })).toBeVisible();
}

export async function logoutUi(page: Page): Promise<void> {
  await page.getByRole('button', { name: 'Cerrar sesión' }).click();
  await expect(page).toHaveURL(/\/login$/);
}

/** Texto completo visible de la página (para comprobar que no hay identidades). */
export async function visibleText(page: Page): Promise<string> {
  return page.locator('body').innerText();
}

/**
 * Filtra la auditoría por acción (código) y manuscrito SIN recargar la página:
 * cada recarga completa de la SPA rota la cookie de sesión y encadenarlas es frágil.
 */
export async function filterAudit(page: Page, action: string, manuscriptId: string): Promise<void> {
  await page.getByLabel('Acción').fill(action);
  await page.getByLabel('Manuscrito (id)').fill(manuscriptId);
  await page.getByRole('button', { name: 'Filtrar' }).click();
}
