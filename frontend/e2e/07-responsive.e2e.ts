import { expect, Page, test } from '@playwright/test';

import { visit } from './support/a11y';
import { loginUi } from './support/ui';
import { buildWorld, screens, World } from './support/world';

/**
 * Responsive (TSK-92): en escritorio y en tableta, horizontal y vertical, ninguna pantalla
 * desborda la página y todo control es alcanzable (cabe en el ancho y no queda tapado).
 */
const VIEWPORTS = [
  { name: 'escritorio 1920×1080', width: 1920, height: 1080 },
  { name: 'portátil 1366×768', width: 1366, height: 768 },
  { name: 'tableta horizontal 1024×768', width: 1024, height: 768 },
  { name: 'tableta vertical 768×1024', width: 768, height: 1024 },
];

let world: World;
test.beforeAll(async () => {
  world = await buildWorld('Responsive');
});

/** Desborde horizontal de la página y controles fuera de alcance, en el viewport actual. */
async function layoutProblems(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const problems: string[] = [];
    const root = document.documentElement;
    if (root.scrollWidth > root.clientWidth + 1) {
      problems.push(`la página desborda en horizontal (${root.scrollWidth} > ${root.clientWidth})`);
    }
    const label = (el: Element): string =>
      `${el.tagName.toLowerCase()}${(el as HTMLElement).id ? `#${(el as HTMLElement).id}` : ''} «${(el.getAttribute('aria-label') ?? el.textContent ?? '').trim().slice(0, 30)}»`;
    const scrollsX = (el: Element | null): boolean => {
      for (let n = el?.parentElement; n; n = n.parentElement) {
        const overflow = getComputedStyle(n).overflowX;
        if ((overflow === 'auto' || overflow === 'scroll') && n.scrollWidth > n.clientWidth) {
          return true;
        }
      }
      return false;
    };
    const controls = document.querySelectorAll<HTMLElement>(
      'a[href], button, input:not([type=hidden]), select, textarea, summary',
    );
    for (const el of Array.from(controls)) {
      // El enlace «Saltar al contenido» está fuera de pantalla a propósito hasta recibir el foco.
      if (el.classList.contains('skip-link')) {
        continue;
      }
      if (!el.checkVisibility({ visibilityProperty: true }) || (el as HTMLButtonElement).disabled) {
        continue;
      }
      const rect = el.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0) {
        continue; // p. ej. el radio oculto que dibuja su etiqueta
      }
      if (!scrollsX(el) && (rect.left < -1 || rect.right > root.clientWidth + 1)) {
        problems.push(
          `${label(el)} queda fuera del ancho (${Math.round(rect.left)}–${Math.round(rect.right)})`,
        );
        continue;
      }
      el.scrollIntoView({ block: 'center', inline: 'center' });
      const r = el.getBoundingClientRect();
      const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
      const covered =
        !hit || !(el.contains(hit) || hit.contains(el) || el.closest('label')?.contains(hit));
      if (covered) {
        problems.push(`${label(el)} está tapado por ${hit ? label(hit) : 'nada'}`);
      }
    }
    window.scrollTo(0, 0);
    return problems;
  });
}

test('control: el verificador detecta un desborde y un control fuera de pantalla (no pasa en vacío)', async ({
  page,
}) => {
  await page.setViewportSize({ width: 768, height: 1024 });
  await page.setContent(
    '<!doctype html><html lang="es"><head><title>x</title></head><body><main><h1>Prueba</h1>' +
      '<div style="width:1500px"><button style="margin-left:1200px">Fuera del ancho</button></div></main></body></html>',
  );
  const problems = (await layoutProblems(page)).join('\n');
  expect(problems).toContain('desborda en horizontal');
  expect(problems).toContain('Fuera del ancho');
});

for (const role of [null, 'author', 'editor', 'reviewer', 'admin'] as const) {
  test(`sin desbordes ni controles inaccesibles (${role ?? 'público'})`, async ({ page }) => {
    await page.setViewportSize({ width: 1920, height: 1080 });
    if (role) {
      await loginUi(page, role);
    }
    const problems: string[] = [];
    for (const screen of screens(world).filter((s) => s.role === role)) {
      await visit(page, screen.path);
      for (const viewport of VIEWPORTS) {
        await page.setViewportSize({ width: viewport.width, height: viewport.height });
        for (const problem of await layoutProblems(page)) {
          problems.push(`${screen.name} @ ${viewport.name}: ${problem}`);
        }
      }
      await page.setViewportSize({ width: 1920, height: 1080 });
    }
    expect(problems, problems.join('\n')).toEqual([]);
  });
}
