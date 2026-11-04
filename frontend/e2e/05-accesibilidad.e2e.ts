import { expect, Page, test } from '@playwright/test';

import { describeFindings, scan, visit } from './support/a11y';
import { RUN } from './support/env';
import { loginUi } from './support/ui';
import { buildWorld, World } from './support/world';

/**
 * Accesibilidad (TSK-92): axe-core con WCAG 2.x A/AA —contraste incluido— sobre las
 * pantallas de cada rol, con datos reales y con los diálogos abiertos.
 */
let world: World;
test.beforeAll(async () => {
  world = await buildWorld('Accesibilidad');
});

/** Acumula los hallazgos de una prueba y los reporta todos juntos al final. */
function collector() {
  const found: string[] = [];
  return {
    async check(page: Page, name: string): Promise<void> {
      const result = await scan(page);
      if (result.length > 0) {
        found.push(`${name}\n${describeFindings(result)}`);
      }
    },
    done(): void {
      expect(found, `Violaciones WCAG A/AA:\n${found.join('\n')}`).toEqual([]);
    },
  };
}

test('control: axe detecta un contraste insuficiente (la prueba no pasa en vacío)', async ({
  page,
}) => {
  await page.setContent(
    '<!doctype html><html lang="es"><head><title>x</title></head><body><main><h1>Prueba</h1>' +
      '<p style="color:#bbbbbb;background:#ffffff">Texto de bajo contraste</p></main></body></html>',
  );
  const rules = (await scan(page)).map((f) => f.rule);
  expect(rules).toContain('color-contrast');
});

test('público', async ({ page }) => {
  const c = collector();
  await visit(page, '/login');
  await c.check(page, 'login');
  await visit(page, '/catalog');
  await c.check(page, 'catálogo');
  await visit(page, `/catalog/${world.accepted.code}`);
  await c.check(page, 'ficha del catálogo');
  c.done();
});

test('Autor', async ({ page }) => {
  const c = collector();
  await loginUi(page, 'author');
  await c.check(page, 'panel del autor');
  for (const [name, path] of [
    ['mis manuscritos', '/app/author/manuscripts'],
    ['nuevo manuscrito', '/app/author/manuscripts/new'],
    ['detalle enviado', `/app/author/manuscripts/${world.submitted.id}`],
    ['detalle borrador', `/app/author/manuscripts/${world.draftId}`],
    ['editar borrador', `/app/author/manuscripts/${world.draftId}/edit`],
    ['historial', `/app/author/manuscripts/${world.submitted.id}/history`],
    ['avisos', '/app/notifications'],
  ]) {
    await visit(page, path);
    await c.check(page, `autor: ${name}`);
  }
  await visit(page, `/app/author/manuscripts/${world.submitted.id}`);
  await page.getByRole('button', { name: 'Dar de baja' }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await c.check(page, 'autor: diálogo de baja');
  c.done();
});

test('Editor', async ({ page }) => {
  const c = collector();
  await loginUi(page, 'editor');
  await c.check(page, 'panel del editor');
  for (const [name, path] of [
    ['bandeja', '/app/editor/submissions'],
    ['detalle enviado', `/app/editor/submissions/${world.submitted.id}`],
    ['detalle en revisión', `/app/editor/submissions/${world.pending.id}`],
    ['detalle aceptado', `/app/editor/submissions/${world.accepted.id}`],
    ['vencidas', '/app/editor/assignments/expired'],
    ['incidentes', '/app/editor/incidents'],
  ]) {
    await visit(page, path);
    await c.check(page, `editor: ${name}`);
  }
  await visit(page, `/app/editor/submissions/${world.submitted.id}`);
  await page.getByRole('button', { name: 'Pasar a revisión' }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await c.check(page, 'editor: diálogo de pasar a revisión');
  c.done();
});

test('Revisor', async ({ page }) => {
  const c = collector();
  await loginUi(page, 'reviewer');
  await c.check(page, 'panel del revisor');
  await visit(page, '/app/reviewer/assignments');
  await c.check(page, 'revisor: asignaciones');
  await page.getByRole('link', { name: world.pending.code, exact: true }).click();
  await expect(page.locator('h1').first()).toBeVisible();
  await c.check(page, 'revisor: detalle');
  await page.getByRole('link', { name: 'Evaluar manuscrito' }).click();
  await expect(page.locator('h1').first()).toBeVisible();
  await c.check(page, 'revisor: formulario de evaluación');
  await page.getByRole('button', { name: 'Reportar posible fuga de identidad' }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await c.check(page, 'revisor: diálogo de fuga');
  await visit(page, '/app/reviewer/history');
  await c.check(page, 'revisor: historial');
  c.done();
});

test('Administrador', async ({ page }) => {
  const c = collector();
  await loginUi(page, 'admin');
  await c.check(page, 'panel del administrador');
  await visit(page, '/app/admin/audit');
  await c.check(page, 'admin: auditoría');
  await page
    .getByRole('link', { name: /Ver detalle/ })
    .first()
    .click();
  await expect(page.locator('h1').first()).toBeVisible();
  await c.check(page, 'admin: detalle del evento');
  c.done();
});
