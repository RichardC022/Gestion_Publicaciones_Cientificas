import { Page } from '@playwright/test';

export interface TabReport {
  total: number;
  /** Controles que el recorrido con Tab nunca alcanzó. */
  unreachable: string[];
  /** Controles que, al recibir el foco, no cambian nada visible. */
  noIndicator: string[];
}

/**
 * Recorre la pantalla SOLO con Tab y comprueba dos cosas por cada control visible:
 * que se alcanza y que, al recibir el foco, algo visible cambia (contorno, sombra, borde,
 * fondo o color en él o en sus tres ancestros más cercanos: p. ej. la etiqueta que dibuja
 * un radio oculto). De los radios del mismo grupo basta con uno: las flechas mueven entre ellos.
 *
 * El estilo «sin foco» se mide ANTES de empezar y no se toca el foco con `blur()/focus()`:
 * en un `<input type=date>` eso devolvería el foco al día y el Tab nunca avanzaría.
 */
export async function tabThrough(page: Page): Promise<TabReport> {
  const total = await page.evaluate(() => {
    const selector =
      'a[href], button, input:not([type=hidden]), select, textarea, summary, [tabindex]:not([tabindex="-1"])';
    const styleOf = (el: HTMLElement): string =>
      [
        el,
        el.parentElement,
        el.parentElement?.parentElement,
        el.parentElement?.parentElement?.parentElement,
      ]
        .filter((n): n is HTMLElement => !!n)
        .map((n) => {
          const c = getComputedStyle(n);
          return [
            c.outlineStyle,
            c.outlineWidth,
            c.outlineColor,
            c.boxShadow,
            c.borderTopColor,
            c.backgroundColor,
            c.color,
            c.textDecorationLine,
          ].join('|');
        })
        .join('||');
    const plain: Record<string, string> = {};
    const seenGroups = new Set<string>();
    let index = 0;
    for (const el of Array.from(document.querySelectorAll<HTMLElement>(selector))) {
      const rect = el.getBoundingClientRect();
      const disabled = (el as HTMLButtonElement).disabled === true;
      // Un radio o casilla puede estar oculto y dibujarlo su etiqueta: se juzga la etiqueta.
      const owner = el.closest('label') ?? el;
      const shown =
        owner.checkVisibility({ visibilityProperty: true }) && !el.closest('dialog:not([open])');
      const empty = rect.width === 0 && rect.height === 0 && !el.closest('label');
      if (disabled || !shown || empty || el.getAttribute('tabindex') === '-1') {
        continue;
      }
      if (el instanceof HTMLInputElement && el.type === 'radio') {
        const group = `${el.form ? 'f' : ''}${el.name}`;
        if (seenGroups.has(group)) {
          continue;
        }
        seenGroups.add(group);
      }
      el.dataset['e2eIdx'] = String(index);
      plain[String(index)] = styleOf(el);
      index++;
    }
    (window as unknown as { __plain: Record<string, string>; __styleOf: unknown }).__plain = plain;
    return index;
  });

  await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
  const reached = new Set<string>();
  // Un control puede tener varias paradas (día, mes, año e icono de un campo de fecha):
  // basta con que alguna muestre el indicador de foco.
  const shown = new Map<string, { name: string; changed: boolean }>();

  // Un <input type=date> consume varias pulsaciones (día, mes, año): hay holgura de sobra.
  for (let step = 0; step < total * 5 + 10 && reached.size < total; step++) {
    await page.keyboard.press('Tab');
    const probe = () =>
      page.evaluate(() => {
        const el = document.activeElement as HTMLElement | null;
        if (!el || el === document.body || !el.dataset['e2eIdx']) {
          return null;
        }
        const styleOf = (n0: HTMLElement): string =>
          [
            n0,
            n0.parentElement,
            n0.parentElement?.parentElement,
            n0.parentElement?.parentElement?.parentElement,
          ]
            .filter((n): n is HTMLElement => !!n)
            .map((n) => {
              const c = getComputedStyle(n);
              return [
                c.outlineStyle,
                c.outlineWidth,
                c.outlineColor,
                c.boxShadow,
                c.borderTopColor,
                c.backgroundColor,
                c.color,
                c.textDecorationLine,
              ].join('|');
            })
            .join('||');
        const idx = el.dataset['e2eIdx'] as string;
        const plain = (window as unknown as { __plain: Record<string, string> }).__plain[idx];
        const type = (el as HTMLInputElement).type ? `[${(el as HTMLInputElement).type}]` : '';
        const text = (el.getAttribute('aria-label') ?? el.textContent ?? '').trim().slice(0, 40);
        return {
          idx,
          changed: styleOf(el) !== plain,
          name: `${el.tagName.toLowerCase()}${type}${el.id ? `#${el.id}` : ''} «${text}»`,
        };
      });
    let info = await probe();
    // Una transición CSS puede estar a medias justo al recibir el foco: se vuelve a mirar.
    if (info && !info.changed) {
      await page.waitForTimeout(400);
      info = await probe();
    }
    if (info) {
      reached.add(info.idx);
      const previous = shown.get(info.idx);
      shown.set(info.idx, { name: info.name, changed: info.changed || previous?.changed === true });
    }
  }

  const unreachable = await page.evaluate((seen) => {
    return Array.from(document.querySelectorAll<HTMLElement>('[data-e2e-idx]'))
      .filter((el) => !seen.includes(el.dataset['e2eIdx'] as string))
      .map((el) => {
        const type = (el as HTMLInputElement).type ? `[${(el as HTMLInputElement).type}]` : '';
        const text = (el.getAttribute('aria-label') ?? el.textContent ?? '').trim().slice(0, 40);
        return `${el.tagName.toLowerCase()}${type}${el.id ? `#${el.id}` : ''} «${text}»`;
      });
  }, Array.from(reached));
  const noIndicator = Array.from(shown.values())
    .filter((entry) => !entry.changed)
    .map((entry) => entry.name);
  return { total, unreachable, noIndicator };
}
