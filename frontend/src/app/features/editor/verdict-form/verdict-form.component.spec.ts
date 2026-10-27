import { Component, signal } from '@angular/core';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, TestRequest, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { API_BASE_URL } from '../../../core/http/api-base-url.token';
import {
  EditorEvaluation,
  Recommendation,
  Verdict,
  VerdictRegistered,
} from '../../../core/models/editor.model';
import { errorEnvelope } from '../../author/testing/manuscript.fixtures';
import { buildEvaluation, buildVerdict, buildVerdictResult } from '../testing/editor.fixtures';
import {
  VerdictFormComponent,
  justificationRequired,
  verdictFormErrors,
} from './verdict-form.component';

@Component({
  imports: [VerdictFormComponent],
  template: `<app-verdict-form
    manuscriptId="s-1"
    [version]="version()"
    [etag]="etag()"
    [canRegister]="canRegister()"
    (registered)="registered.push($event)"
    (stale)="staleCount = staleCount + 1"
  />`,
})
class HostComponent {
  readonly version = signal(1);
  readonly etag = signal<string | null>('"4"');
  readonly canRegister = signal(true);
  readonly registered: VerdictRegistered[] = [];
  staleCount = 0;
}

const EVALUATIONS = '/api/editor/manuscripts/s-1/evaluations/';
const VERDICTS = '/api/editor/manuscripts/s-1/verdicts/';
const page = <T>(results: T[]) => ({ count: results.length, next: null, previous: null, results });

describe('VerdictFormComponent', () => {
  let http: HttpTestingController;

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
  });

  afterEach(() => http.verify());

  const text = (node: Element | null) => (node?.textContent ?? '').replace(/\s+/g, ' ').trim();

  /** Monta el formulario y responde evaluaciones y veredictos. */
  const open = async (
    data: { evaluations?: EditorEvaluation[]; verdicts?: Verdict[] } = {},
    setup: (host: HostComponent) => void = () => undefined,
  ) => {
    const fixture = TestBed.createComponent(HostComponent);
    setup(fixture.componentInstance);
    fixture.detectChanges();
    const element = fixture.nativeElement as HTMLElement;
    const settle = async () => {
      await fixture.whenStable();
      fixture.detectChanges();
    };
    http.expectOne((r) => r.url === EVALUATIONS).flush(page(data.evaluations ?? [buildEvaluation()]));
    http.expectOne((r) => r.method === 'GET' && r.url === VERDICTS).flush(page(data.verdicts ?? []));
    await settle();
    return { fixture, host: fixture.componentInstance, element, settle };
  };

  const confirmDialog = (element: HTMLElement) =>
    element.querySelector('app-confirm-dialog dialog') as HTMLDialogElement;
  const submitButton = (element: HTMLElement) =>
    element.querySelector('form button[type="submit"]') as HTMLButtonElement;
  const choose = async (element: HTMLElement, label: string, settle: () => Promise<void>) => {
    const option = Array.from(element.querySelectorAll('.verdict__option')).find(
      (o) => text(o.querySelector('strong')) === label,
    );
    (option!.querySelector('input') as HTMLInputElement).click();
    await settle();
  };
  const write = async (
    element: HTMLElement,
    selector: string,
    value: string,
    settle: () => Promise<void>,
  ) => {
    const area = element.querySelector(selector) as HTMLTextAreaElement;
    area.value = value;
    area.dispatchEvent(new Event('input'));
    await settle();
  };
  const justification = (e: HTMLElement) => e.querySelector('textarea[name="justification"]');
  const observations = (e: HTMLElement) => e.querySelector('textarea[name="observations"]');
  const verdictPost = (): TestRequest => http.expectOne((r) => r.method === 'POST' && r.url === VERDICTS);

  /** Elige una decisión, rellena lo necesario y confirma el diálogo. */
  const send = async (
    element: HTMLElement,
    settle: () => Promise<void>,
    decision = 'Aceptado',
  ) => {
    await choose(element, decision, settle);
    submitButton(element).click();
    await settle();
    (Array.from(confirmDialog(element).querySelectorAll('button')).find(
      (b) => text(b) === 'Registrar veredicto',
    ) as HTMLButtonElement).click();
    await settle();
  };

  describe('evaluación del Revisor', () => {
    it('muestra la evaluación final con la identidad del Revisor y los comentarios confidenciales', async () => {
      const { element } = await open();

      const evaluation = text(element.querySelector('.verdict__evaluation'));
      expect(evaluation).toContain('Evaluación final de la versión v1');
      expect(evaluation).toContain('Marta Ruiz');
      expect(evaluation).toContain('marta@unl.edu.ec');
      // 15:00 UTC en la zona institucional (UTC-5) son las 10:00.
      expect(evaluation).toContain('05/11/2026 10:00');
      expect(evaluation).toContain('Originalidad: 4 / 5');
      expect(evaluation).toContain('Ética: 5 / 5');
      expect(evaluation).toContain('Buen trabajo; falta detallar el muestreo.');
      expect(evaluation).toContain('Comentarios confidenciales (solo el Editor)');
      expect(evaluation).toContain('Solo para el Editor: sospecho autocitas.');
    });

    it('la recomendación del Revisor es solo lectura', async () => {
      const { element } = await open({ evaluations: [buildEvaluation({ recommendation: 'REJECT' })] });

      const recommendation = element.querySelector('.verdict__recommendation') as HTMLElement;
      expect(text(recommendation)).toContain('Recomendación del Revisor: Rechazar');
      expect(text(recommendation)).toContain('(solo lectura)');
      expect(recommendation.querySelector('input, select, textarea, button')).toBeNull();
    });

    it('avisa si el Revisor declaró un conflicto de interés', async () => {
      const { element } = await open({ evaluations: [buildEvaluation({ conflict_declared: true })] });

      expect(text(element)).toContain('El Revisor declaró un conflicto de interés.');
    });

    it('solo se usa la evaluación de la versión vigente', async () => {
      const { element } = await open(
        { evaluations: [buildEvaluation({ version_number: 1, reviewer: { id: 'x', full_name: 'Otro Revisor', email: 'o@x.edu' } })] },
        (host) => host.version.set(2),
      );

      expect(element.querySelector('.verdict__evaluation')).toBeNull();
      expect(text(element)).toContain('Aún no hay una evaluación final de la versión vigente');
      expect(element.querySelector('form')).toBeNull();
    });

    it('sin evaluación final no hay formulario y se explica por qué', async () => {
      const { element } = await open({ evaluations: [] });

      expect(text(element)).toContain('El veredicto se habilita cuando el Revisor la envíe.');
      expect(element.querySelector('form')).toBeNull();
    });

    it('un error de carga se explica y permite reintentar', async () => {
      const fixture = TestBed.createComponent(HostComponent);
      fixture.detectChanges();
      const element = fixture.nativeElement as HTMLElement;
      expect(element.querySelector('app-loading-spinner')).not.toBeNull();
      http.expectOne((r) => r.url === EVALUATIONS).flush(errorEnvelope('SERVER_ERROR', 'Error.'), {
        status: 500,
        statusText: 'Server Error',
      });
      // Al fallar la primera, `forkJoin` cancela la segunda petición.
      await fixture.whenStable();
      fixture.detectChanges();

      expect(element.querySelector('app-error-state')).not.toBeNull();

      (element.querySelector('app-error-state button') as HTMLButtonElement).click();
      http.expectOne((r) => r.url === EVALUATIONS).flush(page([buildEvaluation()]));
      // La petición cancelada por `forkJoin` sigue registrada: solo cuenta la nueva.
      http
        .match((r) => r.method === 'GET' && r.url === VERDICTS)
        .filter((r) => !r.cancelled)
        .forEach((r) => r.flush(page([])));
      await fixture.whenStable();
      fixture.detectChanges();

      expect(element.querySelector('app-error-state')).toBeNull();
      expect(element.querySelector('form')).not.toBeNull();
    });
  });

  describe('veredictos registrados', () => {
    it('se listan en solo lectura, sin ningún control para editarlos', async () => {
      const { element } = await open({
        verdicts: [
          buildVerdict({ decision: 'REQUIRES_CORRECTIONS', observations: 'Ampliar el muestreo.', version_number: 1 }),
        ],
      }, (host) => host.version.set(2));

      const history = element.querySelector('.verdict__history') as HTMLElement;
      expect(text(history)).toContain('Requiere correcciones');
      expect(text(history)).toContain('versión v1 · Edgar Mora');
      expect(text(history)).toContain('Observaciones: Ampliar el muestreo.');
      expect(text(history)).toContain('no se edita ni se sobrescribe');
      expect(history.querySelector('button, input, textarea, select, a')).toBeNull();
    });

    it('con la versión vigente ya juzgada desaparece el formulario', async () => {
      const { element } = await open({ verdicts: [buildVerdict({ version_number: 1 })] });

      expect(element.querySelector('form')).toBeNull();
      expect(text(element.querySelector('.verdict__history'))).toContain('Aceptado');
    });

    it('un veredicto de una versión anterior no impide juzgar la vigente', async () => {
      const { element } = await open(
        {
          evaluations: [buildEvaluation({ version_number: 2 })],
          verdicts: [buildVerdict({ version_number: 1, decision: 'REQUIRES_CORRECTIONS', observations: 'x' })],
        },
        (host) => host.version.set(2),
      );

      expect(element.querySelector('form')).not.toBeNull();
      expect(element.querySelectorAll('.verdict__history li').length).toBe(1);
    });

    it('un veredicto de corrección indica que sustituye a otro', async () => {
      const { element } = await open({
        verdicts: [buildVerdict({ id: 'vd-2', previous_verdict: 'vd-1', decision: 'REJECTED', justification: 'Revisado.' })],
      });

      expect(text(element.querySelector('.verdict__history'))).toContain(
        '(sustituye a un veredicto anterior)',
      );
    });

    it('sin permiso para registrar (no está en revisión) solo se lee', async () => {
      const { element } = await open({}, (host) => host.canRegister.set(false));

      expect(element.querySelector('.verdict__evaluation')).not.toBeNull();
      expect(element.querySelector('form')).toBeNull();
    });
  });

  describe('validación', () => {
    it('sin decisión no se envía y se pide elegir', async () => {
      const { element, settle } = await open();

      submitButton(element).click();
      await settle();

      expect(text(element.querySelector('.verdict__error'))).toBe('Seleccione una decisión.');
      expect(confirmDialog(element).open).toBe(false);
      http.expectNone((r) => r.method === 'POST');
    });

    it('rechazar exige la justificación', async () => {
      const { element, settle } = await open({ evaluations: [buildEvaluation({ recommendation: 'REJECT' })] });
      await choose(element, 'Rechazado', settle);
      expect(justification(element)).not.toBeNull();

      submitButton(element).click();
      await settle();

      expect(text(element.querySelector('.verdict__error'))).toBe('Indique la justificación del rechazo.');
      expect(justification(element)!.getAttribute('aria-invalid')).toBe('true');
      expect(confirmDialog(element).open).toBe(false);
      http.expectNone((r) => r.method === 'POST');
    });

    it('una justificación en blanco no cuenta', async () => {
      const { element, settle } = await open({ evaluations: [buildEvaluation({ recommendation: 'REJECT' })] });
      await choose(element, 'Rechazado', settle);
      await write(element, 'textarea[name="justification"]', '   ', settle);

      submitButton(element).click();
      await settle();

      expect(confirmDialog(element).open).toBe(false);
      expect(text(element.querySelector('.verdict__error'))).toContain('justificación');
    });

    it('pedir correcciones exige las observaciones', async () => {
      const { element, settle } = await open({
        evaluations: [buildEvaluation({ recommendation: 'REQUIRES_CORRECTIONS' })],
      });
      await choose(element, 'Requiere correcciones', settle);
      expect(observations(element)).not.toBeNull();

      submitButton(element).click();
      await settle();

      expect(text(element.querySelector('.verdict__error'))).toBe(
        'Indique las observaciones para el Autor.',
      );
      expect(confirmDialog(element).open).toBe(false);
      http.expectNone((r) => r.method === 'POST');
    });

    it('seguir la recomendación no pide justificación ni advierte', async () => {
      const { element, settle } = await open({ evaluations: [buildEvaluation({ recommendation: 'ACCEPT' })] });

      await choose(element, 'Aceptado', settle);

      expect(justification(element)).toBeNull();
      expect(observations(element)).toBeNull();
      expect(element.querySelector('.verdict__warning')).toBeNull();
      submitButton(element).click();
      await settle();
      expect(confirmDialog(element).open).toBe(true);
    });

    it('apartarse de la recomendación lo advierte y exige justificar', async () => {
      const { element, settle } = await open({ evaluations: [buildEvaluation({ recommendation: 'REJECT' })] });

      await choose(element, 'Aceptado', settle);

      expect(text(element.querySelector('.verdict__warning'))).toContain(
        'se aparta de la recomendación del Revisor (Rechazar)',
      );
      expect(justification(element)).not.toBeNull();
      submitButton(element).click();
      await settle();
      expect(text(element.querySelector('.verdict__error'))).toBe(
        'Justifique por qué se aparta de la recomendación del Revisor.',
      );
      expect(confirmDialog(element).open).toBe(false);
    });

    it('pedir correcciones contra una recomendación de aceptar exige ambos textos', async () => {
      const { element, settle } = await open({ evaluations: [buildEvaluation({ recommendation: 'ACCEPT' })] });
      await choose(element, 'Requiere correcciones', settle);

      submitButton(element).click();
      await settle();

      const errors = Array.from(element.querySelectorAll('.verdict__error')).map((e) => text(e));
      expect(errors).toEqual([
        'Justifique por qué se aparta de la recomendación del Revisor.',
        'Indique las observaciones para el Autor.',
      ]);
      expect(element.querySelector('.verdict__warning')).not.toBeNull();
    });

    it('cada texto admite lo que acepta la API', async () => {
      const { element, settle } = await open({ evaluations: [buildEvaluation({ recommendation: 'REJECT' })] });
      await choose(element, 'Rechazado', settle);

      expect(justification(element)!.getAttribute('maxlength')).toBe('5000');
    });
  });

  describe('registro', () => {
    it('pide confirmación explicando la consecuencia de cada decisión', async () => {
      const { element, settle } = await open();

      await choose(element, 'Aceptado', settle);
      submitButton(element).click();
      await settle();

      expect(confirmDialog(element).open).toBe(true);
      expect(text(confirmDialog(element))).toContain('no se puede editar ni sobrescribir');
      expect(text(confirmDialog(element))).toContain('se publicará de inmediato en el catálogo');
      http.expectNone((r) => r.method === 'POST');
    });

    it.each([
      ['Rechazado', 'REJECT', 'no se publicará'],
      ['Requiere correcciones', 'REQUIRES_CORRECTIONS', 'se abrirá la siguiente ronda'],
    ])('explica qué pasa al %s', async (label, recommendation, expected) => {
      const { element, settle } = await open({
        evaluations: [buildEvaluation({ recommendation: recommendation as Recommendation })],
      });
      await choose(element, label, settle);
      await write(element, 'textarea[name="justification"], textarea[name="observations"]', 'Texto', settle);
      if (label === 'Requiere correcciones') {
        await write(element, 'textarea[name="observations"]', 'Texto', settle);
      }

      submitButton(element).click();
      await settle();

      expect(text(confirmDialog(element))).toContain(expected);
    });

    it('cancelar la confirmación no envía nada', async () => {
      const { element, settle } = await open();
      await choose(element, 'Aceptado', settle);
      submitButton(element).click();
      await settle();

      (Array.from(confirmDialog(element).querySelectorAll('button')).find(
        (b) => text(b) === 'Cancelar',
      ) as HTMLButtonElement).click();
      await settle();

      expect(confirmDialog(element).open).toBe(false);
      http.expectNone((r) => r.method === 'POST');
    });

    it('al confirmar envía la decisión con If-Match e Idempotency-Key', async () => {
      const { element, settle } = await open();

      await send(element, settle);

      const request = verdictPost();
      expect(request.request.headers.get('If-Match')).toBe('"4"');
      expect(request.request.headers.get('Idempotency-Key')).toMatch(/^[A-Za-z0-9._:-]{1,100}$/);
      // Sin textos obligatorios, no viajan textos.
      expect(request.request.body).toEqual({
        decision: 'ACCEPTED',
        justification: null,
        observations: null,
      });
      request.flush(buildVerdictResult(), { status: 201, statusText: 'Created', headers: { ETag: '"5"' } });
    });

    it('envía los textos recortados solo cuando la decisión los exige', async () => {
      const { element, settle } = await open({
        evaluations: [buildEvaluation({ recommendation: 'ACCEPT' })],
      });
      await choose(element, 'Requiere correcciones', settle);
      await write(element, 'textarea[name="justification"]', '  Se aparta por el anexo.  ', settle);
      await write(element, 'textarea[name="observations"]', '  Ampliar la sección 3.  ', settle);
      submitButton(element).click();
      await settle();
      (Array.from(confirmDialog(element).querySelectorAll('button')).find(
        (b) => text(b) === 'Registrar veredicto',
      ) as HTMLButtonElement).click();
      await settle();

      const request = verdictPost();
      expect(request.request.body).toEqual({
        decision: 'REQUIRES_CORRECTIONS',
        justification: 'Se aparta por el anexo.',
        observations: 'Ampliar la sección 3.',
      });
      request.flush(buildVerdictResult(), { status: 201, statusText: 'Created' });
    });

    it('un texto escrito y luego innecesario no se envía', async () => {
      const { element, settle } = await open({
        evaluations: [buildEvaluation({ recommendation: 'REQUIRES_CORRECTIONS' })],
      });
      await choose(element, 'Requiere correcciones', settle);
      await write(element, 'textarea[name="observations"]', 'Ampliar la sección 3.', settle);
      await choose(element, 'Aceptado', settle);
      await write(element, 'textarea[name="justification"]', 'Lo acepto igualmente.', settle);
      await choose(element, 'Requiere correcciones', settle);
      submitButton(element).click();
      await settle();
      (Array.from(confirmDialog(element).querySelectorAll('button')).find(
        (b) => text(b) === 'Registrar veredicto',
      ) as HTMLButtonElement).click();
      await settle();

      const request = verdictPost();
      // Seguir la recomendación (correcciones) no necesita justificación: no viaja.
      expect((request.request.body as { justification: string | null }).justification).toBeNull();
      request.flush(buildVerdictResult(), { status: 201, statusText: 'Created' });
    });

    it('al registrarse emite el resultado, lista el veredicto y retira el formulario', async () => {
      const { element, host, settle } = await open();
      await send(element, settle);

      const result = buildVerdictResult({
        verdict: buildVerdict({ id: 'vd-9', decision: 'ACCEPTED' }),
      });
      verdictPost().flush(result, { status: 201, statusText: 'Created', headers: { ETag: '"5"' } });
      await settle();

      expect(host.registered).toEqual([{ result, etag: '"5"' }]);
      expect(element.querySelector('form')).toBeNull();
      expect(text(element.querySelector('.verdict__history'))).toContain('Aceptado');
      expect(host.staleCount).toBe(0);
    });

    it('mientras registra bloquea el envío y no permite repetirlo', async () => {
      const { element, settle } = await open();
      await send(element, settle);

      expect(text(submitButton(element))).toBe('Registrando…');
      expect(submitButton(element).disabled).toBe(true);
      submitButton(element).click();
      await settle();

      const request = verdictPost();
      request.flush(buildVerdictResult(), { status: 201, statusText: 'Created' });
    });

    it('sin ETag no envía y pide releer el detalle', async () => {
      const { element, host, settle } = await open({}, (h) => h.etag.set(null));
      await send(element, settle);

      http.expectNone((r) => r.method === 'POST');
      expect(text(element.querySelector('.verdict__form .verdict__error'))).toContain('recargue');
      expect(host.staleCount).toBe(1);
    });
  });

  describe('errores y reintentos', () => {
    it('un corte de red se reintenta con la misma clave de idempotencia', async () => {
      const { element, settle } = await open();
      await send(element, settle);
      const first = verdictPost();
      const key = first.request.headers.get('Idempotency-Key');
      first.error(new ProgressEvent('error'), { status: 0 });
      await settle();

      expect(text(element.querySelector('.verdict__form .verdict__error'))).not.toBe('');
      submitButton(element).click();
      await settle();
      (Array.from(confirmDialog(element).querySelectorAll('button')).find(
        (b) => text(b) === 'Registrar veredicto',
      ) as HTMLButtonElement).click();
      await settle();

      const retry = verdictPost();
      expect(retry.request.headers.get('Idempotency-Key')).toBe(key);
      retry.flush(buildVerdictResult(), { status: 201, statusText: 'Created' });
    });

    it('si el Editor cambia el contenido, la intención es otra y la clave también', async () => {
      const { element, settle } = await open({ evaluations: [buildEvaluation({ recommendation: 'REJECT' })] });
      await choose(element, 'Rechazado', settle);
      await write(element, 'textarea[name="justification"]', 'Primera versión.', settle);
      submitButton(element).click();
      await settle();
      (Array.from(confirmDialog(element).querySelectorAll('button')).find(
        (b) => text(b) === 'Registrar veredicto',
      ) as HTMLButtonElement).click();
      await settle();
      const first = verdictPost();
      const key = first.request.headers.get('Idempotency-Key');
      first.flush(errorEnvelope('AUDIT_UNAVAILABLE', 'Sin auditoría.'), {
        status: 503,
        statusText: 'Service Unavailable',
      });
      await settle();

      await write(element, 'textarea[name="justification"]', 'Texto corregido.', settle);
      submitButton(element).click();
      await settle();
      (Array.from(confirmDialog(element).querySelectorAll('button')).find(
        (b) => text(b) === 'Registrar veredicto',
      ) as HTMLButtonElement).click();
      await settle();

      const second = verdictPost();
      expect(second.request.headers.get('Idempotency-Key')).not.toBe(key);
      second.flush(buildVerdictResult(), { status: 201, statusText: 'Created' });
    });

    it('si falla la auditoría (503) lo explica, deja reintentar y no pide releer', async () => {
      const { element, host, settle } = await open();
      await send(element, settle);

      verdictPost().flush(errorEnvelope('AUDIT_UNAVAILABLE', 'Sin auditoría.'), {
        status: 503,
        statusText: 'Service Unavailable',
      });
      await settle();

      expect(text(element.querySelector('.verdict__form .verdict__error'))).toContain(
        'Servicio no disponible temporalmente',
      );
      expect(submitButton(element).disabled).toBe(false);
      expect(host.staleCount).toBe(0);
      expect(host.registered).toEqual([]);
    });

    it.each([
      ['VERSION_CONFLICT', 409],
      ['VERDICT_CONFLICT', 409],
      ['STATE_CONFLICT', 409],
    ])('un %s relee los datos y pide releer el detalle', async (code, status) => {
      const { element, host, settle } = await open();
      await send(element, settle);

      verdictPost().flush(errorEnvelope(code, 'Conflicto.'), { status, statusText: 'Conflict' });
      await settle();

      expect(host.staleCount).toBe(1);
      // El formulario se relee: el veredicto que ganó aparecerá en la lista.
      http.expectOne((r) => r.url === EVALUATIONS).flush(page([buildEvaluation()]));
      http.expectOne((r) => r.method === 'GET' && r.url === VERDICTS).flush(page([buildVerdict({ decision: 'REJECTED', justification: 'Otro Editor.' })]));
      await settle();

      expect(element.querySelector('form')).toBeNull();
      expect(text(element.querySelector('.verdict__history'))).toContain('Otro Editor.');
    });
  });
});

describe('justificationRequired', () => {
  it.each([
    ['REJECTED', 'REJECT', true],
    ['REJECTED', null, true],
    ['ACCEPTED', 'ACCEPT', false],
    ['ACCEPTED', 'REJECT', true],
    ['ACCEPTED', null, false],
    ['REQUIRES_CORRECTIONS', 'REQUIRES_CORRECTIONS', false],
    ['REQUIRES_CORRECTIONS', 'ACCEPT', true],
  ] as const)('%s con recomendación %s → %s', (decision, recommendation, expected) => {
    expect(justificationRequired(decision, recommendation)).toBe(expected);
  });

  it('sin decisión no se exige nada', () => {
    expect(justificationRequired(null, 'ACCEPT')).toBe(false);
  });
});

describe('verdictFormErrors', () => {
  const value = (overrides: Partial<Parameters<typeof verdictFormErrors>[0]> = {}) => ({
    decision: 'ACCEPTED' as const,
    justification: '',
    observations: '',
    ...overrides,
  });

  it('un formulario válido no tiene errores', () => {
    expect(verdictFormErrors(value(), 'ACCEPT')).toEqual({});
    expect(
      verdictFormErrors(value({ decision: 'REJECTED', justification: 'Motivo.' }), 'REJECT'),
    ).toEqual({});
    expect(
      verdictFormErrors(
        value({ decision: 'REQUIRES_CORRECTIONS', observations: 'Corregir.' }),
        'REQUIRES_CORRECTIONS',
      ),
    ).toEqual({});
  });

  it('sin decisión solo pide la decisión', () => {
    expect(verdictFormErrors(value({ decision: null }), 'ACCEPT')).toEqual({
      decision: 'Seleccione una decisión.',
    });
  });

  it('distingue el motivo de la justificación obligatoria', () => {
    expect(verdictFormErrors(value({ decision: 'REJECTED' }), 'REJECT').justification).toBe(
      'Indique la justificación del rechazo.',
    );
    expect(verdictFormErrors(value({ decision: 'ACCEPTED' }), 'REJECT').justification).toBe(
      'Justifique por qué se aparta de la recomendación del Revisor.',
    );
  });

  it('los espacios no cuentan como texto', () => {
    expect(
      verdictFormErrors(value({ decision: 'REJECTED', justification: '   ' }), 'REJECT'),
    ).toHaveProperty('justification');
    expect(
      verdictFormErrors(
        value({ decision: 'REQUIRES_CORRECTIONS', observations: ' \n ' }),
        'REQUIRES_CORRECTIONS',
      ),
    ).toHaveProperty('observations');
  });
});
