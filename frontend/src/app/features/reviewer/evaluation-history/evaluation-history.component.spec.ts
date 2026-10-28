import { provideHttpClient } from '@angular/common/http';
import {
  HttpTestingController,
  TestRequest,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';

import { API_BASE_URL } from '../../../core/http/api-base-url.token';
import { ReviewerHistoryRow } from '../../../core/models/reviewer.model';
import { errorEnvelope } from '../../author/testing/manuscript.fixtures';
import {
  buildHistoryDetail,
  buildHistoryPage,
  buildHistoryRow,
} from '../testing/reviewer.fixtures';
import { EvaluationHistoryComponent, PAGE_SIZE } from './evaluation-history.component';

const LIST = '/api/reviewer/evaluations/';
const PAGE_URL = '/app/reviewer/history';

describe('EvaluationHistoryComponent', () => {
  let http: HttpTestingController;
  let router: Router;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideRouter([{ path: 'app/reviewer/history', component: EvaluationHistoryComponent }]),
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: API_BASE_URL, useValue: '/api/' },
      ],
    });
    http = TestBed.inject(HttpTestingController);
    router = TestBed.inject(Router);
  });

  afterEach(() => http.verify());

  const text = (node: Element | null) => (node?.textContent ?? '').replace(/\s+/g, ' ').trim();
  const listRequest = (): TestRequest =>
    http.expectOne((r) => r.method === 'GET' && r.url === LIST);

  const open = async (url = PAGE_URL) => {
    const harness = await RouterTestingHarness.create();
    await harness.navigateByUrl(url, EvaluationHistoryComponent);
    const element = harness.routeNativeElement as HTMLElement;
    const settle = async () => {
      await harness.fixture.whenStable();
      harness.detectChanges();
    };
    return { harness, element, settle };
  };

  const render = async (rows: ReviewerHistoryRow[], count = rows.length) => {
    const view = await open();
    listRequest().flush(buildHistoryPage(rows, count));
    await view.settle();
    return view;
  };

  const rowsOf = (element: HTMLElement) =>
    Array.from(element.querySelectorAll('tbody tr:not(.history__detail)'));
  const toggle = (element: HTMLElement, index = 0) =>
    rowsOf(element)[index].querySelector<HTMLButtonElement>('button')!;

  it('muestra un estado de carga mientras espera el historial', async () => {
    const { element } = await open();

    expect(element.querySelector('app-loading-spinner')).not.toBeNull();
    listRequest().flush(buildHistoryPage([]));
  });

  describe('lista', () => {
    it('muestra manuscrito, versión, recomendación, fecha y resultado editorial', async () => {
      const { element } = await render([
        buildHistoryRow({
          manuscript_code: 'GPC-2026-000007',
          manuscript_title: 'Suelos del páramo',
          area: 'Edafología',
          version_number: 2,
          round_number: 1,
          recommendation: 'ACCEPT',
          submitted_at: '2026-10-25T20:00:00Z',
          editorial_result: { decision: 'ACCEPTED', decided_at: '2026-10-26T15:00:00Z' },
        }),
      ]);

      const cells = Array.from(rowsOf(element)[0].querySelectorAll('td')).map((c) => text(c));
      expect(cells.slice(0, 6)).toEqual([
        'GPC-2026-000007',
        'Suelos del páramo',
        'Edafología',
        'v2 Ronda 1',
        'Aceptar',
        '25/10/2026 15:00',
      ]);
      const result = rowsOf(element)[0].querySelectorAll('td')[6];
      expect(text(result.querySelector('.badge'))).toBe('Aceptado');
      expect(text(result.querySelector('.history__meta'))).toBe('26/10/2026');
    });

    it('sin decisión del Editor lo dice', async () => {
      const { element } = await render([buildHistoryRow()]);

      expect(text(rowsOf(element)[0].querySelectorAll('td')[6])).toBe('Pendiente de decisión');
    });

    it('traduce cada decisión editorial', async () => {
      const decided = (decision: 'ACCEPTED' | 'REJECTED' | 'REQUIRES_CORRECTIONS', id: string) =>
        buildHistoryRow({ id, editorial_result: { decision, decided_at: '2026-10-26T15:00:00Z' } });
      const { element } = await render([
        decided('ACCEPTED', 'e-1'),
        decided('REJECTED', 'e-2'),
        decided('REQUIRES_CORRECTIONS', 'e-3'),
      ]);

      const badges = rowsOf(element).map((row) => text(row.querySelector('.badge')));
      expect(badges).toEqual(['Aceptado', 'Rechazado', 'Requiere correcciones']);
    });

    it('es de solo lectura: no ofrece editar, reenviar ni borrar', async () => {
      const { element } = await render([buildHistoryRow()]);

      const actions = Array.from(element.querySelectorAll('button, a')).map((e) => text(e));
      expect(actions.join(' | ')).not.toMatch(/editar|reenviar|enviar|borrar|eliminar|guardar/i);
      expect(element.querySelector('form, input, textarea')).toBeNull();
    });

    it('no pinta datos de autoría ni el texto del Editor aunque la respuesta los trajera', async () => {
      const leaky = {
        ...buildHistoryRow(),
        authors: [{ full_name: 'Ana López Reservada', email: 'ana@unl.edu.ec' }],
        created_by: 'ana@unl.edu.ec',
        editorial_result: {
          decision: 'REJECTED',
          decided_at: '2026-10-26T15:00:00Z',
          justification: 'Justificación interna del Editor.',
          observations: 'Observaciones para el Autor.',
        },
      } as unknown as ReviewerHistoryRow;

      const { element } = await render([leaky]);

      const html = element.innerHTML;
      expect(html).not.toContain('Ana López Reservada');
      expect(html).not.toContain('ana@unl.edu.ec');
      expect(html).not.toContain('Justificación interna');
      expect(html).not.toContain('Observaciones para el Autor');
    });

    it('cuenta las evaluaciones', async () => {
      const { element } = await render([buildHistoryRow()], 1);

      expect(text(element.querySelector('.list-header__count'))).toBe('1 evaluación enviada');
    });
  });

  describe('detalle', () => {
    it('al abrir una fila pide la evaluación y muestra puntajes y comentarios para el Autor', async () => {
      const { element, settle } = await render([buildHistoryRow()]);

      toggle(element).click();
      await settle();
      expect(element.querySelector('.history__detail app-loading-spinner')).not.toBeNull();
      http.expectOne('/api/reviewer/evaluations/ev-1/').flush(buildHistoryDetail());
      await settle();

      const detail = element.querySelector('.history__detail')!;
      const scores = Array.from(detail.querySelectorAll('.scores__row')).map(
        (row) => `${text(row.querySelector('dt'))}: ${text(row.querySelector('dd'))}`,
      );
      expect(scores).toEqual([
        'Originalidad: 4 / 5',
        'Metodología: 3 / 5',
        'Claridad: 5 / 5',
        'Relevancia: 4 / 5',
        'Ética: 5 / 5',
      ]);
      expect(text(detail)).toContain('Aclarar la metodología.');
      expect(toggle(element).getAttribute('aria-expanded')).toBe('true');
    });

    it('nunca muestra comentarios confidenciales aunque la respuesta los trajera', async () => {
      const { element, settle } = await render([buildHistoryRow()]);

      toggle(element).click();
      await settle();
      http.expectOne('/api/reviewer/evaluations/ev-1/').flush({
        ...buildHistoryDetail(),
        confidential_comments: 'Comentario solo para el Editor.',
      });
      await settle();

      expect(element.innerHTML).not.toContain('Comentario solo para el Editor.');
      expect(text(element.querySelector('.history__detail'))).not.toMatch(/confidencial/i);
    });

    it('se cierra y se vuelve a abrir sin pedirlo otra vez', async () => {
      const { element, settle } = await render([buildHistoryRow()]);
      toggle(element).click();
      await settle();
      http.expectOne('/api/reviewer/evaluations/ev-1/').flush(buildHistoryDetail());
      await settle();

      toggle(element).click();
      await settle();
      expect(element.querySelector('.history__detail')).toBeNull();
      toggle(element).click();
      await settle();

      http.expectNone('/api/reviewer/evaluations/ev-1/');
      expect(text(element.querySelector('.history__detail'))).toContain('Aclarar la metodología.');
    });

    it('si falla explica el error y permite reintentar', async () => {
      const { element, settle } = await render([buildHistoryRow()]);
      toggle(element).click();
      await settle();

      http.expectOne('/api/reviewer/evaluations/ev-1/').flush(errorEnvelope('SERVER_ERROR', 'x'), {
        status: 500,
        statusText: 'Server Error',
      });
      await settle();
      expect(element.querySelector('.history__detail [role="alert"]')).not.toBeNull();

      element.querySelector<HTMLButtonElement>('.history__detail .btn')!.click();
      await settle();
      http.expectOne('/api/reviewer/evaluations/ev-1/').flush(buildHistoryDetail());
      await settle();

      expect(text(element.querySelector('.history__detail'))).toContain('Aclarar la metodología.');
    });
  });

  describe('estados', () => {
    it('sin evaluaciones muestra el estado vacío', async () => {
      const { element } = await render([]);

      expect(text(element.querySelector('app-empty-state'))).toContain('Todavía no ha enviado');
      expect(element.querySelector('table')).toBeNull();
    });

    it('si falla explica el error y permite reintentar', async () => {
      const { element, settle } = await open();
      listRequest().flush(errorEnvelope('SERVER_ERROR', 'Error.'), {
        status: 500,
        statusText: 'Server Error',
      });
      await settle();
      expect(element.querySelector('[role="alert"]')).not.toBeNull();

      element.querySelector<HTMLButtonElement>('app-error-state button')!.click();
      await settle();
      listRequest().flush(buildHistoryPage([buildHistoryRow()]));
      await settle();

      expect(rowsOf(element).length).toBe(1);
    });
  });

  describe('paginación', () => {
    it('lee la página de la URL y la pide con el tamaño de página', async () => {
      const { harness } = await open(`${PAGE_URL}?page=2`);

      const request = listRequest();
      expect(request.request.params.get('page')).toBe('2');
      expect(request.request.params.get('page_size')).toBe(String(PAGE_SIZE));
      request.flush(buildHistoryPage([buildHistoryRow()], 25));
      await harness.fixture.whenStable();
    });

    it.each(['0', '-3', 'abc'])('ignora el valor manipulado page=%s', async (value) => {
      const { harness } = await open(`${PAGE_URL}?page=${value}`);

      const request = listRequest();
      expect(request.request.params.has('page')).toBe(false);
      request.flush(buildHistoryPage([]));
      await harness.fixture.whenStable();
    });

    it('al cambiar de página actualiza la URL', async () => {
      const { element, settle } = await open();
      listRequest().flush(buildHistoryPage([buildHistoryRow()], PAGE_SIZE + 5));
      await settle();

      Array.from(element.querySelectorAll<HTMLButtonElement>('app-pagination button'))
        .find((b) => text(b) === 'Siguiente')!
        .click();
      await settle();

      expect(router.url).toBe(`${PAGE_URL}?page=2`);
      expect(listRequest().request.params.get('page')).toBe('2');
    });
  });
});
