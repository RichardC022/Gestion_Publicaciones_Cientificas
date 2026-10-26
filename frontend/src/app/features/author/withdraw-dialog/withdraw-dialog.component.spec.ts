import { ComponentFixture, TestBed } from '@angular/core/testing';
import { beforeAll } from 'vitest';

import { MANUSCRIPT_STATUSES, ManuscriptStatus } from '../../../core/models/manuscript.model';
import { WITHDRAWAL_REASON_MAX_LENGTH, WithdrawDialogComponent } from './withdraw-dialog.component';

const REASON_REQUIRED: ManuscriptStatus[] = ['UNDER_REVIEW', 'ACCEPTED'];
const REASON_OPTIONAL = MANUSCRIPT_STATUSES.filter((status) => !REASON_REQUIRED.includes(status));

describe('WithdrawDialogComponent', () => {
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

  let fixture: ComponentFixture<WithdrawDialogComponent>;
  let element: HTMLElement;
  const confirmed: (string | null)[] = [];
  let cancelled = 0;

  const render = async (
    options: { status?: ManuscriptStatus; open?: boolean; busy?: boolean; error?: string } = {},
  ) => {
    confirmed.length = 0;
    cancelled = 0;
    fixture = TestBed.createComponent(WithdrawDialogComponent);
    fixture.componentRef.setInput('status', options.status ?? 'DRAFT');
    fixture.componentRef.setInput('manuscriptCode', 'GPC-2026-000007');
    fixture.componentRef.setInput('open', options.open ?? true);
    fixture.componentRef.setInput('busy', options.busy ?? false);
    fixture.componentRef.setInput('error', options.error ?? '');
    fixture.componentInstance.confirmed.subscribe((reason) => confirmed.push(reason));
    fixture.componentInstance.cancelled.subscribe(() => (cancelled += 1));
    element = fixture.nativeElement as HTMLElement;
    await fixture.whenStable();
  };

  const settle = () => fixture.whenStable();
  const dialog = () => element.querySelector('dialog') as HTMLDialogElement;
  const textarea = () => element.querySelector('textarea') as HTMLTextAreaElement;
  const text = () => (element.textContent ?? '').replace(/\s+/g, ' ');
  const button = (label: string) =>
    Array.from(element.querySelectorAll('button')).find((b) => b.textContent?.trim() === label) as
      HTMLButtonElement | undefined;
  const alerts = () =>
    Array.from(element.querySelectorAll('[role="alert"]')).map((e) => e.textContent?.trim());

  const write = async (value: string) => {
    textarea().value = value;
    textarea().dispatchEvent(new Event('input'));
    await settle();
  };

  describe('apertura', () => {
    it('permanece cerrado mientras open es falso', async () => {
      await render({ open: false });

      expect(dialog().open).toBe(false);
    });

    it('se abre como modal con el código del manuscrito en el título', async () => {
      await render();

      expect(dialog().open).toBe(true);
      expect(element.querySelector('h2')?.textContent).toBe('Dar de baja GPC-2026-000007');
    });

    it('se asocia a su título y descripción para lectores de pantalla', async () => {
      await render();

      const title = element.querySelector('h2') as HTMLElement;
      expect(dialog().getAttribute('aria-labelledby')).toBe(title.id);
      const description = element.querySelector(`#${dialog().getAttribute('aria-describedby')}`);
      expect(description?.textContent).toContain('baja lógica');
    });
  });

  describe('la confirmación aclara que no se borra el historial', () => {
    it.each(MANUSCRIPT_STATUSES)('en %s explica qué se conserva', async (status) => {
      await render({ status });

      const body = text();
      expect(body).toContain('No se borra nada');
      for (const kept of ['versiones', 'evaluaciones', 'historial', 'auditoría']) {
        expect(body).toContain(kept);
      }
      expect(body).toContain('vista de archivados');
      expect(body).toContain('no se puede deshacer');
    });

    it('en revisión advierte que dejará de poder evaluarse', async () => {
      await render({ status: 'UNDER_REVIEW' });

      expect(element.querySelector('.withdraw-dialog__warning')?.textContent).toContain(
        'dejará de poder evaluarse',
      );
    });

    it('aceptado advierte que el artículo sale del catálogo', async () => {
      await render({ status: 'ACCEPTED' });

      expect(element.querySelector('.withdraw-dialog__warning')?.textContent).toContain(
        'dejará de mostrarse en el catálogo público',
      );
    });

    it.each(REASON_OPTIONAL)('en %s no muestra advertencias especiales', async (status) => {
      await render({ status });

      expect(element.querySelector('.withdraw-dialog__warning')).toBeNull();
    });

    it('la confirmación es una acción destructiva (botón rojo)', async () => {
      await render();

      expect(button('Confirmar baja')?.classList.contains('btn--danger')).toBe(true);
    });
  });

  describe('motivo obligatorio en revisión y aceptado', () => {
    it.each(REASON_REQUIRED)('en %s la etiqueta indica que es obligatorio', async (status) => {
      await render({ status });

      expect(element.querySelector('label')?.textContent).toContain('(obligatorio)');
      expect(textarea().getAttribute('aria-required')).toBe('true');
    });

    it.each(REASON_REQUIRED)('en %s sin motivo no se confirma y se explica', async (status) => {
      await render({ status });

      button('Confirmar baja')?.click();
      await settle();

      expect(confirmed).toEqual([]);
      expect(alerts().join(' ')).toContain('Indique el motivo de la baja');
      expect(textarea().getAttribute('aria-invalid')).toBe('true');
      expect(textarea().getAttribute('aria-describedby')).not.toBeNull();
    });

    it.each(['', '   ', '\n\t '])('un motivo en blanco (%j) tampoco vale', async (blank) => {
      await render({ status: 'UNDER_REVIEW' });
      await write(blank);

      button('Confirmar baja')?.click();
      await settle();

      expect(confirmed).toEqual([]);
    });

    it.each(REASON_REQUIRED)('en %s confirma con el motivo recortado', async (status) => {
      await render({ status });
      await write('  Retiro por decisión del equipo.  ');

      button('Confirmar baja')?.click();
      await settle();

      expect(confirmed).toEqual(['Retiro por decisión del equipo.']);
      expect(alerts()).toEqual([]);
    });

    it('el error desaparece al escribir el motivo', async () => {
      await render({ status: 'ACCEPTED' });
      button('Confirmar baja')?.click();
      await settle();
      expect(alerts().length).toBe(1);

      await write('Motivo');

      expect(alerts()).toEqual([]);
      expect(textarea().getAttribute('aria-invalid')).toBeNull();
    });
  });

  describe('motivo opcional en los demás estados', () => {
    it.each(REASON_OPTIONAL)('en %s la etiqueta indica que es opcional', async (status) => {
      await render({ status });

      expect(element.querySelector('label')?.textContent).toContain('(opcional)');
      expect(textarea().getAttribute('aria-required')).toBe('false');
    });

    it.each(REASON_OPTIONAL)('en %s confirma sin motivo con null', async (status) => {
      await render({ status });

      button('Confirmar baja')?.click();
      await settle();

      expect(confirmed).toEqual([null]);
      expect(alerts()).toEqual([]);
    });

    it('si se escribe un motivo opcional, se envía recortado', async () => {
      await render({ status: 'REJECTED' });
      await write(' Archivo el rechazo. ');

      button('Confirmar baja')?.click();
      await settle();

      expect(confirmed).toEqual(['Archivo el rechazo.']);
    });

    it('un motivo solo con espacios cuenta como ausente', async () => {
      await render({ status: 'DRAFT' });
      await write('    ');

      button('Confirmar baja')?.click();
      await settle();

      expect(confirmed).toEqual([null]);
    });
  });

  it('limita el motivo al máximo que acepta la API', async () => {
    await render();

    expect(WITHDRAWAL_REASON_MAX_LENGTH).toBe(2000);
    expect(textarea().getAttribute('maxlength')).toBe('2000');
  });

  describe('cancelar', () => {
    it('el botón Cancelar emite cancelled sin confirmar', async () => {
      await render();

      button('Cancelar')?.click();
      await settle();

      expect(cancelled).toBe(1);
      expect(confirmed).toEqual([]);
    });

    it('Esc cancela y no cierra por su cuenta (decide quien lo usa)', async () => {
      await render();
      const escape = new Event('cancel', { cancelable: true });

      dialog().dispatchEvent(escape);
      await settle();

      expect(escape.defaultPrevented).toBe(true);
      expect(cancelled).toBe(1);
      expect(dialog().open).toBe(true);
    });

    it('al pasar open a falso se cierra', async () => {
      await render();

      fixture.componentRef.setInput('open', false);
      await settle();

      expect(dialog().open).toBe(false);
    });
  });

  describe('baja en curso', () => {
    it('bloquea los controles y evita una segunda confirmación', async () => {
      await render({ status: 'DRAFT', busy: true });

      expect(button('Dando de baja…')?.disabled).toBe(true);
      expect(button('Cancelar')?.disabled).toBe(true);
      expect(textarea().disabled).toBe(true);
      button('Dando de baja…')?.click();
      await settle();
      expect(confirmed).toEqual([]);
    });

    it('Esc no cancela mientras se da de baja', async () => {
      await render({ busy: true });

      dialog().dispatchEvent(new Event('cancel', { cancelable: true }));
      await settle();

      expect(cancelled).toBe(0);
    });
  });

  describe('errores y reapertura', () => {
    it('muestra el error de la baja dentro del diálogo', async () => {
      await render({ error: 'Servicio no disponible temporalmente.' });

      expect(alerts()).toEqual(['Servicio no disponible temporalmente.']);
      expect(dialog().open).toBe(true);
    });

    it('cada apertura empieza limpia: sin motivo previo ni errores de validación', async () => {
      await render({ status: 'ACCEPTED' });
      await write('Motivo anterior');
      button('Cancelar')?.click();
      fixture.componentRef.setInput('open', false);
      await settle();

      fixture.componentRef.setInput('open', true);
      await settle();

      expect(textarea().value).toBe('');
      expect(alerts()).toEqual([]);
    });
  });
});
