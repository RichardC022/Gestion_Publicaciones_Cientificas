import { provideHttpClient } from '@angular/common/http';
import {
  HttpTestingController,
  TestRequest,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';
import { vi } from 'vitest';

import { API_BASE_URL } from '../../../core/http/api-base-url.token';
import { ReviewerAssignmentDetail, ReviewerEvaluation } from '../../../core/models/reviewer.model';
import { errorEnvelope } from '../../author/testing/manuscript.fixtures';
import {
  buildAssignmentDetail,
  buildCompleteEvaluation,
  buildReviewerEvaluation,
} from '../testing/reviewer.fixtures';
import { EvaluationFormComponent } from './evaluation-form.component';

@Component({ template: '' })
class BlankComponent {}

const DETAIL = '/api/reviewer/assignments/a-1/';
const EVALUATION = '/api/reviewer/assignments/a-1/evaluation/';
const SUBMIT = '/api/reviewer/assignments/a-1/evaluation/submit/';
const PAGE_URL = '/app/reviewer/assignments/a-1/evaluate';
const NOW = new Date('2026-10-27T12:00:00Z');

describe('EvaluationFormComponent', () => {
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
        provideRouter([
          { path: 'app/reviewer/assignments/:id/evaluate', component: EvaluationFormComponent },
          { path: 'app/reviewer/assignments/:id', component: BlankComponent },
          { path: 'app/reviewer/assignments', component: BlankComponent },
        ]),
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: API_BASE_URL, useValue: '/api/' },
      ],
    });
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    http.verify();
    vi.useRealTimers();
  });

  const text = (node: Element | null) => (node?.textContent ?? '').replace(/\s+/g, ' ').trim();

  const open = async (
    evaluation: ReviewerEvaluation = buildReviewerEvaluation(),
    etag = '"0"',
    detail: ReviewerAssignmentDetail = buildAssignmentDetail({ due_at: '2026-11-10T15:00:00Z' }),
  ) => {
    const harness = await RouterTestingHarness.create();
    const component = await harness.navigateByUrl(PAGE_URL, EvaluationFormComponent);
    const element = harness.routeNativeElement as HTMLElement;
    const settle = async () => {
      await harness.fixture.whenStable();
      harness.detectChanges();
    };
    http.expectOne((r) => r.url === DETAIL).flush(detail);
    http.expectOne((r) => r.url === EVALUATION).flush(evaluation, { headers: { ETag: etag } });
    await settle();
    return { harness, component, element, settle };
  };

  const radio = (element: HTMLElement, field: string, value: string) =>
    Array.from(
      element.querySelectorAll<HTMLInputElement>(
        `input[type="radio"][name^="evaluation-${field}-"]`,
      ),
    ).find((input) => input.value === value)!;

  const choose = async (
    view: { element: HTMLElement; settle: () => Promise<void> },
    field: string,
    value: string,
  ) => {
    const input = radio(view.element, field, value);
    input.checked = true;
    input.dispatchEvent(new Event('change', { bubbles: true }));
    await view.settle();
  };

  const type = async (
    view: { element: HTMLElement; settle: () => Promise<void> },
    index: 0 | 1,
    value: string,
  ) => {
    const area = view.element.querySelectorAll<HTMLTextAreaElement>('textarea')[index];
    area.value = value;
    area.dispatchEvent(new Event('input', { bubbles: true }));
    await view.settle();
  };

  const declare = async (view: { element: HTMLElement; settle: () => Promise<void> }) => {
    const box = view.element.querySelector<HTMLInputElement>('input[type="checkbox"]')!;
    box.checked = true;
    box.dispatchEvent(new Event('change', { bubbles: true }));
    await view.settle();
  };

  const button = (element: HTMLElement, label: string) =>
    Array.from(element.querySelectorAll<HTMLButtonElement>('button')).find(
      (b) => text(b) === label,
    )!;

  const confirmDialog = (element: HTMLElement) =>
    element.querySelector('dialog') as HTMLDialogElement;

  const flushSave = (
    expectedEtag: string,
    response: ReviewerEvaluation,
    nextEtag: string,
  ): TestRequest => {
    const request = http.expectOne((r) => r.method === 'PUT' && r.url === EVALUATION);
    expect(request.request.headers.get('If-Match')).toBe(expectedEtag);
    request.flush(response, { headers: { ETag: nextEtag } });
    return request;
  };

  describe('carga', () => {
    it('muestra los criterios, la recomendación y los comentarios', async () => {
      const { element } = await open();

      const legends = Array.from(element.querySelectorAll('legend')).map((l) => text(l));
      expect(legends).toEqual([
        'Originalidad',
        'Metodología',
        'Claridad',
        'Relevancia',
        'Ética',
        'Recomendación al Editor',
      ]);
      expect(element.querySelectorAll('input[type="radio"]').length).toBe(5 * 5 + 3);
      expect(element.querySelectorAll('textarea').length).toBe(2);
      expect(text(element)).toContain('Evaluación: Efecto del clima en cultivos andinos');
      expect(text(element)).toContain('Su borrador es privado');
      expect(element.querySelector('app-deadline-countdown')).not.toBeNull();
    });

    it('carga el borrador guardado en los controles', async () => {
      const { element } = await open(buildCompleteEvaluation(), '"3"');

      expect(radio(element, 'originality_score', '4').checked).toBe(true);
      expect(radio(element, 'methodology_score', '3').checked).toBe(true);
      expect(radio(element, 'recommendation', 'REQUIRES_CORRECTIONS').checked).toBe(true);
      const areas = element.querySelectorAll<HTMLTextAreaElement>('textarea');
      expect(areas[0].value).toBe('Aclarar la metodología.');
      expect(areas[1].value).toBe('Revisar la muestra.');
    });

    it('si la carga falla explica el error y permite reintentar', async () => {
      const harness = await RouterTestingHarness.create();
      await harness.navigateByUrl(PAGE_URL, EvaluationFormComponent);
      http.expectOne((r) => r.url === DETAIL).flush(buildAssignmentDetail());
      http
        .expectOne((r) => r.url === EVALUATION)
        .flush(errorEnvelope('SERVER_ERROR', 'Error.'), {
          status: 500,
          statusText: 'Server Error',
        });
      await harness.fixture.whenStable();
      harness.detectChanges();

      const element = harness.routeNativeElement as HTMLElement;
      expect(element.querySelector('[role="alert"]')).not.toBeNull();
      expect(element.querySelector('form')).toBeNull();
    });
  });

  describe('borrador', () => {
    it('se guarda sin completar los demás campos y no pide la declaración', async () => {
      const view = await open();
      await choose(view, 'originality_score', '4');

      button(view.element, 'Guardar borrador').click();
      await view.settle();
      const request = flushSave(
        '"0"',
        buildReviewerEvaluation({ id: 'ev-1', originality_score: 4 }),
        '"1"',
      );
      await view.settle();

      expect(request.request.body).toEqual({
        originality_score: 4,
        methodology_score: null,
        clarity_score: null,
        relevance_score: null,
        ethics_score: null,
        recommendation: null,
        comments_for_author: null,
        confidential_comments: null,
      });
      expect(text(view.element)).toContain('Borrador guardado.');
      expect(view.element.querySelector('.field__error')).toBeNull();
    });

    it('«Guardar borrador» está deshabilitado mientras no haya cambios', async () => {
      const view = await open();
      expect(button(view.element, 'Guardar borrador').disabled).toBe(true);

      await type(view, 0, 'Algo');
      expect(button(view.element, 'Guardar borrador').disabled).toBe(false);
    });

    it('cada guardado usa el ETag del anterior', async () => {
      const view = await open();
      await type(view, 0, 'Primero');
      button(view.element, 'Guardar borrador').click();
      await view.settle();
      flushSave(
        '"0"',
        buildReviewerEvaluation({ id: 'ev-1', comments_for_author: 'Primero' }),
        '"1"',
      );
      await view.settle();

      await type(view, 0, 'Segundo');
      button(view.element, 'Guardar borrador').click();
      await view.settle();
      flushSave(
        '"1"',
        buildReviewerEvaluation({ id: 'ev-1', comments_for_author: 'Segundo' }),
        '"2"',
      );
      await view.settle();
    });

    it('no se comparte con el Autor: lo declara y no pide nada del Autor', async () => {
      const { element } = await open();

      expect(text(element)).toContain('no se comparte con el Autor');
      expect(text(element)).toContain('solo los ve el Editor');
    });

    it('avisa de cambios sin guardar hasta que se guardan', async () => {
      const view = await open();
      expect(view.component.hasUnsavedChanges()).toBe(false);

      await type(view, 0, 'Texto nuevo');
      expect(view.component.hasUnsavedChanges()).toBe(true);

      button(view.element, 'Guardar borrador').click();
      await view.settle();
      flushSave(
        '"0"',
        buildReviewerEvaluation({ id: 'ev-1', comments_for_author: 'Texto nuevo' }),
        '"1"',
      );
      await view.settle();
      expect(view.component.hasUnsavedChanges()).toBe(false);
    });
  });

  describe('envío final', () => {
    it('vacío: señala todo lo que falta, incluida la declaración, y no envía nada', async () => {
      const view = await open();

      button(view.element, 'Enviar evaluación').click();
      await view.settle();

      const summary = Array.from(view.element.querySelectorAll('[role="alert"] li')).map((li) =>
        text(li),
      );
      expect(summary).toHaveLength(8);
      expect(summary.join(' ')).toContain('declarar que no tiene conflicto de interés');
      expect(view.element.querySelectorAll('.field__error').length).toBe(8);
      expect(confirmDialog(view.element).hasAttribute('open')).toBe(false);
      http.expectNone(SUBMIT);
      http.expectNone((r) => r.method === 'PUT');
    });

    it('sin la declaración de conflicto no se envía', async () => {
      const view = await open(buildCompleteEvaluation(), '"2"');

      button(view.element, 'Enviar evaluación').click();
      await view.settle();

      expect(
        Array.from(view.element.querySelectorAll('.field__error')).map((e) => text(e)),
      ).toEqual(['Debe declarar que no tiene conflicto de interés para enviar la evaluación.']);
      http.expectNone(SUBMIT);
    });

    it('los comentarios confidenciales son opcionales', async () => {
      const view = await open(buildCompleteEvaluation({ confidential_comments: null }), '"2"');
      await declare(view);

      button(view.element, 'Enviar evaluación').click();
      await view.settle();

      expect(confirmDialog(view.element).hasAttribute('open')).toBe(true);
    });

    it('pide confirmación y cancelar no envía', async () => {
      const view = await open(buildCompleteEvaluation(), '"2"');
      await declare(view);

      button(view.element, 'Enviar evaluación').click();
      await view.settle();
      const dialog = confirmDialog(view.element);
      expect(dialog.hasAttribute('open')).toBe(true);
      expect(text(dialog)).toContain('El envío es definitivo');

      button(dialog as unknown as HTMLElement, 'Cancelar').click();
      await view.settle();

      http.expectNone(SUBMIT);
      expect(dialog.hasAttribute('open')).toBe(false);
    });

    it('sin cambios pendientes envía directamente con el ETag vigente', async () => {
      const view = await open(buildCompleteEvaluation(), '"2"');
      await declare(view);
      button(view.element, 'Enviar evaluación').click();
      await view.settle();

      button(confirmDialog(view.element) as unknown as HTMLElement, 'Enviar evaluación').click();
      await view.settle();
      const request = http.expectOne(SUBMIT);
      expect(request.request.headers.get('If-Match')).toBe('"2"');
      request.flush(
        buildCompleteEvaluation({ status: 'FINAL', submitted_at: '2026-10-27T15:00:00Z' }),
        { headers: { ETag: '"3"' } },
      );
      await view.settle();

      expect(text(view.element)).toContain('Evaluación enviada');
      expect(text(view.element)).toContain('27/10/2026 10:00');
      expect(view.element.querySelector('textarea')!.readOnly).toBe(true);
      expect(radio(view.element, 'ethics_score', '5').disabled).toBe(true);
      expect(view.component.hasUnsavedChanges()).toBe(false);
    });

    it('con cambios pendientes guarda primero y envía con el ETag nuevo', async () => {
      const view = await open(buildCompleteEvaluation(), '"2"');
      await type(view, 0, 'Comentarios ajustados');
      await declare(view);
      button(view.element, 'Enviar evaluación').click();
      await view.settle();

      button(confirmDialog(view.element) as unknown as HTMLElement, 'Enviar evaluación').click();
      await view.settle();
      flushSave(
        '"2"',
        buildCompleteEvaluation({ comments_for_author: 'Comentarios ajustados' }),
        '"3"',
      );
      await view.settle();
      const submit = http.expectOne(SUBMIT);
      expect(submit.request.headers.get('If-Match')).toBe('"3"');
      submit.flush(
        buildCompleteEvaluation({ status: 'FINAL', submitted_at: '2026-10-27T15:00:00Z' }),
        {
          headers: { ETag: '"4"' },
        },
      );
      await view.settle();

      expect(text(view.element)).toContain('Evaluación enviada');
    });

    it('si guardar falla antes de enviar, no envía y conserva el texto', async () => {
      const view = await open(buildCompleteEvaluation(), '"2"');
      await type(view, 0, 'Texto importante');
      await declare(view);
      button(view.element, 'Enviar evaluación').click();
      await view.settle();

      button(confirmDialog(view.element) as unknown as HTMLElement, 'Enviar evaluación').click();
      await view.settle();
      http
        .expectOne((r) => r.method === 'PUT')
        .flush(errorEnvelope('AUDIT_UNAVAILABLE', 'No disponible.'), {
          status: 503,
          statusText: 'Service Unavailable',
        });
      await view.settle();

      http.expectNone(SUBMIT);
      expect(view.element.querySelector('textarea')!.value).toBe('Texto importante');
      expect(text(view.element.querySelector('.callout--error'))).toContain(
        'Servicio no disponible',
      );
      expect(button(view.element, 'Enviar evaluación').disabled).toBe(false);
    });

    it('un 400 del servidor marca los campos que faltan', async () => {
      const view = await open(buildCompleteEvaluation(), '"2"');
      await declare(view);
      button(view.element, 'Enviar evaluación').click();
      await view.settle();
      button(confirmDialog(view.element) as unknown as HTMLElement, 'Enviar evaluación').click();
      await view.settle();

      http.expectOne(SUBMIT).flush(
        errorEnvelope('VALIDATION_ERROR', 'Complete la evaluación antes de enviarla.', {
          clarity_score: ['Este campo es obligatorio para enviar la evaluación.'],
        }),
        { status: 400, statusText: 'Bad Request' },
      );
      await view.settle();

      expect(text(view.element.querySelector('.field__error'))).toBe(
        'Este campo es obligatorio para enviar la evaluación.',
      );
    });
  });

  describe('conflictos del servidor sin perder el texto', () => {
    it('409 por versión: conserva el texto y ofrece elegir', async () => {
      const view = await open(buildCompleteEvaluation(), '"2"');
      await type(view, 0, 'Mi texto sin perder');
      button(view.element, 'Guardar borrador').click();
      await view.settle();

      http
        .expectOne((r) => r.method === 'PUT')
        .flush(errorEnvelope('VERSION_CONFLICT', 'Desfasado.', { lock_version: 3 }), {
          status: 409,
          statusText: 'Conflict',
        });
      await view.settle();

      expect(text(view.element.querySelector('[role="alert"]'))).toContain(
        'El borrador cambió desde que lo abrió',
      );
      expect(view.element.querySelector('textarea')!.value).toBe('Mi texto sin perder');
      expect(button(view.element, 'Enviar evaluación').disabled).toBe(true);
    });

    it('«Conservar mi texto» toma el ETag vigente y deja guardar de nuevo', async () => {
      const view = await open(buildCompleteEvaluation(), '"2"');
      await type(view, 0, 'Mi texto sin perder');
      button(view.element, 'Guardar borrador').click();
      await view.settle();
      http
        .expectOne((r) => r.method === 'PUT')
        .flush(errorEnvelope('VERSION_CONFLICT', 'Desfasado.'), {
          status: 409,
          statusText: 'Conflict',
        });
      await view.settle();

      button(view.element, 'Conservar mi texto').click();
      await view.settle();
      http
        .expectOne((r) => r.method === 'GET' && r.url === EVALUATION)
        .flush(buildCompleteEvaluation({ comments_for_author: 'De otra pestaña' }), {
          headers: { ETag: '"3"' },
        });
      await view.settle();

      expect(view.element.querySelector('textarea')!.value).toBe('Mi texto sin perder');
      expect(view.element.querySelector('#stale-title')).toBeNull();
      button(view.element, 'Guardar borrador').click();
      await view.settle();
      const request = flushSave(
        '"3"',
        buildCompleteEvaluation({ comments_for_author: 'Mi texto sin perder' }),
        '"4"',
      );
      expect(request.request.body.comments_for_author).toBe('Mi texto sin perder');
    });

    it('«Usar la versión guardada» reemplaza el texto por el del servidor', async () => {
      const view = await open(buildCompleteEvaluation(), '"2"');
      await type(view, 0, 'Mi texto');
      button(view.element, 'Guardar borrador').click();
      await view.settle();
      http
        .expectOne((r) => r.method === 'PUT')
        .flush(errorEnvelope('VERSION_CONFLICT', 'Desfasado.'), {
          status: 409,
          statusText: 'Conflict',
        });
      await view.settle();

      button(view.element, 'Usar la versión guardada').click();
      await view.settle();
      http
        .expectOne((r) => r.method === 'GET' && r.url === EVALUATION)
        .flush(buildCompleteEvaluation({ comments_for_author: 'De otra pestaña' }), {
          headers: { ETag: '"3"' },
        });
      await view.settle();

      expect(view.element.querySelector('textarea')!.value).toBe('De otra pestaña');
      expect(view.component.hasUnsavedChanges()).toBe(false);
    });

    it('410 al guardar: bloquea los campos pero deja el texto a la vista', async () => {
      const view = await open(buildCompleteEvaluation(), '"2"');
      await type(view, 0, 'Texto que no debe desaparecer');
      button(view.element, 'Guardar borrador').click();
      await view.settle();

      http
        .expectOne((r) => r.method === 'PUT')
        .flush(errorEnvelope('STATE_CONFLICT', 'El plazo de evaluación venció.'), {
          status: 410,
          statusText: 'Gone',
        });
      await view.settle();

      const area = view.element.querySelector('textarea')!;
      expect(area.value).toBe('Texto que no debe desaparecer');
      expect(area.readOnly).toBe(true);
      expect(text(view.element)).toContain('El plazo de evaluación venció');
      expect(button(view.element, 'Guardar borrador').disabled).toBe(true);
      expect(button(view.element, 'Enviar evaluación').disabled).toBe(true);
    });

    it('410 al enviar: bloquea y conserva todo lo escrito', async () => {
      const view = await open(buildCompleteEvaluation(), '"2"');
      await declare(view);
      button(view.element, 'Enviar evaluación').click();
      await view.settle();
      button(confirmDialog(view.element) as unknown as HTMLElement, 'Enviar evaluación').click();
      await view.settle();

      http.expectOne(SUBMIT).flush(errorEnvelope('STATE_CONFLICT', 'Plazo vencido.'), {
        status: 410,
        statusText: 'Gone',
      });
      await view.settle();

      expect(text(view.element)).toContain('El plazo de evaluación venció');
      expect(view.element.querySelectorAll<HTMLTextAreaElement>('textarea')[0].value).toBe(
        'Aclarar la metodología.',
      );
      expect(radio(view.element, 'clarity_score', '5').checked).toBe(true);
    });

    it('409 de estado (por ejemplo, ya enviada): bloquea con el mensaje del servidor', async () => {
      const view = await open(buildCompleteEvaluation(), '"2"');
      await type(view, 0, 'Otro texto');
      button(view.element, 'Guardar borrador').click();
      await view.settle();

      http
        .expectOne((r) => r.method === 'PUT')
        .flush(
          errorEnvelope('STATE_CONFLICT', 'La evaluación ya fue enviada y no admite cambios.'),
          { status: 409, statusText: 'Conflict' },
        );
      await view.settle();

      expect(text(view.element)).toContain('La evaluación ya fue enviada y no admite cambios.');
      expect(view.element.querySelector('textarea')!.value).toBe('Otro texto');
      expect(view.element.querySelector('textarea')!.readOnly).toBe(true);
    });

    it('un error de red no bloquea ni borra: se puede reintentar', async () => {
      const view = await open(buildCompleteEvaluation(), '"2"');
      await type(view, 0, 'Texto en riesgo');
      button(view.element, 'Guardar borrador').click();
      await view.settle();

      http.expectOne((r) => r.method === 'PUT').error(new ProgressEvent('error'));
      await view.settle();

      expect(text(view.element.querySelector('.callout--error'))).toContain(
        'No fue posible conectar con el servidor',
      );
      expect(view.element.querySelector('textarea')!.value).toBe('Texto en riesgo');
      expect(button(view.element, 'Guardar borrador').disabled).toBe(false);
      button(view.element, 'Guardar borrador').click();
      await view.settle();
      flushSave('"2"', buildCompleteEvaluation({ comments_for_author: 'Texto en riesgo' }), '"3"');
    });
  });

  describe('bloqueos al cargar', () => {
    it('con conflicto de interés declarado el formulario queda bloqueado', async () => {
      const { element } = await open(buildCompleteEvaluation({ conflict_declared: true }), '"2"');

      expect(text(element)).toContain('Declaró un conflicto de interés');
      expect(element.querySelector('textarea')!.readOnly).toBe(true);
      expect(button(element, 'Guardar borrador').disabled).toBe(true);
      expect(button(element, 'Enviar evaluación').disabled).toBe(true);
    });

    it('una evaluación ya final se muestra enviada y de solo lectura', async () => {
      const { element, component } = await open(
        buildCompleteEvaluation({ status: 'FINAL', submitted_at: '2026-10-25T20:00:00Z' }),
        '"5"',
        buildAssignmentDetail({ status: 'COMPLETED', state: 'EVALUATED', document_url: null }),
      );

      expect(text(element)).toContain('Evaluación enviada');
      expect(text(element)).toContain('25/10/2026 15:00');
      expect(element.querySelector('textarea')!.readOnly).toBe(true);
      expect(button(element, 'Enviar evaluación').disabled).toBe(true);
      expect(component.hasUnsavedChanges()).toBe(false);
    });

    it('con el plazo vencido según el servidor bloquea guardado y envío', async () => {
      const { element } = await open(
        buildCompleteEvaluation(),
        '"2"',
        buildAssignmentDetail({ is_overdue: true, state: 'OVERDUE' }),
      );

      expect(text(element)).toContain('El plazo de evaluación venció');
      expect(element.querySelector('textarea')!.readOnly).toBe(true);
      expect(button(element, 'Enviar evaluación').disabled).toBe(true);
      expect(text(element.querySelector('app-deadline-countdown'))).toContain('Plazo vencido');
    });

    it('al vencer el contador con el formulario abierto bloquea el envío', async () => {
      vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval', 'Date'] });
      vi.setSystemTime(NOW);
      const view = await open(
        buildCompleteEvaluation(),
        '"2"',
        buildAssignmentDetail({ due_at: '2026-10-27T12:00:02Z' }),
      );
      expect(button(view.element, 'Enviar evaluación').disabled).toBe(false);

      vi.advanceTimersByTime(2_000);
      await view.settle();

      expect(button(view.element, 'Enviar evaluación').disabled).toBe(true);
      expect(view.element.querySelectorAll<HTMLTextAreaElement>('textarea')[0].value).toBe(
        'Aclarar la metodología.',
      );
    });
  });

  describe('doble ciego', () => {
    it('no pinta datos de autoría aunque la respuesta los trajera', async () => {
      const leaky = {
        ...buildAssignmentDetail(),
        authors: [{ full_name: 'Ana López Reservada', email: 'ana@unl.edu.ec' }],
      } as ReviewerAssignmentDetail;

      const { element } = await open(buildReviewerEvaluation(), '"0"', leaky);

      expect(element.innerHTML).not.toContain('Ana López Reservada');
      expect(element.innerHTML).not.toContain('ana@unl.edu.ec');
    });
  });
});
