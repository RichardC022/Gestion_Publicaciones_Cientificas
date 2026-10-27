import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';

import { API_BASE_URL } from '../../../core/http/api-base-url.token';
import { EditorEvaluation, SubmissionDetail, Verdict } from '../../../core/models/editor.model';
import { errorEnvelope } from '../../author/testing/manuscript.fixtures';
import {
  buildAssignment,
  buildEvaluation,
  buildReviewer,
  buildSubmissionDetail,
  buildVerdict,
  buildVerdictResult,
} from '../testing/editor.fixtures';
import { SubmissionDetailComponent } from './submission-detail.component';

const DETAIL_URL = '/api/editor/submissions/s-1/';

const emptyPage = <T>(results: T[] = []) => ({ count: results.length, next: null, previous: null, results });

describe('SubmissionDetailComponent', () => {
  let http: HttpTestingController;
  /** Lo que responden las evaluaciones y los veredictos que el formulario de veredicto pide. */
  let verdictData: { evaluations: EditorEvaluation[]; verdicts: Verdict[] };

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
    verdictData = { evaluations: [], verdicts: [] };
    TestBed.configureTestingModule({
      providers: [
        provideRouter([
          { path: 'app/editor/submissions/:id', component: SubmissionDetailComponent },
        ]),
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: API_BASE_URL, useValue: '/api/' },
      ],
    });
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  /** Responde las peticiones de evaluaciones y veredictos que haya pendientes. */
  const answerVerdictData = () => {
    http
      .match((r) => r.url === '/api/editor/manuscripts/s-1/evaluations/')
      .forEach((r) => r.flush(emptyPage(verdictData.evaluations)));
    http
      .match((r) => r.method === 'GET' && r.url === '/api/editor/manuscripts/s-1/verdicts/')
      .forEach((r) => r.flush(emptyPage(verdictData.verdicts)));
  };

  const text = (node: Element | null) => (node?.textContent ?? '').replace(/\s+/g, ' ').trim();

  /** Abre el detalle de `s-1` y responde con el envío indicado. */
  const open = async (overrides: Partial<SubmissionDetail> = {}, etag = '"0"') => {
    const harness = await RouterTestingHarness.create();
    await harness.navigateByUrl('/app/editor/submissions/s-1', SubmissionDetailComponent);
    const element = harness.routeNativeElement as HTMLElement;
    const settle = async () => {
      await harness.fixture.whenStable();
      harness.detectChanges();
      // El formulario de veredicto pide sus datos al montarse (envíos ya en revisión).
      answerVerdictData();
      await harness.fixture.whenStable();
      harness.detectChanges();
    };
    http
      .expectOne(DETAIL_URL)
      .flush(buildSubmissionDetail(overrides), { headers: { ETag: etag } });
    await settle();
    return { harness, element, settle };
  };

  /** Diálogo de confirmación del paso a revisión (la página tiene tres diálogos). */
  const dialog = (element: HTMLElement) =>
    element.querySelector('app-confirm-dialog dialog') as HTMLDialogElement;
  const assignDialog = (element: HTMLElement) =>
    element.querySelector('app-assign-reviewer-dialog dialog') as HTMLDialogElement;
  const revokeDialog = (element: HTMLElement) =>
    element.querySelector('app-revoke-assignment-dialog dialog') as HTMLDialogElement;
  const inDialog = (root: HTMLDialogElement, label: string) =>
    Array.from(root.querySelectorAll('button')).find((b) => text(b).includes(label)) as
      | HTMLButtonElement
      | undefined;
  /** Botón de la página; el diálogo de confirmación siempre está en el DOM y no cuenta. */
  const button = (element: HTMLElement, label: string) =>
    Array.from(element.querySelectorAll('button')).find(
      (b) => !b.closest('dialog') && text(b) === label,
    ) as HTMLButtonElement | undefined;
  const dialogButton = (element: HTMLElement, label: string) =>
    Array.from(dialog(element).querySelectorAll('button')).find(
      (b) => text(b) === label,
    ) as HTMLButtonElement;

  describe('contenido', () => {
    it('muestra los metadatos completos y las insignias del envío', async () => {
      const { element } = await open({ current_version: 2, current_round: 1 });

      expect(text(element.querySelector('h1'))).toBe('Efecto del clima en cultivos andinos');
      expect(text(element.querySelector('.detail-code'))).toBe('GPC-2026-000001');
      const badges = text(element.querySelector('.detail-badges'));
      expect(badges).toContain('Enviado');
      expect(badges).toContain('Ronda 1');
      expect(badges).toContain('Versión v2');
      const metadata = text(element.querySelector('[aria-labelledby="metadata-title"]'));
      expect(metadata).toContain('Agronomía');
      expect(metadata).toContain('clima, cultivos');
      expect(metadata).toContain('Resumen del estudio de campo.');
    });

    it('lista a los autores con su correo y filiación', async () => {
      const { element } = await open();

      const rows = Array.from(element.querySelectorAll('[aria-labelledby="authors-title"] tbody tr'))
        .map((row) => Array.from(row.querySelectorAll('td')).map((c) => text(c)));
      expect(rows).toEqual([
        ['Ana López Correspondencia', 'a.lopez@unl.edu.ec', 'Universidad Nacional de Loja'],
        ['Luis Pérez', 'luis@otra.edu', 'Otra Universidad'],
      ]);
    });

    it('muestra cada versión con su sello de integridad y no expone rutas del volumen', async () => {
      const { element } = await open();

      const versions = text(element.querySelector('[aria-labelledby="versions-title"]'));
      expect(versions).toContain('Versión v1');
      expect(versions).toContain('articulo.pdf');
      expect(versions).toContain(`sha256:${'a'.repeat(64)}`);
      expect(versions).toContain('Vigente');
      const html = element.innerHTML;
      expect(html).not.toContain('file_url');
      expect(html).not.toContain('/api/manuscripts/s-1/versions');
      expect(html).not.toContain('/private/');
    });

    it('muestra el historial cronológico', async () => {
      const { element } = await open();

      const entries = Array.from(element.querySelectorAll('.timeline li')).map((li) => text(li));
      expect(entries.length).toBe(2);
      expect(entries[0]).toContain('Borrador creado.');
      expect(entries[1]).toContain('Versión v1 enviada (ronda 0).');
      // 15:30 UTC en la zona institucional (UTC-5) son las 10:30.
      expect(entries[1]).toContain('21/10/2026 10:30');
    });

    it('no muestra datos de auditoría global ni acciones de Administrador', async () => {
      const { element } = await open();

      const content = text(element).toLowerCase();
      expect(content).not.toContain('auditor');
      expect(content).not.toContain('administrador');
      expect(element.querySelector('a[href*="/admin"]')).toBeNull();
    });

    it('un envío dado de baja se muestra en solo lectura', async () => {
      const { element } = await open({ is_active: false, withdrawn_at: '2026-10-22T15:00:00Z' });

      expect(text(element)).toContain('Dado de baja');
      expect(button(element, 'Pasar a revisión')).toBeUndefined();
    });
  });

  describe('estados', () => {
    it('muestra el indicador de carga hasta que llega la respuesta', async () => {
      const harness = await RouterTestingHarness.create();
      await harness.navigateByUrl('/app/editor/submissions/s-1', SubmissionDetailComponent);
      const element = harness.routeNativeElement as HTMLElement;

      expect(element.querySelector('app-loading-spinner')).not.toBeNull();
      http.expectOne(DETAIL_URL).flush(buildSubmissionDetail());
      await harness.fixture.whenStable();
      harness.detectChanges();

      expect(element.querySelector('app-loading-spinner')).toBeNull();
    });

    it('un envío fuera del ámbito (404) se explica y permite reintentar', async () => {
      const harness = await RouterTestingHarness.create();
      await harness.navigateByUrl('/app/editor/submissions/s-1', SubmissionDetailComponent);
      const element = harness.routeNativeElement as HTMLElement;
      http
        .expectOne(DETAIL_URL)
        .flush(errorEnvelope('NOT_FOUND', 'No encontrado.'), {
          status: 404,
          statusText: 'Not Found',
        });
      await harness.fixture.whenStable();
      harness.detectChanges();

      expect(element.querySelector('app-error-state')).not.toBeNull();
      expect(element.querySelector('h1')).toBeNull();

      (element.querySelector('app-error-state button') as HTMLButtonElement).click();
      http.expectOne(DETAIL_URL).flush(buildSubmissionDetail());
      await harness.fixture.whenStable();
      harness.detectChanges();

      expect(element.querySelector('app-error-state')).toBeNull();
      expect(text(element.querySelector('h1'))).toContain('Efecto del clima');
    });
  });

  describe('paso a revisión', () => {
    const START_URL = '/api/editor/submissions/s-1/start-review/';

    it('solo se ofrece a un envío enviado y activo', async () => {
      const { element } = await open();

      expect(button(element, 'Pasar a revisión')).toBeDefined();
    });

    it.each(['UNDER_REVIEW', 'REQUIRES_CORRECTIONS', 'ACCEPTED', 'REJECTED'] as const)(
      'no se ofrece en estado %s',
      async (status) => {
        const { element } = await open({ status });

        expect(button(element, 'Pasar a revisión')).toBeUndefined();
      },
    );

    it('pide confirmación y explica la consecuencia antes de actuar', async () => {
      const { element, settle } = await open();
      expect(dialog(element).open).toBe(false);

      button(element, 'Pasar a revisión')!.click();
      await settle();

      expect(dialog(element).open).toBe(true);
      expect(text(dialog(element))).toContain('pasará a «En revisión»');
      http.expectNone(START_URL);
    });

    it('cancelar no cambia nada ni llama a la API', async () => {
      const { element, settle } = await open();
      button(element, 'Pasar a revisión')!.click();
      await settle();

      dialogButton(element, 'Cancelar').click();
      await settle();

      expect(dialog(element).open).toBe(false);
      http.expectNone(START_URL);
      expect(text(element.querySelector('.detail-badges'))).toContain('Enviado');
    });

    it('al confirmar llama a la API y refleja el estado actualizado', async () => {
      const { element, settle } = await open();
      button(element, 'Pasar a revisión')!.click();
      await settle();

      dialogButton(element, 'Pasar a revisión').click();
      await settle();
      const request = http.expectOne(START_URL);
      expect(request.request.method).toBe('POST');
      request.flush({ id: 's-1', code: 'GPC-2026-000001', status: 'UNDER_REVIEW', assignment: null });
      await settle();

      // Vuelve a leer el detalle: el estado mostrado es el del servidor.
      http.expectOne(DETAIL_URL).flush(buildSubmissionDetail({ status: 'UNDER_REVIEW' }), {
        headers: { ETag: '"1"' },
      });
      await settle();

      expect(text(element.querySelector('.detail-badges'))).toContain('En revisión');
      expect(text(element)).toContain('El envío pasó a revisión.');
      expect(text(element)).toContain('a la espera de asignar un Revisor');
      expect(button(element, 'Pasar a revisión')).toBeUndefined();
      expect(dialog(element).open).toBe(false);
    });

    it('mientras actúa bloquea el botón y no permite repetir la acción', async () => {
      const { element, settle } = await open();
      button(element, 'Pasar a revisión')!.click();
      await settle();
      dialogButton(element, 'Pasar a revisión').click();
      await settle();

      const busy = button(element, 'Pasando a revisión…');
      expect(busy?.disabled).toBe(true);
      http
        .expectOne(START_URL)
        .flush({ id: 's-1', code: 'GPC-2026-000001', status: 'UNDER_REVIEW', assignment: null });
      http.expectOne(DETAIL_URL).flush(buildSubmissionDetail({ status: 'UNDER_REVIEW' }));
    });

    it('si otro Editor se adelantó (409) lo explica y muestra el estado real', async () => {
      const { element, settle } = await open();
      button(element, 'Pasar a revisión')!.click();
      await settle();
      dialogButton(element, 'Pasar a revisión').click();
      await settle();

      http
        .expectOne(START_URL)
        .flush(errorEnvelope('STATE_CONFLICT', 'Solo un manuscrito enviado puede pasar a revisión.'), {
          status: 409,
          statusText: 'Conflict',
        });
      await settle();
      http.expectOne(DETAIL_URL).flush(buildSubmissionDetail({ status: 'UNDER_REVIEW' }));
      await settle();

      expect(element.querySelector('[role="alert"]')).not.toBeNull();
      expect(text(element.querySelector('.detail-badges'))).toContain('En revisión');
      expect(button(element, 'Pasar a revisión')).toBeUndefined();
    });
  });

  describe('Revisor', () => {
    const REVIEWERS = '/api/editor/reviewers/';
    const ASSIGN_URL = '/api/editor/manuscripts/s-1/assignments/';
    const underReview = (overrides: Partial<SubmissionDetail> = {}) =>
      open({ status: 'UNDER_REVIEW', ...overrides });

    const reviewersRequest = () => http.expectOne((r) => r.url === REVIEWERS);
    const page = (...reviewers: ReturnType<typeof buildReviewer>[]) => ({
      count: reviewers.length,
      next: null,
      previous: null,
      results: reviewers,
    });

    it('solo aparece con el envío en revisión', async () => {
      const submitted = await open();
      expect(submitted.element.querySelector('[aria-labelledby="reviewer-title"]')).toBeNull();
    });

    it('sin asignación invita a asignar y no consulta Revisores hasta que se pide', async () => {
      const { element } = await underReview();

      expect(text(element.querySelector('[aria-labelledby="reviewer-title"]'))).toContain(
        'a la espera de asignar un Revisor',
      );
      expect(button(element, 'Asignar Revisor')).toBeDefined();
      http.expectNone((r) => r.url === REVIEWERS);
    });

    it('con asignación muestra al Revisor y su plazo, y ofrece revocar en lugar de asignar', async () => {
      const { element } = await underReview({ open_assignment: buildAssignment() });

      const section = text(element.querySelector('[aria-labelledby="reviewer-title"]'));
      expect(section).toContain('Marta Ruiz');
      expect(section).toContain('marta@unl.edu.ec');
      expect(section).toContain('Fecha límite: 11/11/2026 10:00');
      expect(button(element, 'Revocar asignación')).toBeDefined();
      expect(button(element, 'Asignar Revisor')).toBeUndefined();
    });

    it('una asignación vencida lo señala y pide revocarla', async () => {
      const { element } = await underReview({
        open_assignment: buildAssignment({ status: 'EXPIRED' }),
      });

      const section = text(element.querySelector('[aria-labelledby="reviewer-title"]'));
      expect(section).toContain('Vencida');
      expect(section).toContain('revoque la asignación para designar a otro Revisor');
    });

    describe('asignar', () => {
      it('abre el selector con los candidatos del manuscrito', async () => {
        const { element, settle } = await underReview();
        button(element, 'Asignar Revisor')!.click();
        await settle();

        const request = reviewersRequest();
        expect(request.request.params.get('manuscript_id')).toBe('s-1');
        request.flush(page(buildReviewer({ full_name: 'Marta Ruiz' })));
        await settle();

        expect(text(element.querySelector('app-reviewer-picker'))).toContain('Marta Ruiz');
        expect(button(element, 'Asignar Revisor')).toBeUndefined();
        expect(button(element, 'Cerrar selector')).toBeDefined();
      });

      it('al confirmar asigna, muestra la fecha límite del servidor y al cerrar refleja el estado', async () => {
        const { element, settle } = await underReview();
        button(element, 'Asignar Revisor')!.click();
        await settle();
        reviewersRequest().flush(page(buildReviewer({ id: 'r-1', full_name: 'Marta Ruiz' })));
        await settle();

        (element.querySelector('app-reviewer-picker .picker__item button') as HTMLButtonElement).click();
        await settle();
        expect(assignDialog(element).open).toBe(true);
        expect(text(assignDialog(element))).toContain('Marta Ruiz');
        http.expectNone(ASSIGN_URL);

        inDialog(assignDialog(element), 'Confirmar asignación')!.click();
        await settle();
        const request = http.expectOne(ASSIGN_URL);
        expect(request.request.method).toBe('POST');
        expect(request.request.body).toEqual({ reviewer_id: 'r-1' });
        request.flush(buildAssignment({ due_at: '2026-11-11T15:00:00Z' }), {
          status: 201,
          statusText: 'Created',
        });
        await settle();

        // La fecha límite mostrada es la que fijó el servidor.
        expect(text(assignDialog(element))).toContain('Fecha límite: 11/11/2026 10:00');

        inDialog(assignDialog(element), 'Entendido')!.click();
        await settle();
        http
          .expectOne(DETAIL_URL)
          .flush(buildSubmissionDetail({ status: 'UNDER_REVIEW', open_assignment: buildAssignment() }));
        await settle();

        expect(assignDialog(element).open).toBe(false);
        expect(text(element)).toContain('Revisor asignado.');
        expect(button(element, 'Revocar asignación')).toBeDefined();
        expect(element.querySelector('app-reviewer-picker')).toBeNull();
      });

      it('si otro Editor asignó antes (409) lo explica y muestra el estado real', async () => {
        const { element, settle } = await underReview();
        button(element, 'Asignar Revisor')!.click();
        await settle();
        reviewersRequest().flush(page(buildReviewer({ id: 'r-2', full_name: 'Luis Vega' })));
        await settle();
        (element.querySelector('app-reviewer-picker .picker__item button') as HTMLButtonElement).click();
        await settle();

        inDialog(assignDialog(element), 'Confirmar asignación')!.click();
        await settle();
        http.expectOne(ASSIGN_URL).flush(
          errorEnvelope('ASSIGNMENT_CONFLICT', 'El manuscrito ya tiene un Revisor activo.'),
          { status: 409, statusText: 'Conflict' },
        );
        await settle();
        http
          .expectOne(DETAIL_URL)
          .flush(buildSubmissionDetail({ status: 'UNDER_REVIEW', open_assignment: buildAssignment() }));
        await settle();

        const dialogText = text(assignDialog(element));
        expect(dialogText).toContain('Ya existe una asignación activa.');
        // Con el estado real a la vista, el diálogo advierte y no deja confirmar.
        expect(dialogText).toContain('ya tiene un Revisor activo (Marta Ruiz)');
        expect(inDialog(assignDialog(element), 'Confirmar asignación')!.disabled).toBe(true);
      });

      it('cancelar no asigna', async () => {
        const { element, settle } = await underReview();
        button(element, 'Asignar Revisor')!.click();
        await settle();
        reviewersRequest().flush(page(buildReviewer()));
        await settle();
        (element.querySelector('app-reviewer-picker .picker__item button') as HTMLButtonElement).click();
        await settle();

        inDialog(assignDialog(element), 'Cancelar')!.click();
        await settle();

        expect(assignDialog(element).open).toBe(false);
        http.expectNone(ASSIGN_URL);
        expect(element.querySelector('app-reviewer-picker')).not.toBeNull();
      });

      it('sin Revisores elegibles explica la causa', async () => {
        const { element, settle } = await underReview();
        button(element, 'Asignar Revisor')!.click();
        await settle();
        reviewersRequest().flush({
          count: 0,
          next: null,
          previous: null,
          results: [],
          diagnosis: { reviewers: 2, conflict: 0, no_profile: 0, unavailable: 0, other_area: 2 },
        });
        await settle();

        expect(text(element.querySelector('app-reviewer-picker'))).toContain(
          '2 no declaran el área «Agronomía».',
        );
      });
    });

    describe('revocar', () => {
      const REVOKE_URL = '/api/editor/assignments/a-1/revoke/';

      it('pide causa y motivo, revoca y refleja el estado', async () => {
        const { element, settle } = await underReview({ open_assignment: buildAssignment() });
        button(element, 'Revocar asignación')!.click();
        await settle();
        expect(revokeDialog(element).open).toBe(true);

        // Sin causa ni motivo no llama a la API.
        inDialog(revokeDialog(element), 'Revocar asignación')!.click();
        await settle();
        http.expectNone(REVOKE_URL);

        (revokeDialog(element).querySelector('input[type="radio"]') as HTMLInputElement).click();
        const area = revokeDialog(element).querySelector('textarea') as HTMLTextAreaElement;
        area.value = 'Es coautor de un trabajo previo.';
        area.dispatchEvent(new Event('input'));
        await settle();
        inDialog(revokeDialog(element), 'Revocar asignación')!.click();
        await settle();

        const request = http.expectOne(REVOKE_URL);
        expect(request.request.body).toEqual({
          cause: 'CONFLICT_OF_INTEREST',
          reason: 'Es coautor de un trabajo previo.',
        });
        request.flush(buildAssignment({ status: 'REVOKED' }));
        await settle();
        http
          .expectOne(DETAIL_URL)
          .flush(buildSubmissionDetail({ status: 'UNDER_REVIEW', open_assignment: null }));
        await settle();

        expect(revokeDialog(element).open).toBe(false);
        expect(text(element)).toContain('Asignación revocada.');
        expect(button(element, 'Asignar Revisor')).toBeDefined();
        expect(button(element, 'Revocar asignación')).toBeUndefined();
      });

      it('un error del servidor se muestra en el diálogo', async () => {
        const { element, settle } = await underReview({ open_assignment: buildAssignment() });
        button(element, 'Revocar asignación')!.click();
        await settle();
        (revokeDialog(element).querySelector('input[type="radio"]') as HTMLInputElement).click();
        const area = revokeDialog(element).querySelector('textarea') as HTMLTextAreaElement;
        area.value = 'Motivo.';
        area.dispatchEvent(new Event('input'));
        await settle();
        inDialog(revokeDialog(element), 'Revocar asignación')!.click();
        await settle();

        http.expectOne(REVOKE_URL).flush(
          errorEnvelope('STATE_CONFLICT', 'Solo una asignación activa o vencida puede revocarse.'),
          { status: 409, statusText: 'Conflict' },
        );
        await settle();
        http.expectOne(DETAIL_URL).flush(buildSubmissionDetail({ status: 'UNDER_REVIEW' }));
        await settle();

        expect(revokeDialog(element).open).toBe(true);
        expect(text(revokeDialog(element))).toContain(
          'La acción no es válida en el estado actual.',
        );
      });
    });
  });

  describe('veredicto', () => {
    const VERDICT_URL = '/api/editor/manuscripts/s-1/verdicts/';
    const verdictSection = (element: HTMLElement) => element.querySelector('app-verdict-form');

    it('no aparece mientras el envío solo está enviado', async () => {
      const { element } = await open();

      expect(verdictSection(element)).toBeNull();
    });

    it.each(['UNDER_REVIEW', 'REQUIRES_CORRECTIONS', 'ACCEPTED', 'REJECTED'] as const)(
      'aparece con el envío en estado %s',
      async (status) => {
        const { element } = await open({ status });

        expect(verdictSection(element)).not.toBeNull();
      },
    );

    it('un envío ya juzgado muestra el veredicto en solo lectura y sin formulario', async () => {
      verdictData = {
        evaluations: [buildEvaluation()],
        verdicts: [buildVerdict({ decision: 'REJECTED', justification: 'Metodología inválida.' })],
      };
      const { element } = await open({ status: 'REJECTED' });

      const section = verdictSection(element) as HTMLElement;
      expect(text(section)).toContain('Rechazado');
      expect(text(section)).toContain('Justificación: Metodología inválida.');
      expect(section.querySelector('form')).toBeNull();
    });

    it('con el envío dado de baja no ofrece registrar', async () => {
      verdictData = { evaluations: [buildEvaluation()], verdicts: [] };
      const { element } = await open({
        status: 'UNDER_REVIEW',
        is_active: false,
        withdrawn_at: '2026-10-22T15:00:00Z',
      });

      expect(verdictSection(element)!.querySelector('form')).toBeNull();
    });

    it('registra el veredicto con el ETag del detalle, informa el efecto y relee el detalle', async () => {
      verdictData = { evaluations: [buildEvaluation()], verdicts: [] };
      const { element, settle } = await open({ status: 'UNDER_REVIEW' }, '"7"');

      (element.querySelector('app-verdict-form .verdict__option input') as HTMLInputElement).click();
      await settle();
      (element.querySelector('app-verdict-form form button[type="submit"]') as HTMLButtonElement).click();
      await settle();
      const confirm = Array.from(
        element.querySelectorAll('app-verdict-form app-confirm-dialog dialog button'),
      ).find((b) => text(b) === 'Registrar veredicto') as HTMLButtonElement;
      confirm.click();
      await settle();

      const request = http.expectOne((r) => r.method === 'POST' && r.url === VERDICT_URL);
      expect(request.request.headers.get('If-Match')).toBe('"7"');
      request.flush(buildVerdictResult(), { status: 201, statusText: 'Created', headers: { ETag: '"8"' } });
      await settle();
      http
        .expectOne(DETAIL_URL)
        .flush(buildSubmissionDetail({ status: 'ACCEPTED' }), { headers: { ETag: '"8"' } });
      await settle();

      expect(text(element)).toContain('Veredicto registrado: el artículo se publicó en el catálogo.');
      expect(text(element.querySelector('.detail-badges'))).toContain('Aceptado');
      expect(verdictSection(element)!.querySelector('form')).toBeNull();
    });

    it('al pedir correcciones informa de la ronda abierta', async () => {
      verdictData = {
        evaluations: [buildEvaluation({ recommendation: 'REQUIRES_CORRECTIONS' })],
        verdicts: [],
      };
      const { element, settle } = await open({ status: 'UNDER_REVIEW' });

      (element.querySelectorAll('app-verdict-form .verdict__option input')[1] as HTMLInputElement).click();
      await settle();
      const area = element.querySelector('textarea[name="observations"]') as HTMLTextAreaElement;
      area.value = 'Ampliar la sección 3.';
      area.dispatchEvent(new Event('input'));
      await settle();
      (element.querySelector('app-verdict-form form button[type="submit"]') as HTMLButtonElement).click();
      await settle();
      (Array.from(element.querySelectorAll('app-verdict-form app-confirm-dialog dialog button')).find(
        (b) => text(b) === 'Registrar veredicto',
      ) as HTMLButtonElement).click();
      await settle();

      http
        .expectOne((r) => r.method === 'POST' && r.url === VERDICT_URL)
        .flush(
          buildVerdictResult({
            verdict: buildVerdict({ decision: 'REQUIRES_CORRECTIONS', observations: 'Ampliar la sección 3.' }),
            opened_round: 1,
            catalog_entry: null,
          }),
          { status: 201, statusText: 'Created' },
        );
      await settle();
      http.expectOne(DETAIL_URL).flush(buildSubmissionDetail({ status: 'REQUIRES_CORRECTIONS' }));
      await settle();

      expect(text(element)).toContain('se abrió la ronda 1');
    });

    it('si otro Editor ya juzgó (409) relee el detalle y muestra el estado real', async () => {
      verdictData = { evaluations: [buildEvaluation()], verdicts: [] };
      const { element, settle } = await open({ status: 'UNDER_REVIEW' });
      (element.querySelector('app-verdict-form .verdict__option input') as HTMLInputElement).click();
      await settle();
      (element.querySelector('app-verdict-form form button[type="submit"]') as HTMLButtonElement).click();
      await settle();
      (Array.from(element.querySelectorAll('app-verdict-form app-confirm-dialog dialog button')).find(
        (b) => text(b) === 'Registrar veredicto',
      ) as HTMLButtonElement).click();
      await settle();

      // Lo que responderán las lecturas que provoca el conflicto: el veredicto que ganó.
      verdictData = {
        evaluations: [buildEvaluation()],
        verdicts: [buildVerdict({ decision: 'REJECTED', justification: 'Otro Editor.' })],
      };
      http
        .expectOne((r) => r.method === 'POST' && r.url === VERDICT_URL)
        .flush(errorEnvelope('VERDICT_CONFLICT', 'Ya existe un veredicto.'), {
          status: 409,
          statusText: 'Conflict',
        });
      await settle();
      // El detalle y los datos del formulario se releen.
      http.expectOne(DETAIL_URL).flush(buildSubmissionDetail({ status: 'REJECTED' }));
      await settle();

      expect(text(element.querySelector('.detail-badges'))).toContain('Rechazado');
      expect(text(verdictSection(element))).toContain('Otro Editor.');
      expect(verdictSection(element)!.querySelector('form')).toBeNull();
    });
  });

  describe('descarga del PDF', () => {
    let clicked: HTMLAnchorElement[];
    let click: ReturnType<typeof vi.spyOn>;

    beforeEach(() => {
      clicked = [];
      Object.assign(URL, { createObjectURL: vi.fn(() => 'blob:gpc-test'), revokeObjectURL: vi.fn() });
      click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (
        this: HTMLAnchorElement,
      ) {
        clicked.push(this);
      });
    });

    afterEach(() => click.mockRestore());

    it('pide el archivo como Blob al endpoint autorizado y lo entrega con el nombre del servidor', async () => {
      const { element, settle } = await open();

      button(element, 'Descargar PDF')!.click();
      await settle();
      const request = http.expectOne('/api/manuscripts/s-1/versions/v-1/file/');
      expect(request.request.responseType).toBe('blob');
      request.flush(new Blob(['%PDF-1.7'], { type: 'application/pdf' }), {
        headers: { 'Content-Disposition': 'attachment; filename="GPC-2026-000001-v1.pdf"' },
      });
      await settle();

      expect(clicked[0].download).toBe('GPC-2026-000001-v1.pdf');
    });

    it('si falla lo explica y deja volver a intentar', async () => {
      const { element, settle } = await open();

      button(element, 'Descargar PDF')!.click();
      await settle();
      http
        .expectOne('/api/manuscripts/s-1/versions/v-1/file/')
        .flush(new Blob([JSON.stringify(errorEnvelope('AUDIT_UNAVAILABLE', 'Auditoría no disponible.'))]), {
          status: 503,
          statusText: 'Service Unavailable',
        });
      await new Promise((resolve) => setTimeout(resolve));
      await settle();

      expect(element.querySelector('[role="alert"]')).not.toBeNull();
      expect(clicked.length).toBe(0);
      expect(button(element, 'Descargar PDF')!.disabled).toBe(false);
    });
  });
});
