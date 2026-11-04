import { expect, test } from '@playwright/test';

import { ACCOUNTS, AREA, AUTHOR_TOKENS, REVIEWER_TOKENS, RUN } from './support/env';
import { makePdf } from './support/pdf';
import { filterAudit, loginUi, visibleText } from './support/ui';

/**
 * Flujos 2 a 8 como UNA historia, de punta a punta por las pantallas reales:
 * el Autor envía, el Editor asigna, el Revisor evalúa, el Editor acepta, el público lo
 * encuentra y descarga, el Autor lo retira y el Administrador ve la huella en la auditoría.
 */
test.describe.configure({ mode: 'serial' });

test.describe('Flujos 2 a 8 — del envío al retiro', () => {
  const title = `Glaciares tropicales del Chimborazo ${RUN}`;
  let code = '';
  let manuscriptUrl = '';
  let manuscriptId = '';

  test('2. El Autor crea el borrador, adjunta el PDF, lo envía y recibe el código', async ({
    page,
  }) => {
    await loginUi(page, 'author');
    await page.goto('/app/author/manuscripts/new');

    await page.getByLabel('Título').fill(title);
    await page
      .getByLabel('Resumen')
      .fill('Estudio del retroceso glaciar en el volcán durante dos décadas.');
    await page.getByLabel('Palabras clave').fill('glaciares, clima');
    await page.getByLabel('Área de conocimiento').fill(AREA);
    await page.getByLabel('Idioma (código de dos letras)').fill('es');
    await page.getByLabel('Filiación').first().fill('Universidad Nacional de Loja');
    await page.getByRole('button', { name: 'Guardar borrador' }).click();

    await expect(page).toHaveURL(/\/app\/author\/manuscripts\/[0-9a-f-]{36}$/);
    manuscriptUrl = new URL(page.url()).pathname;
    manuscriptId = manuscriptUrl.split('/').pop() ?? '';
    await expect(page.getByRole('heading', { level: 1, name: title })).toBeVisible();

    await page.locator('#pdf-file').setInputFiles({
      name: 'mi-articulo.pdf',
      mimeType: 'application/pdf',
      buffer: makePdf(`ciclo-${RUN}`),
    });
    await page.locator('.uploader__actions .btn--success').click();
    await expect(page.getByText('mi-articulo.pdf').first()).toBeVisible();

    await page.getByRole('button', { name: 'Enviar manuscrito' }).click();
    await page.getByRole('dialog').getByRole('button', { name: 'Enviar manuscrito' }).click();

    const confirmation = page.getByRole('status').filter({ hasText: 'Código de seguimiento' });
    await expect(confirmation).toBeVisible();
    code = (
      await confirmation.locator('dt:has-text("Código de seguimiento") + dd').innerText()
    ).trim();
    expect(code).toMatch(/^GPC-\d{4}-\d{6}$/);
    await expect(confirmation).toContainText('v1');
  });

  test('3. El Editor ve el envío, lo pasa a revisión, asigna al Revisor y verifica el plazo', async ({
    page,
  }) => {
    await loginUi(page, 'editor');
    await page.goto('/app/editor/submissions');
    await page.getByRole('searchbox', { name: 'Buscar' }).fill(code);
    await page.getByRole('button', { name: 'Filtrar' }).click();
    await page.getByRole('link', { name: code, exact: true }).click();

    await expect(page.getByRole('heading', { level: 1, name: title })).toBeVisible();
    await page.getByRole('button', { name: 'Pasar a revisión' }).click();
    await page.getByRole('dialog').getByRole('button', { name: 'Pasar a revisión' }).click();

    await page.getByRole('button', { name: 'Asignar Revisor' }).click();
    await page.getByRole('button', { name: `Seleccionar a ${ACCOUNTS.reviewer.name}` }).click();
    const dialog = page.getByRole('dialog');
    await dialog.getByRole('button', { name: 'Confirmar asignación' }).click();

    await expect(dialog.getByRole('heading', { name: 'Revisor asignado' })).toBeVisible();
    await expect(dialog).toContainText(ACCOUNTS.reviewer.name);
    await expect(dialog).toContainText('20 días');
    await dialog.getByRole('button', { name: 'Entendido' }).click();
    await expect(page.getByText(/Fecha límite/).first()).toBeVisible();
  });

  test('4. El Revisor ve el manuscrito anonimizado, descarga el PDF sanitizado y envía su evaluación', async ({
    page,
  }) => {
    await loginUi(page, 'reviewer');
    await page.goto('/app/reviewer/assignments');
    await page.getByRole('link', { name: code, exact: true }).click();

    await expect(page.getByRole('heading', { level: 1, name: title })).toBeVisible();
    const pdf = page.waitForResponse((r) =>
      /\/reviewer\/assignments\/.+\/document\//.test(r.url()),
    );
    await page.getByRole('button', { name: 'Descargar PDF' }).click();
    const response = await pdf;
    expect(response.status()).toBe(200);
    expect(response.headers()['content-type']).toContain('application/pdf');

    // Doble ciego: ni el Autor ni su correo aparecen en lo que ve el Revisor.
    const seen = await visibleText(page);
    for (const token of AUTHOR_TOKENS) {
      expect(seen).not.toContain(token);
    }

    await page.getByRole('link', { name: 'Evaluar manuscrito' }).click();
    for (const [criterion, score] of [
      ['Originalidad', '4'],
      ['Metodología', '4'],
      ['Claridad', '5'],
      ['Relevancia', '4'],
      ['Ética', '5'],
    ]) {
      await page
        .getByRole('group', { name: new RegExp(`^${criterion}`) })
        .getByText(score, { exact: true })
        .click();
    }
    await page.getByRole('radio', { name: 'Aceptar', exact: true }).check();
    await page.getByLabel('Comentarios para el Autor').fill('Trabajo sólido, con matices menores.');
    await page
      .getByLabel('Comentarios confidenciales para el Editor')
      .fill('Sin observaciones adicionales.');
    await page
      .getByLabel('Declaro que no tengo ningún conflicto de interés con este manuscrito.')
      .check();
    await page.getByRole('button', { name: 'Enviar evaluación' }).click();
    await page.getByRole('dialog').getByRole('button', { name: 'Enviar evaluación' }).click();

    await expect(
      page.getByText(/evaluación (fue )?enviada|Evaluación enviada/i).first(),
    ).toBeVisible();
  });

  test('5. El Editor registra el veredicto Aceptado y el artículo aparece en el catálogo público', async ({
    page,
  }) => {
    await loginUi(page, 'editor');
    // En revisión ya no figura en «Nuevos envíos»: se entra por su detalle.
    await page.goto(`/app/editor/submissions/${manuscriptId}`);

    await page.getByRole('radio', { name: /^Aceptado/ }).check();
    await page.getByRole('button', { name: 'Registrar veredicto' }).click();
    await page.getByRole('dialog').getByRole('button', { name: 'Registrar veredicto' }).click();
    // El veredicto queda en el historial de la pantalla (no basta con el botón de opción).
    await expect(page.getByRole('heading', { name: 'Veredictos registrados' })).toBeVisible();

    await page.context().clearCookies();
    await page.goto(`/catalog/${code}`);
    await expect(page.getByRole('heading', { level: 1, name: title })).toBeVisible();
  });

  test('6. El público busca, abre la ficha y descarga el PDF sin iniciar sesión', async ({
    browser,
  }) => {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });
    const page = await context.newPage();
    await page.goto('/catalog');
    await page.getByRole('searchbox', { name: 'Buscar' }).fill('Chimborazo');
    await page.getByRole('searchbox', { name: 'Buscar' }).press('Enter');
    await page.getByRole('link', { name: title }).click();

    await expect(page).toHaveURL(new RegExp(`/catalog/${code}$`));
    const pdf = page.waitForResponse((r) => r.url().includes(`/api/catalog/${code}/document/`));
    await page.getByRole('button', { name: 'Ver el documento (PDF)' }).click();
    const response = await pdf;
    expect(response.status()).toBe(200);
    expect(response.headers()['content-type']).toContain('application/pdf');
    // Sin cuenta no hay panel: la ficha pública no ofrece nada de la zona interna.
    await expect(page.getByRole('link', { name: 'Mis manuscritos' })).toHaveCount(0);
    await context.close();
  });

  test('7. El Autor da de baja el manuscrito y desaparece del catálogo', async ({
    page,
    browser,
  }) => {
    await loginUi(page, 'author');
    await page.goto(manuscriptUrl);
    await page.getByRole('button', { name: 'Dar de baja' }).click();
    const dialog = page.getByRole('dialog');
    await dialog.getByLabel(/Motivo de la baja/).fill('Retiro voluntario de los autores.');
    await dialog.getByRole('button', { name: 'Confirmar baja' }).click();
    await expect(page.getByText(/dado de baja|dada de baja/i).first()).toBeVisible();

    const context = await browser.newContext({ ignoreHTTPSErrors: true });
    const visitor = await context.newPage();
    await visitor.goto('/catalog');
    await visitor.getByRole('searchbox', { name: 'Buscar' }).fill('Chimborazo');
    await visitor.getByRole('searchbox', { name: 'Buscar' }).press('Enter');
    await expect(visitor.getByRole('heading', { level: 2, name: title })).toHaveCount(0);
    await visitor.goto(`/catalog/${code}`);
    await expect(visitor.getByRole('heading', { name: 'Artículo no disponible' })).toBeVisible();
    await context.close();

    // El historial se conserva aunque el manuscrito esté dado de baja.
    await page.goto(`${manuscriptUrl}/history`);
    await expect(page.getByText('v1').first()).toBeVisible();
  });

  test('8. El Administrador ve en la auditoría la descarga pública y la baja', async ({ page }) => {
    await loginUi(page, 'admin');
    await page.goto('/app/admin/audit');
    const trail: [string, string][] = [
      ['CATALOG_DOCUMENT_DOWNLOADED', 'PDF del catálogo descargado'],
      ['MANUSCRIPT_WITHDRAWN', 'Manuscrito retirado'],
    ];
    for (const [action, label] of trail) {
      await filterAudit(page, action, manuscriptId);
      const rows = page
        .getByRole('row')
        .filter({ has: page.getByRole('cell', { name: new RegExp(`^${label}`) }) });
      await expect(rows.first()).toContainText(code);
    }
    // El Administrador no tiene acceso a manuscritos: ni menú ni pantalla.
    await page.goto('/app/author/manuscripts');
    await expect(page.getByRole('heading', { name: 'Acceso denegado' })).toBeVisible();
  });
});
