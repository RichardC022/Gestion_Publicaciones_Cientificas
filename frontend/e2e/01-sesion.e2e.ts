import { expect, test } from '@playwright/test';

import { ACCOUNTS, PASSWORD } from './support/env';
import { loginUi, logoutUi } from './support/ui';

/** Flujo 1: login de una persona con dos roles; el panel muestra ambas secciones a la vez. */
test.describe('Flujo 1 — sesión y panel multirrol', () => {
  test('una persona Autor y Revisor ve las dos secciones sin elegir rol', async ({ page }) => {
    await loginUi(page, 'authorReviewer');

    const nav = page.getByRole('navigation', { name: 'Navegación principal' });
    await expect(nav.getByRole('link', { name: 'Mis manuscritos' })).toBeVisible();
    await expect(nav.getByRole('link', { name: 'Mis asignaciones' })).toBeVisible();
    // Sin roles de Editor ni de Administrador, esos módulos no aparecen.
    await expect(nav.getByRole('link', { name: 'Nuevos envíos' })).toHaveCount(0);
    await expect(nav.getByRole('link', { name: 'Auditoría' })).toHaveCount(0);

    const dashboard = page.getByRole('region', { name: 'Panel unificado' });
    await expect(dashboard.getByRole('heading', { name: 'Autor' })).toBeVisible();
    await expect(dashboard.getByRole('heading', { name: 'Revisor' })).toBeVisible();
    await expect(dashboard.getByRole('heading', { name: 'Editor' })).toHaveCount(0);

    // No existe selector ni conmutador de rol.
    await expect(page.getByRole('button', { name: /cambiar de rol|seleccionar rol/i })).toHaveCount(
      0,
    );

    await logoutUi(page);
  });

  test('una contraseña errónea da un mensaje genérico que no revela si la cuenta existe', async ({
    page,
  }) => {
    await page.goto('/login');
    await page.getByLabel('Identificador institucional').fill(ACCOUNTS.author.id);
    await page.getByLabel('Contraseña').fill(`${PASSWORD}-mal`);
    await page.getByRole('button', { name: 'Ingresar' }).click();
    const wrong = await page.getByRole('alert').filter({ hasText: /./ }).first().innerText();

    await page.getByLabel('Identificador institucional').fill('no-existe-e2e');
    await page.getByRole('button', { name: 'Ingresar' }).click();
    await expect(page.getByRole('alert').filter({ hasText: wrong })).toBeVisible();
    await expect(page).toHaveURL(/\/login$/);
  });

  test('una ruta de otro módulo da acceso denegado y sin sesión se pide iniciar sesión', async ({
    page,
  }) => {
    await page.goto('/app/admin/audit');
    await expect(page).toHaveURL(/\/login/);

    await loginUi(page, 'author');
    await page.goto('/app/admin/audit');
    await expect(page.getByRole('heading', { name: 'Acceso denegado' })).toBeVisible();
  });
});
