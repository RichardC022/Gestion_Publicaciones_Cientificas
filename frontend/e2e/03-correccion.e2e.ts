import { expect, test } from '@playwright/test';

import { Api, evaluate, judge, startReview, submitManuscript, Scenario } from './support/api';
import { RUN } from './support/env';
import { filterAudit, loginUi } from './support/ui';

/**
 * Flujo 9: el Administrador habilita una corrección sobre el último veredicto, el Editor
 * registra la nueva decisión y el historial conserva AMBAS, cada una con su auditoría.
 * El escenario (un manuscrito rechazado) se prepara por la API; lo probado va por pantalla.
 */
test.describe('Flujo 9 — corrección administrativa de un veredicto', () => {
  let scenario: Scenario;

  test.beforeAll(async () => {
    const [author, editor, reviewer] = await Promise.all([
      Api.login('author'),
      Api.login('editor'),
      Api.login('reviewer'),
    ]);
    scenario = await submitManuscript(author, `Corrección de veredicto ${RUN}`);
    await startReview(editor, scenario.id, reviewer.userId);
    await evaluate(reviewer, scenario.id, { recommendation: 'REJECT' });
    await judge(editor, scenario.id, {
      decision: 'REJECTED',
      justification: 'La metodología no sostiene las conclusiones del estudio.',
    });
    await Promise.all([author.dispose(), editor.dispose(), reviewer.dispose()]);
  });

  test('el Administrador habilita, el Editor corrige y el historial conserva las dos decisiones', async ({
    browser,
  }) => {
    // 1. El Administrador abre el evento «Veredicto registrado» y habilita la corrección.
    const adminPage = await (await browser.newContext()).newPage();
    await loginUi(adminPage, 'admin');
    await adminPage.goto('/app/admin/audit');
    await filterAudit(adminPage, 'VERDICT_REGISTERED', scenario.id);
    await adminPage
      .getByRole('link', { name: /Ver detalle/ })
      .first()
      .click();

    await adminPage.getByRole('button', { name: 'Habilitar corrección' }).click();
    const dialog = adminPage.getByRole('dialog');
    await dialog
      .getByLabel(/Motivo/)
      .fill('El veredicto se registró sobre la evaluación equivocada.');
    await dialog.getByRole('button', { name: 'Habilitar corrección' }).click();
    await expect(adminPage.getByText(/Corrección habilitada/)).toBeVisible();

    // 2. El Editor registra la decisión corregida.
    const editorPage = await (await browser.newContext()).newPage();
    await loginUi(editorPage, 'editor');
    await editorPage.goto(`/app/editor/submissions/${scenario.id}`);
    await expect(editorPage.getByRole('heading', { name: 'Corrección autorizada' })).toBeVisible();
    await editorPage.getByRole('radio', { name: /^Aceptado/ }).check();
    // Se aparta de la recomendación del Revisor (Rechazar): la justificación es obligatoria.
    await editorPage
      .getByLabel(/Justificación/)
      .fill('Tras revisar la evaluación completa, el estudio sí sostiene sus conclusiones.');
    await editorPage.getByRole('button', { name: 'Registrar decisión corregida' }).click();
    await editorPage
      .getByRole('dialog')
      .getByRole('button', { name: 'Registrar decisión corregida' })
      .click();

    // 3. El historial conserva el veredicto original y el corregido.
    const history = editorPage.locator('.verdict__history li');
    await expect(history).toHaveCount(2);
    await expect(history.first()).toContainText('Rechazado');
    await expect(history.first()).toContainText('sustituida por una decisión posterior');
    await expect(history.last()).toContainText('Aceptado');
    await expect(history.last()).toContainText('decisión corregida');

    // 4. Y la auditoría tiene las tres huellas, sin que ninguna se haya borrado.
    const trail: [string, string][] = [
      ['VERDICT_REGISTERED', 'Veredicto registrado'],
      ['VERDICT_CORRECTION_AUTHORIZED', 'Corrección de veredicto autorizada'],
      ['VERDICT_CORRECTED', 'Veredicto corregido'],
    ];
    await adminPage
      .getByRole('navigation', { name: 'Navegación principal' })
      .getByRole('link', { name: 'Auditoría' })
      .click();
    for (const [action, label] of trail) {
      await filterAudit(adminPage, action, scenario.id);
      const rows = adminPage
        .getByRole('row')
        .filter({ has: adminPage.getByRole('cell', { name: new RegExp(`^${label}`) }) });
      await expect(rows).toHaveCount(1);
      await expect(rows.first()).toContainText(scenario.code);
    }
    await adminPage.context().close();
    await editorPage.context().close();
  });
});
