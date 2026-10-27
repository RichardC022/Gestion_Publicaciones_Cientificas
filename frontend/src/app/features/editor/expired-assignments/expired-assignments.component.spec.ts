import { Component } from '@angular/core';
import { provideHttpClient } from '@angular/common/http';
import {
  HttpTestingController,
  TestRequest,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { Router, convertToParamMap, provideRouter } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';

import { API_BASE_URL } from '../../../core/http/api-base-url.token';
import { Assignment } from '../../../core/models/editor.model';
import { errorEnvelope } from '../../author/testing/manuscript.fixtures';
import { buildAssignment } from '../testing/editor.fixtures';
import {
  ExpiredAssignmentsComponent,
  PAGE_SIZE,
  toPage,
} from './expired-assignments.component';

@Component({ template: '' })
class BlankComponent {}

const EXPIRED = '/api/editor/assignments/expired/';
const PAGE_URL = '/app/editor/assignments/expired';
const page = (results: Assignment[], count = results.length) => ({
  count,
  next: null,
  previous: null,
  results,
});

describe('ExpiredAssignmentsComponent', () => {
  let http: HttpTestingController;
  let router: Router;

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
          { path: 'app/editor/assignments/expired', component: ExpiredAssignmentsComponent },
          { path: 'app/editor/submissions/:id', component: BlankComponent },
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
    http.expectOne((r) => r.method === 'GET' && r.url === EXPIRED);

  const open = async (url = PAGE_URL) => {
    const harness = await RouterTestingHarness.create();
    await harness.navigateByUrl(url, ExpiredAssignmentsComponent);
    const element = harness.routeNativeElement as HTMLElement;
    const settle = async () => {
      await harness.fixture.whenStable();
      harness.detectChanges();
    };
    return { harness, element, settle };
  };

  const rowsOf = (element: HTMLElement) => Array.from(element.querySelectorAll('tbody tr'));
  const dialog = (element: HTMLElement) => element.querySelector('dialog') as HTMLDialogElement;
  const revokeButtons = (element: HTMLElement) =>
    Array.from(element.querySelectorAll<HTMLButtonElement>('tbody button'));

  describe('lista', () => {
    it('muestra envío, título, Revisor, fecha límite y estado', async () => {
      const { element, settle } = await open();
      listRequest().flush(
        page([
          buildAssignment({
            status: 'EXPIRED',
            manuscript: 's-7',
            manuscript_code: 'GPC-2026-000007',
            manuscript_title: 'Suelos del páramo',
            due_at: '2026-11-11T15:00:00Z',
            reviewer: { id: 'r-1', full_name: 'Marta Ruiz', email: 'marta@unl.edu.ec' },
          }),
        ]),
      );
      await settle();

      const cells = Array.from(rowsOf(element)[0].querySelectorAll('td')).map((c) => text(c));
      expect(cells[0]).toBe('GPC-2026-000007');
      expect(cells[1]).toBe('Suelos del páramo');
      expect(cells[2]).toBe('Marta Ruiz marta@unl.edu.ec');
      // 15:00 UTC en la zona institucional (UTC-5) son las 10:00.
      expect(cells[3]).toBe('11/11/2026 10:00');
      expect(cells[4]).toBe('Vencida');
      expect(cells[5]).toContain('Ver envío');
      expect(text(element.querySelector('.list-header__count'))).toBe('1 pendiente de decisión');
    });

    it('una asignación activa ya pasada de fecha se indica como por marcar', async () => {
      const { element, settle } = await open();
      listRequest().flush(page([buildAssignment({ status: 'ACTIVE', is_overdue: true })]));
      await settle();

      const status = rowsOf(element)[0].querySelectorAll('td')[4];
      expect(text(status.querySelector('app-status-badge'))).toBe('Vencida');
      expect(text(status.querySelector('.expired__meta'))).toBe('por marcar');
    });

    it('el código y «Ver envío» llevan al detalle del envío', async () => {
      const { element, settle } = await open();
      listRequest().flush(page([buildAssignment({ manuscript: 's-9' })]));
      await settle();

      const links = Array.from(rowsOf(element)[0].querySelectorAll('a'));
      expect(links.map((a) => a.getAttribute('href'))).toEqual([
        '/app/editor/submissions/s-9',
        '/app/editor/submissions/s-9',
      ]);
    });

    it('aclara que nada se revoca ni se reasigna solo', async () => {
      const { element, settle } = await open();
      listRequest().flush(page([buildAssignment({ status: 'EXPIRED' })]));
      await settle();

      expect(text(element.querySelector('.note'))).toContain(
        'Ninguna se revoca ni se reasigna sola',
      );
    });

    it('no ofrece asignar ni acciones de Administrador', async () => {
      const { element, settle } = await open();
      listRequest().flush(page([buildAssignment({ status: 'EXPIRED' })]));
      await settle();

      const content = text(element).toLowerCase();
      expect(content).not.toContain('asignar a');
      expect(content).not.toContain('auditor');
      expect(element.querySelector('a[href*="/admin"]')).toBeNull();
    });

    it('al cargar solo consulta: no revoca ni reasigna por su cuenta', async () => {
      const { settle } = await open();
      listRequest().flush(page([buildAssignment({ status: 'EXPIRED' })]));
      await settle();

      http.expectNone((r) => r.method !== 'GET');
    });
  });

  describe('estados', () => {
    it('muestra el indicador de carga hasta que llega la respuesta', async () => {
      const { element, settle } = await open();
      expect(element.querySelector('app-loading-spinner')).not.toBeNull();

      listRequest().flush(page([]));
      await settle();

      expect(element.querySelector('app-loading-spinner')).toBeNull();
    });

    it('sin vencidas lo dice', async () => {
      const { element, settle } = await open();
      listRequest().flush(page([]));
      await settle();

      expect(text(element)).toContain('No hay asignaciones vencidas pendientes de decisión.');
      expect(element.querySelector('table')).toBeNull();
    });

    it('un error del servidor se explica y permite reintentar', async () => {
      const { element, settle } = await open();
      listRequest().flush(errorEnvelope('SERVER_ERROR', 'Error.'), {
        status: 500,
        statusText: 'Server Error',
      });
      await settle();
      expect(element.querySelector('app-error-state')).not.toBeNull();

      (element.querySelector('app-error-state button') as HTMLButtonElement).click();
      await settle();
      listRequest().flush(page([buildAssignment({ status: 'EXPIRED' })]));
      await settle();

      expect(element.querySelector('app-error-state')).toBeNull();
      expect(rowsOf(element).length).toBe(1);
    });
  });

  describe('paginación', () => {
    it('sin parámetro pide la primera página', async () => {
      await open();

      const request = listRequest();
      expect(request.request.params.get('page_size')).toBe(String(PAGE_SIZE));
      expect(request.request.params.has('page')).toBe(false);
      request.flush(page([]));
    });

    it('la página de la URL se envía a la API', async () => {
      await open(`${PAGE_URL}?page=3`);

      const request = listRequest();
      expect(request.request.params.get('page')).toBe('3');
      request.flush(page([]));
    });

    it('Siguiente avanza la página en la URL y en la consulta', async () => {
      const { element, settle } = await open();
      listRequest().flush(page([buildAssignment({ status: 'EXPIRED' })], 45));
      await settle();

      (Array.from(element.querySelectorAll('app-pagination button')).find(
        (b) => text(b) === 'Siguiente',
      ) as HTMLButtonElement).click();
      await settle();

      expect(router.url).toBe(`${PAGE_URL}?page=2`);
      const request = listRequest();
      expect(request.request.params.get('page')).toBe('2');
      request.flush(page([buildAssignment({ status: 'EXPIRED' })], 45));
    });
  });

  describe('revocar', () => {
    const REVOKE = '/api/editor/assignments/a-1/revoke/';

    const openRevoke = async (overrides: Partial<Assignment> = {}) => {
      const view = await open();
      listRequest().flush(
        page([
          buildAssignment({
            id: 'a-1',
            status: 'EXPIRED',
            manuscript: 's-1',
            manuscript_code: 'GPC-2026-000001',
            ...overrides,
          }),
        ]),
      );
      await view.settle();
      revokeButtons(view.element)[0].click();
      await view.settle();
      return view;
    };

    const fillAndConfirm = async (
      element: HTMLElement,
      settle: () => Promise<void>,
      reason = 'No respondió en el plazo.',
    ) => {
      const area = dialog(element).querySelector('textarea') as HTMLTextAreaElement;
      area.value = reason;
      area.dispatchEvent(new Event('input'));
      await settle();
      (dialog(element).querySelector('button.btn--danger') as HTMLButtonElement).click();
      await settle();
    };

    it('abre el diálogo con el Revisor y la causa «Plazo vencido» sugerida', async () => {
      const { element } = await openRevoke();

      expect(dialog(element).open).toBe(true);
      expect(text(dialog(element))).toContain('Marta Ruiz');
      expect(text(dialog(element))).toContain('Vencida');
      expect(
        (dialog(element).querySelector('input[type="radio"]:checked') as HTMLInputElement | null)
          ?.value,
      ).toBe('OVERDUE');
    });

    it('cancelar no revoca nada', async () => {
      const { element, settle } = await openRevoke();

      (Array.from(dialog(element).querySelectorAll('button')).find(
        (b) => text(b) === 'Cancelar',
      ) as HTMLButtonElement).click();
      await settle();

      expect(dialog(element).open).toBe(false);
      http.expectNone((r) => r.method === 'POST');
    });

    it('sin motivo no llama a la API', async () => {
      const { element, settle } = await openRevoke();

      (dialog(element).querySelector('button.btn--danger') as HTMLButtonElement).click();
      await settle();

      http.expectNone((r) => r.method === 'POST');
      expect(text(dialog(element))).toContain('Indique el motivo de la revocación.');
    });

    it('revoca con causa y motivo, ofrece reasignar a mano y vuelve a leer la lista', async () => {
      const { element, settle } = await openRevoke();
      await fillAndConfirm(element, settle);

      const request = http.expectOne(REVOKE);
      expect(request.request.body).toEqual({
        cause: 'OVERDUE',
        reason: 'No respondió en el plazo.',
      });
      request.flush(buildAssignment({ id: 'a-1', status: 'REVOKED' }));
      await settle();
      // La lista se relee: la asignación revocada ya no está vencida.
      listRequest().flush(page([]));
      await settle();

      expect(dialog(element).open).toBe(false);
      expect(rowsOf(element).length).toBe(0);
      const notice = element.querySelector('.callout--success') as HTMLElement;
      expect(text(notice)).toContain('Asignación revocada.');
      const link = notice.querySelector('a') as HTMLAnchorElement;
      expect(text(link)).toBe('Abrir GPC-2026-000001 para asignar a otro Revisor');
      expect(link.getAttribute('href')).toBe('/app/editor/submissions/s-1');
      // Revocar no asigna a nadie: la reasignación es manual.
      http.expectNone((r) => r.method === 'POST');
    });

    it('si el servidor rechaza la revocación lo muestra y relee la lista', async () => {
      const { element, settle } = await openRevoke();
      await fillAndConfirm(element, settle);

      http.expectOne(REVOKE).flush(errorEnvelope('STATE_CONFLICT', 'Ya no es revocable.'), {
        status: 409,
        statusText: 'Conflict',
      });
      await settle();
      listRequest().flush(page([]));
      await settle();

      expect(dialog(element).open).toBe(true);
      expect(text(dialog(element))).toContain('La acción no es válida en el estado actual.');
    });

    it('una asignación activa vencida acepta la causa «Plazo vencido»', async () => {
      const { element } = await openRevoke({ status: 'ACTIVE', is_overdue: true });

      expect(text(dialog(element))).toContain('Plazo vencido');
    });
  });
});

describe('toPage', () => {
  it.each([
    [{ page: '3' }, 3],
    [{ page: '1' }, 1],
    [{ page: '0' }, 1],
    [{ page: '-4' }, 1],
    [{ page: 'abc' }, 1],
    [{}, 1],
  ])('%j → %i', (query, expected) => {
    expect(toPage(convertToParamMap(query))).toBe(expected);
  });
});
