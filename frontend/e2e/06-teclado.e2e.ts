import { expect, test } from '@playwright/test';

import { visit } from './support/a11y';
import { ACCOUNTS, PASSWORD } from './support/env';
import { tabThrough } from './support/keyboard';
import { loginUi } from './support/ui';
import { buildWorld, screens, World } from './support/world';

/**
 * Teclado y foco (TSK-92): todo control visible se alcanza con Tab, muestra un indicador de
 * foco y los diálogos atrapan el foco y devuelven al botón que los abrió. Más un inicio de
 * sesión y una búsqueda hechos sin ratón.
 */
let world: World;
test.beforeAll(async () => {
  world = await buildWorld('Teclado');
});

test('control: el verificador detecta un control sin indicador de foco (no pasa en vacío)', async ({
  page,
}) => {
  await page.setContent(
    '<!doctype html><html lang="es"><head><title>x</title><style>button{outline:none}</style></head>' +
      '<body><main><h1>Prueba</h1><button>Sin foco visible</button><a href="#x">Con foco</a></main></body></html>',
  );
  const report = await tabThrough(page);
  expect(report.noIndicator.join()).toContain('Sin foco visible');
  expect(report.noIndicator.join()).not.toContain('Con foco');
});

test('inicio de sesión completo solo con el teclado', async ({ page }) => {
  await page.goto('/login');
  // El primer Tab puede caer en el enlace «Saltar al contenido»: el campo llega enseguida.
  const identifier = page.getByLabel('Identificador institucional');
  for (
    let i = 0;
    i < 4 && !(await identifier.evaluate((el) => el === document.activeElement));
    i++
  ) {
    await page.keyboard.press('Tab');
  }
  await expect(identifier).toBeFocused();
  await page.keyboard.type(ACCOUNTS.author.id);
  await page.keyboard.press('Tab');
  await expect(page.getByLabel('Contraseña')).toBeFocused();
  await page.keyboard.type(PASSWORD);
  await page.keyboard.press('Enter');
  await expect(page.getByRole('heading', { level: 1, name: 'Panel unificado' })).toBeVisible();
});

test('catálogo: buscar y abrir una ficha solo con el teclado', async ({ page }) => {
  await visit(page, '/catalog');
  await page.getByRole('searchbox', { name: 'Buscar' }).focus();
  await page.keyboard.type('Teclado aceptado');
  await page.keyboard.press('Enter');
  const link = page.getByRole('link', { name: new RegExp(world.accepted.title) });
  await expect(link).toBeVisible();
  await link.focus();
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(new RegExp(`/catalog/${world.accepted.code}$`));
});

const roles = ['author', 'editor', 'reviewer', 'admin'] as const;
for (const role of [null, ...roles]) {
  test(`Tab alcanza todos los controles con foco visible (${role ?? 'público'})`, async ({
    page,
  }) => {
    if (role) {
      await loginUi(page, role);
    }
    const problems: string[] = [];
    for (const screen of screens(world).filter((s) => s.role === role)) {
      await visit(page, screen.path);
      const report = await tabThrough(page);
      expect(report.total, `${screen.name}: no se encontró ningún control`).toBeGreaterThan(0);
      if (report.unreachable.length > 0) {
        problems.push(`${screen.name}: no se alcanza con Tab → ${report.unreachable.join(', ')}`);
      }
      if (report.noIndicator.length > 0) {
        problems.push(`${screen.name}: sin indicador de foco → ${report.noIndicator.join(', ')}`);
      }
    }
    expect(problems, problems.join('\n')).toEqual([]);
  });
}

test('un diálogo atrapa el foco, se cierra con Escape y devuelve el foco al botón', async ({
  page,
}) => {
  await loginUi(page, 'author');
  await visit(page, `/app/author/manuscripts/${world.submitted.id}`);
  const opener = page.getByRole('button', { name: 'Dar de baja' });
  await opener.focus();
  await page.keyboard.press('Enter');
  const dialog = page.getByRole('dialog');
  await expect(dialog).toBeVisible();

  // El foco entra al diálogo y, por muchos Tab que se den, nunca llega al contenido de fondo
  // (tras el último control un <dialog> modal cede el foco al navegador, no a la página).
  await expect(dialog.getByRole('textbox')).toBeFocused();
  for (let i = 0; i < 8; i++) {
    await page.keyboard.press('Tab');
    const behind = await dialog.evaluate((d) => {
      const active = document.activeElement;
      return !!active && active !== document.body && !d.contains(active);
    });
    expect(behind, `el Tab ${i + 1} llegó a contenido de fondo`).toBe(false);
  }
  await page.keyboard.press('Escape');
  await expect(dialog).toBeHidden();
  await expect(opener).toBeFocused();
});
