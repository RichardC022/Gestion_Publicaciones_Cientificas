import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';

import { API_BASE_URL } from '../../../core/http/api-base-url.token';
import { IncidentReceipt } from '../../../core/models/reviewer.model';
import { errorEnvelope } from '../../author/testing/manuscript.fixtures';
import { IdentityLeakDialogComponent } from './identity-leak-dialog.component';

const LEAK = '/api/reviewer/assignments/a-1/identity-leak/';
const RECEIPT: IncidentReceipt = {
  id: 'i-1',
  assignment: 'a-1',
  report_type: 'IDENTITY_LEAK',
  status: 'OPEN',
  created_at: '2026-10-27T15:00:00Z',
};

describe('IdentityLeakDialogComponent', () => {
  let http: HttpTestingController;
  let fixture: ComponentFixture<IdentityLeakDialogComponent>;
  let reported: IncidentReceipt[];
  let cancelled: number;

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

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: API_BASE_URL, useValue: '/api/' },
      ],
    });
    http = TestBed.inject(HttpTestingController);
    reported = [];
    cancelled = 0;
  });

  afterEach(() => http.verify());

  const text = (node: Element | null) => (node?.textContent ?? '').replace(/\s+/g, ' ').trim();
  const root = () => fixture.nativeElement as HTMLElement;
  const dialog = () => root().querySelector('dialog') as HTMLDialogElement;
  const send = () =>
    Array.from(root().querySelectorAll<HTMLButtonElement>('button')).find((b) =>
      /Enviar reporte|Enviando/.test(text(b)),
    )!;

  const render = async (open = true) => {
    fixture = TestBed.createComponent(IdentityLeakDialogComponent);
    fixture.componentRef.setInput('assignmentId', 'a-1');
    fixture.componentRef.setInput('open', open);
    fixture.componentInstance.reported.subscribe((value) => reported.push(value));
    fixture.componentInstance.cancelled.subscribe(() => cancelled++);
    await fixture.whenStable();
  };

  const write = async (value: string) => {
    const area = root().querySelector<HTMLTextAreaElement>('textarea')!;
    area.value = value;
    area.dispatchEvent(new Event('input', { bubbles: true }));
    await fixture.whenStable();
  };

  const chooseType = async (value: string) => {
    const radio = Array.from(root().querySelectorAll<HTMLInputElement>('input[type="radio"]')).find(
      (r) => r.value === value,
    )!;
    radio.checked = true;
    radio.dispatchEvent(new Event('change', { bubbles: true }));
    await fixture.whenStable();
  };

  it('se presenta como confidencial: solo el Editor lo ve y el Autor no se entera', async () => {
    await render();

    expect(dialog().hasAttribute('open')).toBe(true);
    const note = text(root().querySelector('[role="note"]'));
    expect(note).toContain('Reporte confidencial');
    expect(note).toContain('Solo lo verá el Editor');
    expect(note).toContain('El Autor no será informado');
    expect(note).toContain('su evaluación no cambia');
  });

  it('ofrece los dos tipos y propone la fuga de identidad', async () => {
    await render();

    const radios = Array.from(root().querySelectorAll<HTMLInputElement>('input[type="radio"]'));
    expect(radios.map((r) => r.value)).toEqual(['IDENTITY_LEAK', 'OTHER']);
    expect(radios[0].checked).toBe(true);
  });

  it('exige la descripción y no envía sin ella', async () => {
    await render();

    send().click();
    await fixture.whenStable();
    fixture.detectChanges();

    http.expectNone(LEAK);
    expect(text(root().querySelector('textarea + [role="alert"]'))).toBe('Describa qué observó.');
    expect(root().querySelector('textarea')!.getAttribute('aria-invalid')).toBe('true');
  });

  it('una descripción en blanco no vale', async () => {
    await render();
    await write('   \n  ');

    send().click();

    http.expectNone(LEAK);
  });

  it('envía el tipo y la descripción recortada, y entrega solo el acuse', async () => {
    await render();
    await chooseType('OTHER');
    await write('  La portada trae un nombre.  ');

    send().click();
    const request = http.expectOne(LEAK);
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual({
      report_type: 'OTHER',
      description: 'La portada trae un nombre.',
    });
    request.flush({ ...RECEIPT, report_type: 'OTHER' }, { status: 201, statusText: 'Created' });
    await fixture.whenStable();

    expect(reported).toHaveLength(1);
    expect(reported[0].id).toBe('i-1');
  });

  it('no envía datos del Revisor ni del Autor', async () => {
    await render();
    await write('Aparece el nombre en el pie de página.');

    send().click();
    const request = http.expectOne(LEAK);

    expect(Object.keys(request.request.body).sort()).toEqual(['description', 'report_type']);
    request.flush(RECEIPT, { status: 201, statusText: 'Created' });
  });

  it('mientras se envía bloquea los controles', async () => {
    await render();
    await write('Texto');

    send().click();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(send().disabled).toBe(true);
    expect(text(send())).toBe('Enviando…');
    send().click();
    http.expectOne(LEAK).flush(RECEIPT, { status: 201, statusText: 'Created' });
  });

  it('un error de red no muestra el reporte como enviado y conserva el texto', async () => {
    await render();
    await write('Texto que no debe perderse');

    send().click();
    http.expectOne(LEAK).error(new ProgressEvent('error'));
    await fixture.whenStable();
    fixture.detectChanges();

    expect(reported).toHaveLength(0);
    const alert = text(root().querySelector('.leak-dialog__error[role="alert"]'));
    expect(alert).toContain('El reporte NO se envió');
    expect(alert).toContain('No fue posible conectar');
    expect(root().querySelector('textarea')!.value).toBe('Texto que no debe perderse');
    expect(send().disabled).toBe(false);
  });

  it('un 409 por reporte abierto lo dice con el mensaje del servidor', async () => {
    await render();
    await write('Otro reporte');

    send().click();
    http
      .expectOne(LEAK)
      .flush(
        errorEnvelope('STATE_CONFLICT', 'Ya existe un reporte abierto para esta asignación.'),
        {
          status: 409,
          statusText: 'Conflict',
        },
      );
    await fixture.whenStable();
    fixture.detectChanges();

    expect(reported).toHaveLength(0);
    expect(text(root().querySelector('.leak-dialog__error[role="alert"]'))).toBe(
      'El reporte NO se envió. Ya existe un reporte abierto para esta asignación.',
    );
  });

  it('un 503 de auditoría tampoco lo da por enviado', async () => {
    await render();
    await write('Texto');

    send().click();
    http.expectOne(LEAK).flush(errorEnvelope('AUDIT_UNAVAILABLE', 'Sin auditoría.'), {
      status: 503,
      statusText: 'Service Unavailable',
    });
    await fixture.whenStable();
    fixture.detectChanges();

    expect(reported).toHaveLength(0);
    expect(text(root().querySelector('.leak-dialog__error[role="alert"]'))).toContain(
      'El reporte NO se envió',
    );
  });

  it('cancelar no envía nada', async () => {
    await render();
    await write('Texto');

    Array.from(root().querySelectorAll<HTMLButtonElement>('button'))
      .find((b) => text(b) === 'Cancelar')!
      .click();

    http.expectNone(LEAK);
    expect(cancelled).toBe(1);
  });

  it('cada apertura empieza limpia', async () => {
    await render();
    await chooseType('OTHER');
    await write('Texto viejo');
    fixture.componentRef.setInput('open', false);
    await fixture.whenStable();

    fixture.componentRef.setInput('open', true);
    await fixture.whenStable();
    fixture.detectChanges();

    expect(root().querySelector('textarea')!.value).toBe('');
    expect(root().querySelector<HTMLInputElement>('input[value="IDENTITY_LEAK"]')).not.toBeNull();
  });
});
