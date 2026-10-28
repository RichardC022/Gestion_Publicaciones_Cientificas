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
import { Incident } from '../../../core/models/editor.model';
import { errorEnvelope } from '../../author/testing/manuscript.fixtures';
import { buildIncident, buildIncidentPage } from '../testing/editor.fixtures';
import { IncidentListComponent, PAGE_SIZE, toFilter } from './incident-list.component';

@Component({ template: '' })
class BlankComponent {}

const LIST = '/api/editor/incidents/';
const PAGE_URL = '/app/editor/incidents';

describe('IncidentListComponent', () => {
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
          { path: 'app/editor/incidents', component: IncidentListComponent },
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
    http.expectOne((r) => r.method === 'GET' && r.url === LIST);

  const open = async (url = PAGE_URL) => {
    const harness = await RouterTestingHarness.create();
    await harness.navigateByUrl(url, IncidentListComponent);
    const element = harness.routeNativeElement as HTMLElement;
    const settle = async () => {
      await harness.fixture.whenStable();
      harness.detectChanges();
    };
    return { harness, element, settle };
  };

  const render = async (incidents: Incident[], count = incidents.length, url = PAGE_URL) => {
    const view = await open(url);
    listRequest().flush(buildIncidentPage(incidents, count));
    await view.settle();
    return view;
  };

  const cards = (element: HTMLElement) => Array.from(element.querySelectorAll('.incident'));
  const actionButton = (card: Element, label: string) =>
    Array.from(card.querySelectorAll<HTMLButtonElement>('.incident__actions button')).find(
      (b) => text(b) === label,
    )!;
  const dialog = (element: HTMLElement) =>
    element.querySelector('app-confirm-dialog dialog') as HTMLDialogElement;
  const confirmButton = (element: HTMLElement, label: string) =>
    Array.from(dialog(element).querySelectorAll<HTMLButtonElement>('button')).find(
      (b) => text(b) === label,
    )!;
  const resolveRequest = (id = 'i-1') => http.expectOne(`/api/editor/incidents/${id}/resolve/`);

  it('muestra un estado de carga mientras espera la lista', async () => {
    const { element } = await open();

    expect(element.querySelector('app-loading-spinner')).not.toBeNull();
    listRequest().flush(buildIncidentPage([]));
  });

  describe('lista', () => {
    it('pide los abiertos por defecto', async () => {
      const { harness } = await open();

      const request = listRequest();
      expect(request.request.params.get('status')).toBe('OPEN');
      expect(request.request.params.get('page_size')).toBe(String(PAGE_SIZE));
      request.flush(buildIncidentPage([]));
      await harness.fixture.whenStable();
    });

    it('muestra el reporte confidencial con la descripción y quién lo envió', async () => {
      const { element } = await render([
        buildIncident({
          manuscript_code: 'GPC-2026-000007',
          manuscript_title: 'Suelos del páramo',
          description: 'El PDF trae un nombre en la cabecera.',
        }),
      ]);

      const card = cards(element)[0];
      expect(text(card.querySelector('h2'))).toBe('GPC-2026-000007: Suelos del páramo');
      expect(text(card.querySelector('.incident__description'))).toBe(
        'El PDF trae un nombre en la cabecera.',
      );
      expect(text(card.querySelector('.incident__meta'))).toBe(
        'Reportó Marta Ruiz (marta@unl.edu.ec) el 25/10/2026 15:00.',
      );
      expect(text(card.querySelector('.incident__badges'))).toContain('Posible fuga de identidad');
      expect(text(card.querySelector('.incident__badges'))).toContain('Abierto');
      expect(card.querySelector('h2 a')!.getAttribute('href')).toBe('/app/editor/submissions/s-1');
    });

    it('declara que es confidencial para el Autor', async () => {
      const { element } = await render([buildIncident()]);

      expect(text(element.querySelector('.note'))).toContain('el Autor no recibe el reporte');
    });

    it('un reporte abierto ofrece las tres resoluciones', async () => {
      const { element } = await render([buildIncident()]);

      const labels = Array.from(
        cards(element)[0].querySelectorAll('.incident__actions button'),
      ).map((b) => text(b));
      expect(labels).toEqual([
        'Solicitar versión anonimizada',
        'Reasignar Revisor',
        'Descartar reporte',
      ]);
    });

    it('un reporte resuelto muestra el resultado y no ofrece acciones', async () => {
      const { element } = await render([
        buildIncident({
          status: 'RESOLVED',
          resolution: 'REQUEST_ANONYMIZED_VERSION',
          resolved_by: { id: 'e-1', full_name: 'Edgar Mora', email: 'edgar@unl.edu.ec' },
          resolved_at: '2026-10-26T15:00:00Z',
          correction_round_number: 1,
        }),
      ]);

      const card = cards(element)[0];
      expect(text(card.querySelector('.incident__resolution'))).toBe(
        'Versión anonimizada solicitada por Edgar Mora el 26/10/2026 10:00 · se abrió la ronda 1',
      );
      expect(card.querySelector('.incident__actions')).toBeNull();
      expect(text(card.querySelector('.incident__badges'))).toContain('Resuelto');
    });

    it('cuenta los reportes', async () => {
      const { element } = await render([buildIncident()], 1);

      expect(text(element.querySelector('.list-header__count'))).toBe('1 reporte');
    });
  });

  describe('filtro y paginación en la URL', () => {
    it('cambiar a «Resueltos» deja el estado en la URL y lo pide', async () => {
      const { element, settle } = await render([buildIncident()]);

      Array.from(element.querySelectorAll<HTMLAnchorElement>('.tabs a'))
        .find((a) => text(a) === 'Resueltos')!
        .click();
      await settle();

      expect(router.url).toBe(`${PAGE_URL}?status=RESOLVED`);
      expect(listRequest().request.params.get('status')).toBe('RESOLVED');
    });

    it('«Todos» no filtra por estado', async () => {
      const { harness } = await open(`${PAGE_URL}?status=ALL`);

      const request = listRequest();
      expect(request.request.params.has('status')).toBe(false);
      request.flush(buildIncidentPage([]));
      await harness.fixture.whenStable();
    });

    it('marca el filtro vigente', async () => {
      const { element, settle } = await open(`${PAGE_URL}?status=RESOLVED`);
      listRequest().flush(buildIncidentPage([]));
      await settle();

      const current = element.querySelector('.tabs a[aria-current="page"]');
      expect(text(current)).toBe('Resueltos');
    });

    it.each(['CLOSED', 'open', '', 'ALL; DROP'])(
      'ignora el estado manipulado «%s» y vuelve a los abiertos',
      async (value) => {
        const { harness } = await open(`${PAGE_URL}?status=${encodeURIComponent(value)}`);

        const request = listRequest();
        expect(request.request.params.get('status')).toBe('OPEN');
        request.flush(buildIncidentPage([]));
        await harness.fixture.whenStable();
      },
    );

    it('toFilter acepta solo los tres valores válidos', () => {
      expect(toFilter(convertToParamMap({ status: 'OPEN' }))).toBe('OPEN');
      expect(toFilter(convertToParamMap({ status: 'RESOLVED' }))).toBe('RESOLVED');
      expect(toFilter(convertToParamMap({ status: 'ALL' }))).toBe('ALL');
      expect(toFilter(convertToParamMap({}))).toBe('OPEN');
    });

    it('lee la página de la URL y al cambiarla actualiza la URL', async () => {
      const { element, settle } = await open(`${PAGE_URL}?page=2`);
      const first = listRequest();
      expect(first.request.params.get('page')).toBe('2');
      first.flush(buildIncidentPage([buildIncident()], PAGE_SIZE * 2 + 1));
      await settle();

      Array.from(element.querySelectorAll<HTMLButtonElement>('app-pagination button'))
        .find((b) => text(b) === 'Siguiente')!
        .click();
      await settle();

      expect(router.url).toBe(`${PAGE_URL}?page=3`);
      expect(listRequest().request.params.get('page')).toBe('3');
    });
  });

  describe('estados', () => {
    it('sin reportes abiertos muestra el estado vacío', async () => {
      const { element } = await render([]);

      expect(text(element.querySelector('app-empty-state'))).toBe('No hay reportes abiertos.');
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
      listRequest().flush(buildIncidentPage([buildIncident()]));
      await settle();

      expect(cards(element).length).toBe(1);
    });
  });

  describe('resolución con confirmación', () => {
    it.each([
      ['Solicitar versión anonimizada', 'nueva ronda'],
      ['Reasignar Revisor', 'a la espera de un nuevo Revisor'],
      ['Descartar reporte', 'sin cambiar el manuscrito'],
    ])('«%s» explica sus efectos y no actúa hasta confirmar', async (label, effect) => {
      const { element, settle } = await render([buildIncident()]);

      actionButton(cards(element)[0], label).click();
      await settle();

      expect(dialog(element).hasAttribute('open')).toBe(true);
      expect(text(dialog(element))).toContain(effect);
      expect(text(dialog(element))).toContain('no se puede deshacer');
      http.expectNone((r) => r.method === 'POST');
    });

    it('cancelar no resuelve nada', async () => {
      const { element, settle } = await render([buildIncident()]);
      actionButton(cards(element)[0], 'Descartar reporte').click();
      await settle();

      confirmButton(element, 'Cancelar').click();
      await settle();

      http.expectNone((r) => r.method === 'POST');
      expect(dialog(element).hasAttribute('open')).toBe(false);
    });

    it('confirmar envía la resolución elegida y refleja el estado actualizado', async () => {
      const { element, settle } = await render([buildIncident()]);
      actionButton(cards(element)[0], 'Descartar reporte').click();
      await settle();

      confirmButton(element, 'Descartar reporte').click();
      await settle();
      const request = resolveRequest();
      expect(request.request.body).toEqual({ resolution: 'DISMISS' });
      request.flush(buildIncident({ status: 'RESOLVED', resolution: 'DISMISS' }));
      await settle();
      expect(text(element.querySelector('.callout--success'))).toContain(
        'Reporte de GPC-2026-000001 resuelto: descartado.',
      );

      // La lista se vuelve a leer y el reporte ya no está entre los abiertos.
      listRequest().flush(buildIncidentPage([]));
      await settle();
      expect(cards(element).length).toBe(0);
      expect(text(element.querySelector('app-empty-state'))).toBe('No hay reportes abiertos.');
    });

    it('solicitar versión anonimizada envía esa resolución', async () => {
      const { element, settle } = await render([buildIncident()]);
      actionButton(cards(element)[0], 'Solicitar versión anonimizada').click();
      await settle();

      confirmButton(element, 'Solicitar versión anonimizada').click();
      await settle();
      const request = resolveRequest();
      expect(request.request.body).toEqual({ resolution: 'REQUEST_ANONYMIZED_VERSION' });
      request.flush(buildIncident({ status: 'RESOLVED' }));
      await settle();
      listRequest().flush(buildIncidentPage([]));
    });

    it('reasignar ofrece abrir el envío para asignar a otro Revisor', async () => {
      const { element, settle } = await render([buildIncident({ manuscript: 's-9' })]);
      actionButton(cards(element)[0], 'Reasignar Revisor').click();
      await settle();

      confirmButton(element, 'Reasignar Revisor').click();
      await settle();
      resolveRequest().flush(buildIncident({ status: 'RESOLVED', resolution: 'REASSIGN' }));
      await settle();
      listRequest().flush(buildIncidentPage([]));
      await settle();

      const link = element.querySelector<HTMLAnchorElement>('.callout--success a');
      expect(link?.getAttribute('href')).toBe('/app/editor/submissions/s-9');
      expect(text(link)).toBe('Abrir GPC-2026-000001 para asignar a otro Revisor');
    });

    it('un segundo intento muestra el 409 y vuelve a leer la lista', async () => {
      const { element, settle } = await render([buildIncident()]);
      actionButton(cards(element)[0], 'Descartar reporte').click();
      await settle();
      confirmButton(element, 'Descartar reporte').click();
      await settle();

      resolveRequest().flush(errorEnvelope('STATE_CONFLICT', 'El incidente ya fue resuelto.'), {
        status: 409,
        statusText: 'Conflict',
      });
      await settle();

      expect(text(element.querySelector('.callout--error'))).toContain(
        'Otro Editor ya resolvió este reporte',
      );
      expect(element.querySelector('.callout--success')).toBeNull();
      listRequest().flush(
        buildIncidentPage([buildIncident({ status: 'RESOLVED', resolution: 'REASSIGN' })]),
      );
      await settle();
      expect(cards(element)[0].querySelector('.incident__actions')).toBeNull();
    });

    it('un 409 porque el manuscrito ya no está en revisión muestra el motivo del servidor', async () => {
      const { element, settle } = await render([buildIncident()]);
      actionButton(cards(element)[0], 'Reasignar Revisor').click();
      await settle();
      confirmButton(element, 'Reasignar Revisor').click();
      await settle();

      resolveRequest().flush(
        errorEnvelope(
          'STATE_CONFLICT',
          'Solo un manuscrito activo en revisión admite solicitar una versión anonimizada o reasignar.',
        ),
        { status: 409, statusText: 'Conflict' },
      );
      await settle();

      expect(text(element.querySelector('.callout--error'))).toContain(
        'Solo un manuscrito activo en revisión',
      );
      listRequest().flush(buildIncidentPage([buildIncident()]));
    });

    it('un error de red no marca el reporte como resuelto', async () => {
      const { element, settle } = await render([buildIncident()]);
      actionButton(cards(element)[0], 'Descartar reporte').click();
      await settle();
      confirmButton(element, 'Descartar reporte').click();
      await settle();

      resolveRequest().error(new ProgressEvent('error'));
      await settle();

      expect(text(element.querySelector('.callout--error'))).toContain('No fue posible conectar');
      expect(element.querySelector('.callout--success')).toBeNull();
      expect(cards(element)[0].querySelector('.incident__actions')).not.toBeNull();
    });

    it('mientras resuelve no admite otra resolución', async () => {
      const { element, settle } = await render([buildIncident(), buildIncident({ id: 'i-2' })]);
      actionButton(cards(element)[0], 'Descartar reporte').click();
      await settle();
      confirmButton(element, 'Descartar reporte').click();
      await settle();

      const buttons = Array.from(
        element.querySelectorAll<HTMLButtonElement>('.incident__actions button'),
      );
      expect(buttons.every((b) => b.disabled)).toBe(true);
      resolveRequest().flush(buildIncident({ status: 'RESOLVED' }));
      await settle();
      listRequest().flush(buildIncidentPage([]));
    });
  });

  describe('confidencialidad', () => {
    it('no ofrece ninguna acción hacia el Autor ni muestra su contacto', async () => {
      const leaky = {
        ...buildIncident(),
        authors: [{ full_name: 'Ana López Reservada', email: 'ana@unl.edu.ec' }],
      } as Incident;

      const { element } = await render([leaky]);

      expect(element.innerHTML).not.toContain('Ana López Reservada');
      expect(element.innerHTML).not.toContain('ana@unl.edu.ec');
      const actions = Array.from(element.querySelectorAll('button, a')).map((e) => text(e));
      expect(actions.join(' | ')).not.toMatch(/notificar|avisar al autor|contactar/i);
    });
  });
});
