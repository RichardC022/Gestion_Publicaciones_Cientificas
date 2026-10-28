import { provideHttpClient } from '@angular/common/http';
import {
  HttpTestingController,
  TestRequest,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';

import { API_BASE_URL } from '../../../core/http/api-base-url.token';
import { ReviewerAssignmentRow } from '../../../core/models/reviewer.model';
import { errorEnvelope } from '../../author/testing/manuscript.fixtures';
import { buildAssignmentPage, buildAssignmentRow } from '../testing/reviewer.fixtures';
import { AssignmentListComponent, PAGE_SIZE } from './assignment-list.component';

@Component({ template: '' })
class BlankComponent {}

const LIST = '/api/reviewer/assignments/';
const PAGE_URL = '/app/reviewer/assignments';

describe('AssignmentListComponent', () => {
  let http: HttpTestingController;
  let router: Router;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideRouter([
          { path: 'app/reviewer/assignments', component: AssignmentListComponent },
          { path: 'app/reviewer/assignments/:id', component: BlankComponent },
        ]),
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
    await harness.navigateByUrl(url, AssignmentListComponent);
    const element = harness.routeNativeElement as HTMLElement;
    const settle = async () => {
      await harness.fixture.whenStable();
      harness.detectChanges();
    };
    return { harness, element, settle };
  };

  const rowsOf = (element: HTMLElement) => Array.from(element.querySelectorAll('tbody tr'));

  const render = async (rows: ReviewerAssignmentRow[], count = rows.length) => {
    const view = await open();
    listRequest().flush(buildAssignmentPage(rows, count));
    await view.settle();
    return view;
  };

  it('muestra un estado de carga mientras espera la bandeja', async () => {
    const { element } = await open();

    expect(element.querySelector('app-loading-spinner')).not.toBeNull();
    listRequest().flush(buildAssignmentPage([]));
  });

  describe('lista', () => {
    it('muestra código, título, área, versión, ronda, fecha límite y estado', async () => {
      const { element } = await render([
        buildAssignmentRow({
          manuscript_code: 'GPC-2026-000007',
          manuscript_title: 'Suelos del páramo',
          area: 'Edafología',
          version_number: 2,
          round_number: 1,
          due_at: '2026-11-11T15:00:00Z',
          state: 'ON_TIME',
        }),
      ]);

      const cells = Array.from(rowsOf(element)[0].querySelectorAll('td')).map((c) => text(c));
      expect(cells[0]).toBe('GPC-2026-000007');
      expect(cells[1]).toBe('Suelos del páramo');
      expect(cells[2]).toBe('Edafología');
      expect(cells[3]).toBe('v2 Ronda 1');
      expect(cells[4]).toBe('11/11/2026 10:00');
      expect(cells[5]).toBe('En plazo');
    });

    it('traduce cada estado de la bandeja', async () => {
      const { element } = await render([
        buildAssignmentRow({ id: 'a-1', state: 'PENDING' }),
        buildAssignmentRow({ id: 'a-2', state: 'ON_TIME' }),
        buildAssignmentRow({ id: 'a-3', state: 'OVERDUE', status: 'EXPIRED' }),
        buildAssignmentRow({ id: 'a-4', state: 'EVALUATED', status: 'COMPLETED' }),
        buildAssignmentRow({ id: 'a-5', state: 'REVOKED', status: 'REVOKED' }),
      ]);

      const states = rowsOf(element).map((row) => text(row.querySelector('.badge')));
      expect(states).toEqual(['Pendiente', 'En plazo', 'Vencida', 'Evaluada', 'Revocada']);
    });

    it('enlaza al detalle solo las asignaciones activas o completadas', async () => {
      const { element } = await render([
        buildAssignmentRow({ id: 'a-1', status: 'ACTIVE' }),
        buildAssignmentRow({ id: 'a-2', status: 'COMPLETED', state: 'EVALUATED' }),
        buildAssignmentRow({ id: 'a-3', status: 'REVOKED', state: 'REVOKED' }),
        buildAssignmentRow({ id: 'a-4', status: 'EXPIRED', state: 'OVERDUE' }),
      ]);

      const hrefs = rowsOf(element).map((row) => row.querySelector('a')?.getAttribute('href'));
      expect(hrefs).toEqual([
        '/app/reviewer/assignments/a-1',
        '/app/reviewer/assignments/a-2',
        undefined,
        undefined,
      ]);
    });

    it('no pinta ningún dato de autoría aunque la respuesta lo trajera por error', async () => {
      const leaky = {
        ...buildAssignmentRow(),
        authors: [{ full_name: 'Ana López Reservada', email: 'ana@unl.edu.ec' }],
        created_by: 'Ana López Reservada',
        original_filename: 'ana-lopez-articulo.pdf',
      } as ReviewerAssignmentRow;

      const { element } = await render([leaky]);

      const html = element.innerHTML;
      expect(html).not.toContain('Ana López Reservada');
      expect(html).not.toContain('ana@unl.edu.ec');
      expect(html).not.toContain('ana-lopez-articulo');
      expect(element.querySelector('th')).not.toBeNull();
      const headers = Array.from(element.querySelectorAll('th')).map((h) => text(h));
      expect(headers.join(' ')).not.toMatch(/autor|filiaci|correo|archivo/i);
    });

    it('cuenta las asignaciones', async () => {
      const { element } = await render([buildAssignmentRow()], 1);

      expect(text(element.querySelector('.list-header__count'))).toBe('1 asignación');
    });
  });

  describe('estados', () => {
    it('sin asignaciones muestra el estado vacío', async () => {
      const { element } = await render([]);

      expect(text(element.querySelector('app-empty-state'))).toContain('No tiene asignaciones');
      expect(element.querySelector('table')).toBeNull();
    });

    it('si falla explica el error y permite reintentar', async () => {
      const { element, settle } = await open();
      listRequest().flush(errorEnvelope('INTERNAL_ERROR', 'Error interno.'), {
        status: 500,
        statusText: 'Server Error',
      });
      await settle();

      expect(element.querySelector('[role="alert"]')).not.toBeNull();
      element.querySelector<HTMLButtonElement>('app-error-state button')!.click();
      await settle();
      listRequest().flush(buildAssignmentPage([buildAssignmentRow()]));
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
      request.flush(buildAssignmentPage([buildAssignmentRow()], 25));
      await harness.fixture.whenStable();
    });

    it.each(['0', '-3', 'abc', '1.5x'])('ignora el valor manipulado page=%s', async (value) => {
      const { harness } = await open(`${PAGE_URL}?page=${value}`);

      const request = listRequest();
      expect(request.request.params.has('page')).toBe(false);
      request.flush(buildAssignmentPage([]));
      await harness.fixture.whenStable();
    });

    it('al cambiar de página actualiza la URL', async () => {
      const { element, settle } = await open();
      listRequest().flush(buildAssignmentPage([buildAssignmentRow()], PAGE_SIZE + 5));
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
