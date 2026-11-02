import { expect, test } from '@playwright/test';

import { Api, startReview, submitManuscript, Scenario } from './support/api';
import { AUTHOR_TOKENS, REVIEWER_TOKENS, RUN } from './support/env';
import { loginUi, visibleText } from './support/ui';

/**
 * Flujo 10: el Revisor reporta una posible fuga de identidad; el Editor pide una versión
 * anonimizada, se abre una ronda y el Autor no llega a conocer la identidad del Revisor
 * (ni siquiera que existió un reporte).
 */
test.describe('Flujo 10 — fuga de identidad', () => {
  let scenario: Scenario;

  test.beforeAll(async () => {
    const [author, editor, reviewer] = await Promise.all([
      Api.login('author'),
      Api.login('editor'),
      Api.login('reviewer'),
    ]);
    scenario = await submitManuscript(author, `Anonimización de manuscritos ${RUN}`);
    await startReview(editor, scenario.id, reviewer.userId);
    await Promise.all([author.dispose(), editor.dispose(), reviewer.dispose()]);
  });

  test('el reporte llega solo al Editor y el Autor recibe una nueva ronda sin saber del Revisor', async ({
    browser,
  }) => {
    // 1. El Revisor reporta; ve el manuscrito sin autores, pero el PDF filtró la afiliación.
    const reviewerPage = await (await browser.newContext()).newPage();
    await loginUi(reviewerPage, 'reviewer');
    await reviewerPage.goto('/app/reviewer/assignments');
    await reviewerPage.getByRole('link', { name: scenario.code, exact: true }).click();
    for (const token of AUTHOR_TOKENS) {
      expect(await visibleText(reviewerPage)).not.toContain(token);
    }
    await reviewerPage.getByRole('button', { name: 'Reportar posible fuga de identidad' }).click();
    const dialog = reviewerPage.getByRole('dialog');
    await dialog.getByRole('radio', { name: /Posible fuga de identidad/ }).check();
    await dialog
      .getByLabel(/Descripción/)
      .fill('El texto del PDF menciona la afiliación de los autores.');
    await dialog.getByRole('button', { name: 'Enviar reporte confidencial' }).click();
    await expect(
      reviewerPage.getByText(/reporte.*(enviado|registrado)|enviado.*reporte/i).first(),
    ).toBeVisible();

    // 2. El Editor lo ve, con quién reportó, y solicita una versión anonimizada.
    const editorPage = await (await browser.newContext()).newPage();
    await loginUi(editorPage, 'editor');
    await editorPage.goto('/app/editor/incidents');
    const incident = editorPage.locator('li.incident').filter({ hasText: scenario.code });
    await expect(incident).toContainText('Rodrigo Valarezo Cueva');
    await incident
      .getByRole('button', {
        name: new RegExp(`Solicitar versión anonimizada del reporte de ${scenario.code}`),
      })
      .click();
    await editorPage
      .getByRole('dialog')
      .getByRole('button', { name: 'Solicitar versión anonimizada' })
      .click();
    await expect(
      editorPage.getByText(/Versión anonimizada solicitada|ronda/i).first(),
    ).toBeVisible();

    // 3. El Autor ve una nueva ronda de correcciones y nada que identifique al Revisor.
    const authorPage = await (await browser.newContext()).newPage();
    await loginUi(authorPage, 'author');
    await authorPage.goto(`/app/author/manuscripts/${scenario.id}`);
    await expect(authorPage.getByText('Requiere correcciones').first()).toBeVisible();
    for (const path of [
      `/app/author/manuscripts/${scenario.id}`,
      `/app/author/manuscripts/${scenario.id}/history`,
      '/app/notifications',
    ]) {
      await authorPage.goto(path);
      await authorPage.waitForLoadState('networkidle');
      const seen = await visibleText(authorPage);
      // Control positivo: la página sí cargó (muestra al propio Autor), así que la ausencia es real.
      expect(seen).toContain('Marcela');
      for (const token of REVIEWER_TOKENS) {
        expect(seen, `${path} no debe contener «${token}»`).not.toContain(token);
      }
    }
    // La cuenta del Autor es compartida: se revisan solo los avisos de ESTE manuscrito.
    const notices = authorPage.locator('app-notification-item').filter({ hasText: scenario.code });
    await expect(notices.first()).toBeVisible();
    for (const text of await notices.allInnerTexts()) {
      expect(text.toLowerCase()).not.toMatch(/fuga|reporte|incidente|revisor/);
    }
    await authorPage.goto(`/app/author/manuscripts/${scenario.id}`);
    expect((await visibleText(authorPage)).toLowerCase()).not.toMatch(/fuga|reporte|incidente/);

    for (const page of [reviewerPage, editorPage, authorPage]) {
      await page.context().close();
    }
  });
});
