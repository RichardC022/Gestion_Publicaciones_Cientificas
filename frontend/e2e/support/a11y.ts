import AxeBuilder from '@axe-core/playwright';
import { expect, Page } from '@playwright/test';

/** Criterios de la TSK-92: WCAG 2.x nivel A y AA (incluye el contraste de color). */
const TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'];

/** Entra a una ruta y espera a que la SPA termine de arrancar (sesión incluida). */
export async function visit(page: Page, path: string): Promise<void> {
  await page.goto(path);
  await page.waitForLoadState('networkidle');
  await expect(page.locator('h1').first()).toBeVisible();
}

export interface Finding {
  rule: string;
  impact: string;
  help: string;
  targets: string[];
}

/** Ejecuta axe sobre lo que hay en pantalla y devuelve las violaciones, ya resumidas. */
export async function scan(page: Page): Promise<Finding[]> {
  const result = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  return result.violations.map((v) => ({
    rule: v.id,
    impact: v.impact ?? 'n/a',
    help: v.help,
    targets: v.nodes.slice(0, 4).map((n) => n.target.join(' ')),
  }));
}

export function describeFindings(findings: Finding[]): string {
  return findings
    .map((f) => `  - [${f.impact}] ${f.rule}: ${f.help}\n      ${f.targets.join('\n      ')}`)
    .join('\n');
}
