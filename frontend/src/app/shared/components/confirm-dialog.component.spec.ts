import { TestBed } from '@angular/core/testing';
import { beforeAll } from 'vitest';

import { ConfirmDialogComponent } from './confirm-dialog.component';

describe('ConfirmDialogComponent', () => {
  beforeAll(() => {
    // jsdom no implementa el ciclo abierto/cerrado del diálogo nativo.
    if (typeof HTMLDialogElement.prototype.showModal !== 'function') {
      HTMLDialogElement.prototype.showModal = function (this: HTMLDialogElement) {
        this.setAttribute('open', '');
      };
    }
    if (typeof HTMLDialogElement.prototype.close !== 'function') {
      HTMLDialogElement.prototype.close = function (this: HTMLDialogElement) {
        this.removeAttribute('open');
      };
    }
  });

  const render = async (open = false, destructive = false) => {
    const fixture = TestBed.createComponent(ConfirmDialogComponent);
    fixture.componentRef.setInput('message', '¿Desea confirmar la acción?');
    fixture.componentRef.setInput('destructive', destructive);
    fixture.componentRef.setInput('open', open);
    await fixture.whenStable();
    return fixture;
  };

  const dialogOf = (fixture: { nativeElement: unknown }) =>
    (fixture.nativeElement as HTMLElement).querySelector<HTMLDialogElement>('dialog');

  const buttonsOf = (fixture: { nativeElement: unknown }) =>
    Array.from(
      (fixture.nativeElement as HTMLElement).querySelectorAll<HTMLButtonElement>('button'),
    );

  it('mantiene el diálogo cerrado cuando open es falso', async () => {
    const fixture = await render();
    expect(dialogOf(fixture)?.open).toBe(false);
  });

  it('abre el diálogo nativo cuando open es verdadero', async () => {
    const fixture = await render(true);
    expect(dialogOf(fixture)?.open).toBe(true);
  });

  it('emite confirmed y cierra el diálogo al confirmar', async () => {
    const fixture = await render(true);
    let confirmed = false;
    let cancelled = false;
    fixture.componentInstance.confirmed.subscribe(() => {
      confirmed = true;
    });
    fixture.componentInstance.cancelled.subscribe(() => {
      cancelled = true;
    });

    buttonsOf(fixture)[1].click();
    await fixture.whenStable();

    expect(confirmed).toBe(true);
    expect(cancelled).toBe(false);
    expect(dialogOf(fixture)?.open).toBe(false);
  });

  it('emite cancelled al pulsar Cancelar', async () => {
    const fixture = await render(true);
    let cancelled = false;
    fixture.componentInstance.cancelled.subscribe(() => {
      cancelled = true;
    });

    buttonsOf(fixture)[0].click();
    await fixture.whenStable();

    expect(cancelled).toBe(true);
  });

  it('usa el botón rojo para acciones destructivas', async () => {
    const fixture = await render(true, true);
    expect(buttonsOf(fixture)[1].className).toContain('btn--danger');
  });
});
