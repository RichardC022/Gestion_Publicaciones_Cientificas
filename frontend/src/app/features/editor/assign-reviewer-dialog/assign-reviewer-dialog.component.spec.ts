import { Component, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';

import { Assignment, EligibleReviewer } from '../../../core/models/editor.model';
import { buildAssignment, buildReviewer } from '../testing/editor.fixtures';
import { AssignReviewerDialogComponent } from './assign-reviewer-dialog.component';

@Component({
  imports: [AssignReviewerDialogComponent],
  template: `<app-assign-reviewer-dialog
    [open]="open()"
    [reviewer]="reviewer()"
    manuscriptCode="GPC-2026-000001"
    [existing]="existing()"
    [busy]="busy()"
    [error]="error()"
    [assignment]="assignment()"
    (confirmed)="events.push('confirmed')"
    (cancelled)="events.push('cancelled')"
    (finished)="events.push('finished')"
  />`,
})
class HostComponent {
  readonly open = signal(true);
  readonly reviewer = signal<EligibleReviewer | null>(buildReviewer());
  readonly existing = signal<Assignment | null>(null);
  readonly busy = signal(false);
  readonly error = signal('');
  readonly assignment = signal<Assignment | null>(null);
  readonly events: string[] = [];
}

describe('AssignReviewerDialogComponent', () => {
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

  const text = (node: Element | null) => (node?.textContent ?? '').replace(/\s+/g, ' ').trim();

  const setup = () => {
    const fixture = TestBed.createComponent(HostComponent);
    fixture.detectChanges();
    const element = fixture.nativeElement as HTMLElement;
    const dialog = () => element.querySelector('dialog') as HTMLDialogElement;
    const button = (label: string) =>
      Array.from(dialog().querySelectorAll('button')).find((b) => text(b) === label) as
        | HTMLButtonElement
        | undefined;
    return { fixture, host: fixture.componentInstance, element, dialog, button };
  };

  it('se abre y se cierra con la entrada open', () => {
    const { fixture, host, dialog } = setup();
    expect(dialog().open).toBe(true);

    host.open.set(false);
    fixture.detectChanges();

    expect(dialog().open).toBe(false);
  });

  it('nombra al Revisor, explica el Revisor único y anuncia el plazo sin inventar una fecha', () => {
    const { dialog } = setup();

    const content = text(dialog());
    expect(content).toContain('Marta Ruiz');
    expect(content).toContain('marta@unl.edu.ec');
    expect(content).toContain('único Revisor de GPC-2026-000001');
    expect(content).toContain('20 días calendario');
    expect(content).toContain('El servidor fija la fecha límite');
    // El navegador no calcula fechas: no hay ninguna fecha antes de confirmar.
    expect(content).not.toMatch(/\d{2}\/\d{2}\/\d{4}/);
  });

  it('confirmar y cancelar emiten sus eventos', () => {
    const { host, button } = setup();

    button('Confirmar asignación')!.click();
    button('Cancelar')!.click();

    expect(host.events).toEqual(['confirmed', 'cancelled']);
  });

  it('mientras asigna bloquea los botones y no emite', () => {
    const { fixture, host, button } = setup();
    host.busy.set(true);
    fixture.detectChanges();

    expect(button('Asignando…')!.disabled).toBe(true);
    expect(button('Cancelar')!.disabled).toBe(true);
    button('Asignando…')!.click();
    button('Cancelar')!.click();
    expect(host.events).toEqual([]);
  });

  describe('asignación existente', () => {
    it('advierte que ya hay un Revisor activo y no permite confirmar', () => {
      const { fixture, host, dialog, button } = setup();
      host.existing.set(buildAssignment({ status: 'ACTIVE' }));
      fixture.detectChanges();

      expect(text(dialog().querySelector('[role="alert"]'))).toContain(
        'ya tiene un Revisor activo (Marta Ruiz)',
      );
      expect(button('Confirmar asignación')!.disabled).toBe(true);
      button('Confirmar asignación')!.click();
      expect(host.events).toEqual([]);
    });

    it('una asignación vencida debe revocarse antes', () => {
      const { fixture, host, dialog, button } = setup();
      host.existing.set(buildAssignment({ status: 'EXPIRED' }));
      fixture.detectChanges();

      expect(text(dialog().querySelector('[role="alert"]'))).toContain(
        'está vencida y debe revocarse antes',
      );
      expect(button('Confirmar asignación')!.disabled).toBe(true);
    });

    it('una asignación ya revocada no bloquea', () => {
      const { fixture, host, dialog, button } = setup();
      host.existing.set(buildAssignment({ status: 'REVOKED' }));
      fixture.detectChanges();

      expect(dialog().querySelector('[role="alert"]')).toBeNull();
      expect(button('Confirmar asignación')!.disabled).toBe(false);
    });
  });

  it('muestra el 409 del servidor cuando otro Editor asignó antes', () => {
    const { fixture, host, dialog } = setup();
    host.error.set('El manuscrito ya tiene un Revisor activo.');
    fixture.detectChanges();

    expect(text(dialog().querySelector('[role="alert"]'))).toBe(
      'El manuscrito ya tiene un Revisor activo.',
    );
  });

  describe('resultado', () => {
    const done = () => buildAssignment({ due_at: '2026-11-11T15:00:00Z' });

    it('muestra la fecha límite exacta que devolvió el servidor', () => {
      const { fixture, host, dialog, button } = setup();
      host.assignment.set(done());
      fixture.detectChanges();

      const content = text(dialog());
      expect(content).toContain('Revisor asignado');
      // 15:00 UTC en la zona institucional (UTC-5) son las 10:00.
      expect(content).toContain('Fecha límite: 11/11/2026 10:00');
      expect(button('Confirmar asignación')).toBeUndefined();
      expect(button('Cancelar')).toBeUndefined();
    });

    it('«Entendido» cierra el resultado', () => {
      const { fixture, host, button } = setup();
      host.assignment.set(done());
      fixture.detectChanges();

      button('Entendido')!.click();

      expect(host.events).toEqual(['finished']);
    });

    it('Esc en el resultado lo cierra como finalizado, no como cancelado', () => {
      const { fixture, host, dialog } = setup();
      host.assignment.set(done());
      fixture.detectChanges();

      dialog().dispatchEvent(new Event('cancel', { cancelable: true }));

      expect(host.events).toEqual(['finished']);
    });
  });

  it('Esc antes de confirmar cancela', () => {
    const { host, dialog } = setup();

    dialog().dispatchEvent(new Event('cancel', { cancelable: true }));

    expect(host.events).toEqual(['cancelled']);
  });
});
