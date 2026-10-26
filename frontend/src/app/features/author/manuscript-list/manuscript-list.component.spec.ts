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
import { MANUSCRIPT_STATUSES } from '../../../core/models/manuscript.model';
import { buildManuscript, buildPage, errorEnvelope } from '../testing/manuscript.fixtures';
import { ManuscriptListComponent, PAGE_SIZE, toListParams } from './manuscript-list.component';

@Component({ template: '' })
class BlankComponent {}

describe('ManuscriptListComponent', () => {
  let http: HttpTestingController;
  let router: Router;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideRouter([
          { path: 'app/author/manuscripts', component: ManuscriptListComponent },
          { path: 'app/author/manuscripts/new', component: BlankComponent },
          { path: 'app/author/manuscripts/:id', component: BlankComponent },
          { path: 'app/author/manuscripts/:id/edit', component: BlankComponent },
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

  const listRequest = (): TestRequest => http.expectOne((r) => r.url === '/api/manuscripts/');

  const open = async (url = '/app/author/manuscripts') => {
    const harness = await RouterTestingHarness.create();
    const component = await harness.navigateByUrl(url, ManuscriptListComponent);
    const element = harness.routeNativeElement as HTMLElement;
    const settle = async () => {
      await harness.fixture.whenStable();
      harness.detectChanges();
    };
    return { harness, component, element, settle };
  };

  const rowsOf = (element: HTMLElement) => Array.from(element.querySelectorAll('tbody tr'));

  describe('tabla', () => {
    it('muestra código, título, estado, versión, ronda, actualización y acción pendiente', async () => {
      const { element, settle } = await open();
      listRequest().flush(
        buildPage([
          buildManuscript({
            id: 'm-7',
            code: 'GPC-2026-000007',
            title: 'Suelos del páramo',
            status: 'REQUIRES_CORRECTIONS',
            current_version: 2,
            current_round: 1,
            updated_at: '2026-10-21T15:30:00Z',
          }),
        ]),
      );
      await settle();

      const cells = Array.from(rowsOf(element)[0].querySelectorAll('td')).map((c) =>
        (c.textContent ?? '').replace(/\s+/g, ' ').trim(),
      );
      expect(cells[0]).toBe('GPC-2026-000007');
      expect(cells[1]).toBe('Suelos del páramo');
      expect(cells[2]).toBe('Requiere correcciones');
      expect(cells[3]).toBe('v2');
      expect(cells[4]).toBe('Ronda 1');
      // 15:30 UTC en la zona institucional (UTC-5) son las 10:30.
      expect(cells[5]).toBe('21/10/2026 10:30');
      expect(cells[6]).toBe('Enviar nueva versión');
    });

    it('un borrador sin versión formal muestra una raya', async () => {
      const { element, settle } = await open();
      listRequest().flush(buildPage([buildManuscript({ current_version: 0 })]));
      await settle();

      expect(rowsOf(element)[0].querySelectorAll('td')[3].textContent?.trim()).toBe('—');
    });

    it('el código enlaza con el detalle del manuscrito', async () => {
      const { element, settle } = await open();
      listRequest().flush(buildPage([buildManuscript({ id: 'm-9' })]));
      await settle();

      const link = rowsOf(element)[0].querySelector('a') as HTMLAnchorElement;
      expect(link.getAttribute('href')).toBe('/app/author/manuscripts/m-9');
    });

    it('solo ofrece Editar en Borrador y Requiere correcciones', async () => {
      const { element, settle } = await open();
      listRequest().flush(
        buildPage(
          MANUSCRIPT_STATUSES.map((status, index) =>
            buildManuscript({ id: `m-${index}`, code: `C-${status}`, status }),
          ),
        ),
      );
      await settle();

      const editable = rowsOf(element)
        .filter((row) =>
          Array.from(row.querySelectorAll('a')).some((a) => a.textContent?.trim() === 'Editar'),
        )
        .map((row) => row.querySelector('td')?.textContent?.trim());
      expect(editable).toEqual(['C-DRAFT', 'C-REQUIRES_CORRECTIONS']);
    });

    it('un manuscrito archivado muestra «Dado de baja», «Archivado» y no ofrece editar', async () => {
      const { element, settle } = await open('/app/author/manuscripts?archived=true');
      listRequest().flush(
        buildPage([
          buildManuscript({
            status: 'DRAFT',
            is_active: false,
            withdrawn_at: '2026-10-22T00:00:00Z',
          }),
        ]),
      );
      await settle();

      const row = rowsOf(element)[0];
      expect(row.textContent).toContain('Dado de baja');
      expect(row.textContent).toContain('Archivado');
      expect(
        Array.from(row.querySelectorAll('a')).some((a) => a.textContent?.trim() === 'Editar'),
      ).toBe(false);
    });

    it('no muestra identidades de revisores ni datos internos', async () => {
      const { element, settle } = await open();
      listRequest().flush(buildPage([buildManuscript({ status: 'UNDER_REVIEW' })]));
      await settle();

      const text = (element.textContent ?? '').toLowerCase();
      expect(text).not.toContain('confidencial');
      expect(text).not.toContain('puntuación');
    });
  });

  describe('estado en la URL', () => {
    it('sin filtros solo pide la primera página', async () => {
      await open();

      const request = listRequest();
      expect(request.request.params.get('page_size')).toBe(String(PAGE_SIZE));
      expect(request.request.params.keys().sort()).toEqual(['page_size']);
      request.flush(buildPage([]));
    });

    it('los parámetros de la URL se envían a la API y se reflejan en el formulario', async () => {
      const { component, settle } = await open(
        '/app/author/manuscripts?status=DRAFT&date_from=2026-10-01&date_to=2026-10-31&archived=true&page=3',
      );

      const request = listRequest();
      expect(request.request.params.get('status')).toBe('DRAFT');
      expect(request.request.params.get('date_from')).toBe('2026-10-01');
      expect(request.request.params.get('date_to')).toBe('2026-10-31');
      expect(request.request.params.get('archived')).toBe('true');
      expect(request.request.params.get('page')).toBe('3');
      request.flush(buildPage([], 0));
      await settle();

      expect(component.filters.getRawValue()).toEqual({
        status: 'DRAFT',
        date_from: '2026-10-01',
        date_to: '2026-10-31',
        archived: true,
      });
    });

    it('descarta los parámetros manipulados a mano en lugar de provocar un 400', async () => {
      await open('/app/author/manuscripts?status=HACKED&date_from=ayer&page=-4&archived=quizas');

      const request = listRequest();
      expect(request.request.params.keys().sort()).toEqual(['page_size']);
      request.flush(buildPage([]));
    });

    it('aplicar filtros actualiza la URL y vuelve a consultar', async () => {
      const { component, element, settle } = await open();
      listRequest().flush(buildPage([buildManuscript()]));
      await settle();

      component.filters.patchValue({ status: 'REQUIRES_CORRECTIONS', date_from: '2026-10-01' });
      (element.querySelector('form button[type="submit"]') as HTMLButtonElement).click();
      await settle();

      expect(router.url).toBe(
        '/app/author/manuscripts?status=REQUIRES_CORRECTIONS&date_from=2026-10-01',
      );
      const request = listRequest();
      expect(request.request.params.get('status')).toBe('REQUIRES_CORRECTIONS');
      expect(request.request.params.get('date_from')).toBe('2026-10-01');
      request.flush(buildPage([]));
      await settle();
    });

    it('filtrar vuelve a la primera página', async () => {
      const { component, element, settle } = await open('/app/author/manuscripts?page=3');
      listRequest().flush(buildPage([buildManuscript()], 100));
      await settle();

      component.filters.patchValue({ status: 'DRAFT' });
      (element.querySelector('form button[type="submit"]') as HTMLButtonElement).click();
      await settle();

      expect(router.url).toBe('/app/author/manuscripts?status=DRAFT');
      listRequest().flush(buildPage([]));
    });

    it('limpiar quita todos los filtros de la URL', async () => {
      const { element, settle } = await open('/app/author/manuscripts?status=DRAFT&archived=true');
      listRequest().flush(buildPage([]));
      await settle();

      const clear = Array.from(element.querySelectorAll('button')).find(
        (b) => b.textContent?.trim() === 'Limpiar',
      ) as HTMLButtonElement;
      clear.click();
      await settle();

      expect(router.url).toBe('/app/author/manuscripts');
      expect(listRequest().request.params.keys().sort()).toEqual(['page_size']);
    });

    it('una fecha inicial posterior a la final se explica y no consulta', async () => {
      const { component, element, settle } = await open();
      listRequest().flush(buildPage([buildManuscript()]));
      await settle();

      component.filters.patchValue({ date_from: '2026-11-01', date_to: '2026-10-01' });
      (element.querySelector('form button[type="submit"]') as HTMLButtonElement).click();
      await settle();

      expect(element.querySelector('.filters__error')?.textContent).toContain(
        'no puede ser posterior',
      );
      expect(router.url).toBe('/app/author/manuscripts');
    });
  });

  describe('vista de archivados', () => {
    it('activar «Ver archivados» pide archived=true y cambia el título', async () => {
      const { component, element, settle } = await open();
      listRequest().flush(buildPage([buildManuscript()]));
      await settle();
      expect(element.querySelector('h1')?.textContent).toContain('Mis manuscritos');

      component.filters.patchValue({ archived: true });
      (element.querySelector('form button[type="submit"]') as HTMLButtonElement).click();
      await settle();

      const request = listRequest();
      expect(request.request.params.get('archived')).toBe('true');
      request.flush(buildPage([]));
      await settle();
      expect(element.querySelector('h1')?.textContent).toContain('Manuscritos archivados');
      expect(element.textContent).toContain('No tiene manuscritos archivados.');
    });
  });

  describe('paginación', () => {
    it('Siguiente avanza la página en la URL y en la consulta', async () => {
      const { element, settle } = await open();
      listRequest().flush(buildPage([buildManuscript()], 45));
      await settle();
      expect(element.querySelector('app-pagination')?.textContent).toContain('Página 1 de 3');

      const next = Array.from(element.querySelectorAll('app-pagination button')).find(
        (b) => b.textContent?.trim() === 'Siguiente',
      ) as HTMLButtonElement;
      next.click();
      await settle();

      expect(router.url).toBe('/app/author/manuscripts?page=2');
      const request = listRequest();
      expect(request.request.params.get('page')).toBe('2');
      request.flush(buildPage([buildManuscript()], 45));
      await settle();
      expect(element.querySelector('app-pagination')?.textContent).toContain('Página 2 de 3');
    });

    it('la primera página no deja page en la URL', async () => {
      const { element, settle } = await open('/app/author/manuscripts?page=2');
      listRequest().flush(buildPage([buildManuscript()], 45));
      await settle();

      const previous = Array.from(element.querySelectorAll('app-pagination button')).find(
        (b) => b.textContent?.trim() === 'Anterior',
      ) as HTMLButtonElement;
      previous.click();
      await settle();

      expect(router.url).toBe('/app/author/manuscripts');
      listRequest().flush(buildPage([]));
    });
  });

  describe('estados', () => {
    it('muestra el indicador de carga hasta que llega la respuesta', async () => {
      const { element, settle } = await open();
      expect(element.querySelector('app-loading-spinner')).not.toBeNull();

      listRequest().flush(buildPage([buildManuscript()]));
      await settle();

      expect(element.querySelector('app-loading-spinner')).toBeNull();
    });

    it('sin manuscritos ofrece registrar el primero', async () => {
      const { element, settle } = await open();
      listRequest().flush(buildPage([]));
      await settle();

      expect(element.textContent).toContain('Aún no ha registrado manuscritos.');
      (element.querySelector('app-empty-state button') as HTMLButtonElement).click();
      await settle();
      expect(router.url).toBe('/app/author/manuscripts/new');
    });

    it('con filtros sin resultados lo explica', async () => {
      const { element, settle } = await open('/app/author/manuscripts?status=REJECTED');
      listRequest().flush(buildPage([]));
      await settle();

      expect(element.textContent).toContain(
        'Ningún manuscrito coincide con los filtros aplicados.',
      );
    });

    it('un error muestra el mensaje accionable y reintentar vuelve a consultar', async () => {
      const { element, settle } = await open();
      listRequest().flush(errorEnvelope('SERVER_ERROR', 'Error interno.'), {
        status: 500,
        statusText: 'Server Error',
      });
      await settle();

      expect(element.querySelector('app-error-state [role="alert"]')?.textContent).toContain(
        'Error interno del servidor',
      );

      (element.querySelector('app-error-state button') as HTMLButtonElement).click();
      await settle();
      listRequest().flush(buildPage([buildManuscript()]));
      await settle();

      expect(element.querySelector('app-error-state')).toBeNull();
      expect(rowsOf(element).length).toBe(1);
    });

    it('«Nuevo manuscrito» lleva al formulario de alta', async () => {
      const { element, settle } = await open();
      listRequest().flush(buildPage([]));
      await settle();

      const link = element.querySelector('a.btn--primary') as HTMLAnchorElement;
      expect(link.getAttribute('href')).toBe('/app/author/manuscripts/new');
    });
  });
});

describe('toListParams', () => {
  const params = (query: Record<string, string>) => toListParams(convertToParamMap(query));

  it('siempre fija el tamaño de página', () => {
    expect(params({})).toEqual({ page_size: PAGE_SIZE });
  });

  it('acepta los valores válidos', () => {
    expect(
      params({
        status: 'ACCEPTED',
        date_from: '2026-01-31',
        date_to: '2026-02-01',
        archived: 'true',
        page: '2',
      }),
    ).toEqual({
      page_size: PAGE_SIZE,
      status: 'ACCEPTED',
      date_from: '2026-01-31',
      date_to: '2026-02-01',
      archived: true,
      page: 2,
    });
  });

  it.each([
    [{ status: 'accepted' }],
    [{ status: '' }],
    [{ date_from: '2026-1-5' }],
    [{ date_to: '31/10/2026' }],
    [{ archived: 'false' }],
    [{ page: '1' }],
    [{ page: '0' }],
    [{ page: 'abc' }],
  ])('descarta %j', (query) => {
    expect(params(query)).toEqual({ page_size: PAGE_SIZE });
  });
});
