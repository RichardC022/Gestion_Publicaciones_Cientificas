import { Component, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';

import { Assignment } from '../../../core/models/editor.model';
import { buildAssignment } from '../testing/editor.fixtures';
import {
  RevocationRequest,
  RevokeAssignmentDialogComponent,
} from './revoke-assignment-dialog.component';

@Component({
  imports: [RevokeAssignmentDialogComponent],
  template: `<app-revoke-assignment-dialog
    [open]="open()"
    [assignment]="assignment()"
    [busy]="busy()"
    [error]="error()"
    (confirmed)="confirmed.push($event)"
    (cancelled)="cancelled = cancelled + 1"
  />`,
})
class HostComponent {
  readonly open = signal(true);
  readonly assignment = signal<Assignment | null>(buildAssignment());
  readonly busy = signal(false);
  readonly error = signal('');
  readonly confirmed: RevocationRequest[] = [];
  cancelled = 0;
}

describe('RevokeAssignmentDialogComponent', () => {
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

  const setup = (assignment: Assignment = buildAssignment()) => {
    const fixture = TestBed.createComponent(HostComponent);
    fixture.componentInstance.assignment.set(assignment);
    fixture.detectChanges();
    const element = fixture.nativeElement as HTMLElement;
    const dialog = () => element.querySelector('dialog') as HTMLDialogElement;
    // El botón rojo cambia de texto mientras revoca: se identifica por su estilo.
    const confirmButton = () => dialog().querySelector('button.btn--danger') as HTMLButtonElement;
    const cancelButton = () =>
      Array.from(dialog().querySelectorAll('button')).find(
        (b) => text(b) === 'Cancelar',
      ) as HTMLButtonElement;
    const causes = () =>
      Array.from(dialog().querySelectorAll('.revoke-dialog__option')).map((o) =>
        text(o.querySelector('strong')),
      );
    const pickCause = (label: string) => {
      const option = Array.from(dialog().querySelectorAll('.revoke-dialog__option')).find(
        (o) => text(o.querySelector('strong')) === label,
      );
      (option!.querySelector('input') as HTMLInputElement).click();
      fixture.detectChanges();
    };
    const write = (value: string) => {
      const area = dialog().querySelector('textarea') as HTMLTextAreaElement;
      area.value = value;
      area.dispatchEvent(new Event('input'));
      fixture.detectChanges();
    };
    return {
      fixture,
      host: fixture.componentInstance,
      dialog,
      confirmButton,
      cancelButton,
      causes,
      pickCause,
      write,
    };
  };

  it('nombra al Revisor y explica las consecuencias', () => {
    const { dialog } = setup();

    const content = text(dialog());
    expect(content).toContain('Marta Ruiz');
    expect(content).toContain('marta@unl.edu.ec');
    // 15:00 UTC en la zona institucional (UTC-5) son las 10:00.
    expect(content).toContain('Su plazo vence el 11/11/2026 10:00');
    expect(content).toContain('seguirá en revisión, a la espera de un nuevo Revisor');
    expect(content).toContain('evaluaciones ya escritas se conservan');
  });

  describe('causas', () => {
    it('con el plazo vigente ofrece solo las tres causas tempranas', () => {
      const { causes, dialog } = setup(buildAssignment({ status: 'ACTIVE', is_overdue: false }));

      expect(causes()).toEqual(['Conflicto de interés', 'Error de asignación', 'Cuenta inhabilitada']);
      expect(text(dialog())).toContain('«Plazo vencido» solo está disponible');
    });

    it.each([
      ['vencida (EXPIRED)', { status: 'EXPIRED', is_overdue: false }],
      ['activa pasada su fecha', { status: 'ACTIVE', is_overdue: true }],
    ])('una asignación %s ofrece «Plazo vencido» y lo sugiere', (_name, overrides) => {
      const { causes, dialog, confirmButton, write, host } = setup(buildAssignment(overrides));

      expect(causes()).toContain('Plazo vencido');
      expect(text(dialog())).toContain('Vencida');
      write('No respondió en el plazo.');
      confirmButton().click();
      expect(host.confirmed).toEqual([{ cause: 'OVERDUE', reason: 'No respondió en el plazo.' }]);
    });

    it('describe cada causa para distinguirlas', () => {
      const { dialog } = setup(buildAssignment({ status: 'EXPIRED' }));

      const content = text(dialog());
      expect(content).toContain('vínculo con el manuscrito o sus autores');
      expect(content).toContain('persona equivocada');
      expect(content).toContain('ya no puede acceder al sistema');
      expect(content).toContain('no evaluó dentro de los 20 días');
    });
  });

  describe('validación', () => {
    it('sin causa ni motivo explica ambos y no emite', () => {
      const { dialog, confirmButton, host } = setup();

      confirmButton().click();
      TestBed.tick();

      expect(text(dialog())).toContain('Seleccione la causa de la revocación.');
      expect(text(dialog())).toContain('Indique el motivo de la revocación.');
      expect(host.confirmed).toEqual([]);
    });

    it('con causa y sin motivo sigue exigiendo el motivo', () => {
      const { dialog, confirmButton, pickCause, write, host, fixture } = setup();
      pickCause('Error de asignación');
      write('   ');

      confirmButton().click();
      fixture.detectChanges();

      expect(text(dialog())).not.toContain('Seleccione la causa');
      expect(text(dialog())).toContain('Indique el motivo de la revocación.');
      expect(dialog().querySelector('textarea')!.getAttribute('aria-invalid')).toBe('true');
      expect(host.confirmed).toEqual([]);
    });

    it('con causa y motivo emite ambos, recortando el motivo', () => {
      const { confirmButton, pickCause, write, host } = setup();
      pickCause('Conflicto de interés');
      write('  Es coautor de un trabajo previo.  ');

      confirmButton().click();

      expect(host.confirmed).toEqual([
        { cause: 'CONFLICT_OF_INTEREST', reason: 'Es coautor de un trabajo previo.' },
      ]);
    });

    it('limita el motivo a lo que acepta la API', () => {
      const { dialog } = setup();

      expect(dialog().querySelector('textarea')!.getAttribute('maxlength')).toBe('2000');
    });
  });

  describe('estado', () => {
    it('mientras revoca bloquea los controles y no emite', () => {
      const { fixture, host, confirmButton, cancelButton, pickCause, write } = setup();
      pickCause('Cuenta inhabilitada');
      write('Cuenta cerrada.');
      host.busy.set(true);
      fixture.detectChanges();

      expect(confirmButton().textContent).toContain('Revocando…');
      expect(confirmButton().disabled).toBe(true);
      expect(cancelButton().disabled).toBe(true);
      confirmButton().click();
      cancelButton().click();
      expect(host.confirmed).toEqual([]);
      expect(host.cancelled).toBe(0);
    });

    it('muestra el error del servidor y deja volver a intentar', () => {
      const { fixture, host, dialog, confirmButton } = setup();
      host.error.set('Solo una asignación activa o vencida puede revocarse.');
      fixture.detectChanges();

      expect(text(dialog().querySelector('.revoke-dialog__error'))).toBe(
        'Solo una asignación activa o vencida puede revocarse.',
      );
      expect(confirmButton().disabled).toBe(false);
    });

    it('cancelar y Esc emiten la cancelación', () => {
      const { host, dialog, cancelButton } = setup();

      cancelButton().click();
      dialog().dispatchEvent(new Event('cancel', { cancelable: true }));

      expect(host.cancelled).toBe(2);
    });

    it('cada apertura empieza limpia', async () => {
      const { fixture, host, write, pickCause, dialog } = setup();
      pickCause('Error de asignación');
      write('Texto a medias');

      host.open.set(false);
      fixture.detectChanges();
      host.open.set(true);
      fixture.detectChanges();
      // `ngModel` aplica el valor en una microtarea.
      await fixture.whenStable();

      expect((dialog().querySelector('textarea') as HTMLTextAreaElement).value).toBe('');
      expect(
        dialog().querySelectorAll('input[type="radio"]:checked').length,
      ).toBe(0);
    });

    it('la confirmación es destructiva (botón rojo)', () => {
      const { confirmButton } = setup();

      expect(confirmButton().classList.contains('btn--danger')).toBe(true);
    });
  });
});
