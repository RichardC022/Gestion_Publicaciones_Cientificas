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
import { errorEnvelope } from '../../author/testing/manuscript.fixtures';
import { buildSubmissionPage, buildSubmissionRow } from '../testing/editor.fixtures';
import {
  PAGE_SIZE,
  SubmissionInboxComponent,
  toInboxParams,
} from './submission-inbox.component';

@Component({ template: '' })
class BlankComponent {}

const INBOX = '/app/editor/submissions';

describe('SubmissionInboxComponent', () => {
  let http: HttpTestingController;
  let router: Router;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideRouter([
          { path: 'app/editor/submissions', component: SubmissionInboxComponent },
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

  const listRequest = (): TestRequest => http.expectOne((r) => r.url === '/api/editor/submissions/');

  const open = async (url = INBOX) => {
    const harness = await RouterTestingHarness.create();
    const component = await harness.navigateByUrl(url, SubmissionInboxComponent);
    const element = harness.routeNativeElement as HTMLElement;
    const settle = async () => {
      await harness.fixture.whenStable();
      harness.detectChanges();
    };
    return { harness, component, element, settle };
  };

  const rowsOf = (element: HTMLElement) => Array.from(element.querySelectorAll('tbody tr'));
  const submit = (element: HTMLElement) =>
    (element.querySelector('form button[type="submit"]') as HTMLButtonElement).click();

  describe('tabla', () => {
    it('muestra código, título, autor, área, fecha, versión y ronda', async () => {
      const { element, settle } = await open();
      listRequest().flush(
        buildSubmissionPage([
          buildSubmissionRow({
            code: 'GPC-2026-000007',
            title: 'Suelos del páramo',
            corresponding_author: 'Ana López',
            area: 'Edafología',
            current_version: 2,
            current_round: 1,
            submitted_at: '2026-10-21T15:30:00Z',
          }),
        ]),
      );
      await settle();

      const cells = Array.from(rowsOf(element)[0].querySelectorAll('td')).map((c) =>
        (c.textContent ?? '').replace(/\s+/g, ' ').trim(),
      );
      expect(cells[0]).toBe('GPC-2026-000007');
      expect(cells[1]).toBe('Suelos del páramo');
      expect(cells[2]).toBe('Ana López');
      expect(cells[3]).toBe('Edafología');
      // 15:30 UTC en la zona institucional (UTC-5) son las 10:30.
      expect(cells[4]).toBe('21/10/2026 10:30');
      expect(cells[5]).toBe('v2');
      expect(cells[6]).toBe('Ronda 1');
    });

    it('los datos que faltan se muestran con una raya', async () => {
      const { element, settle } = await open();
      listRequest().flush(
        buildSubmissionPage([
          buildSubmissionRow({
            corresponding_author: null,
            area: '',
            submitted_at: null,
            current_version: 0,
          }),
        ]),
      );
      await settle();

      const cells = Array.from(rowsOf(element)[0].querySelectorAll('td')).map((c) =>
        (c.textContent ?? '').trim(),
      );
      expect([cells[2], cells[3], cells[4], cells[5]]).toEqual(['—', '—', '—', '—']);
    });

    it('el código enlaza con el detalle del envío', async () => {
      const { element, settle } = await open();
      listRequest().flush(buildSubmissionPage([buildSubmissionRow({ id: 's-9' })]));
      await settle();

      const link = rowsOf(element)[0].querySelector('a') as HTMLAnchorElement;
      expect(link.getAttribute('href')).toBe('/app/editor/submissions/s-9');
    });

    it('muestra cuántos envíos esperan', async () => {
      const { element, settle } = await open();
      listRequest().flush(buildSubmissionPage([buildSubmissionRow()], 7));
      await settle();

      expect(element.querySelector('.list-header__count')?.textContent?.trim()).toBe(
        '7 envíos pendientes',
      );
    });

    it('no ofrece acciones de Administrador ni datos de auditoría', async () => {
      const { element, settle } = await open();
      listRequest().flush(buildSubmissionPage([buildSubmissionRow()]));
      await settle();

      const text = (element.textContent ?? '').toLowerCase();
      expect(text).not.toContain('auditor');
      expect(text).not.toContain('administrador');
      expect(element.querySelector('a[href*="/admin"]')).toBeNull();
    });
  });

  describe('estado en la URL', () => {
    it('sin filtros solo pide la primera página con el orden por defecto', async () => {
      await open();

      const request = listRequest();
      expect(request.request.params.get('page_size')).toBe(String(PAGE_SIZE));
      expect(request.request.params.keys().sort()).toEqual(['page_size']);
      request.flush(buildSubmissionPage([]));
    });

    it('los parámetros de la URL se envían a la API y se reflejan en el formulario', async () => {
      const { component, settle } = await open(
        `${INBOX}?search=clima&area=Agronom%C3%ADa&date_from=2026-10-01&date_to=2026-10-31&ordering=title&page=3`,
      );

      const request = listRequest();
      expect(request.request.params.get('search')).toBe('clima');
      expect(request.request.params.get('area')).toBe('Agronomía');
      expect(request.request.params.get('date_from')).toBe('2026-10-01');
      expect(request.request.params.get('date_to')).toBe('2026-10-31');
      expect(request.request.params.get('ordering')).toBe('title');
      expect(request.request.params.get('page')).toBe('3');
      request.flush(buildSubmissionPage([], 0));
      await settle();

      expect(component.filters.getRawValue()).toEqual({
        search: 'clima',
        area: 'Agronomía',
        date_from: '2026-10-01',
        date_to: '2026-10-31',
        ordering: 'title',
      });
    });

    it('descarta los parámetros manipulados a mano en lugar de provocar un 400', async () => {
      await open(`${INBOX}?ordering=password&date_from=ayer&page=-4&status=ACCEPTED`);

      const request = listRequest();
      expect(request.request.params.keys().sort()).toEqual(['page_size']);
      request.flush(buildSubmissionPage([]));
    });

    it('aplicar filtros actualiza la URL y vuelve a consultar', async () => {
      const { component, element, settle } = await open();
      listRequest().flush(buildSubmissionPage([buildSubmissionRow()]));
      await settle();

      component.filters.patchValue({ search: '  clima  ', ordering: 'code' });
      submit(element);
      await settle();

      expect(router.url).toBe(`${INBOX}?search=clima&ordering=code`);
      const request = listRequest();
      expect(request.request.params.get('search')).toBe('clima');
      expect(request.request.params.get('ordering')).toBe('code');
      request.flush(buildSubmissionPage([]));
      await settle();
    });

    it('el orden por defecto no ensucia la URL', async () => {
      const { component, element, settle } = await open();
      listRequest().flush(buildSubmissionPage([buildSubmissionRow()]));
      await settle();

      component.filters.patchValue({ area: 'Medicina' });
      submit(element);
      await settle();

      expect(router.url).toBe(`${INBOX}?area=Medicina`);
      listRequest().flush(buildSubmissionPage([]));
    });

    it('filtrar vuelve a la primera página', async () => {
      const { component, element, settle } = await open(`${INBOX}?page=3`);
      listRequest().flush(buildSubmissionPage([buildSubmissionRow()], 100));
      await settle();

      component.filters.patchValue({ area: 'Medicina' });
      submit(element);
      await settle();

      expect(router.url).toBe(`${INBOX}?area=Medicina`);
      listRequest().flush(buildSubmissionPage([]));
    });

    it('limpiar quita todos los filtros de la URL', async () => {
      const { element, settle } = await open(`${INBOX}?search=clima&ordering=title`);
      listRequest().flush(buildSubmissionPage([]));
      await settle();

      const clear = Array.from(element.querySelectorAll('button')).find(
        (b) => b.textContent?.trim() === 'Limpiar',
      ) as HTMLButtonElement;
      clear.click();
      await settle();

      expect(router.url).toBe(INBOX);
      expect(listRequest().request.params.keys().sort()).toEqual(['page_size']);
    });

    it('una fecha inicial posterior a la final se explica y no consulta', async () => {
      const { component, element, settle } = await open();
      listRequest().flush(buildSubmissionPage([buildSubmissionRow()]));
      await settle();

      component.filters.patchValue({ date_from: '2026-11-01', date_to: '2026-10-01' });
      submit(element);
      await settle();

      expect(element.querySelector('.filters__error')?.textContent).toContain(
        'no puede ser posterior',
      );
      expect(router.url).toBe(INBOX);
    });
  });

  describe('paginación', () => {
    it('Siguiente avanza la página en la URL y en la consulta', async () => {
      const { element, settle } = await open();
      listRequest().flush(buildSubmissionPage([buildSubmissionRow()], 45));
      await settle();
      expect(element.querySelector('app-pagination')?.textContent).toContain('Página 1 de 3');

      const next = Array.from(element.querySelectorAll('app-pagination button')).find(
        (b) => b.textContent?.trim() === 'Siguiente',
      ) as HTMLButtonElement;
      next.click();
      await settle();

      expect(router.url).toBe(`${INBOX}?page=2`);
      const request = listRequest();
      expect(request.request.params.get('page')).toBe('2');
      request.flush(buildSubmissionPage([buildSubmissionRow()], 45));
      await settle();
      expect(element.querySelector('app-pagination')?.textContent).toContain('Página 2 de 3');
    });
  });

  describe('estados', () => {
    it('muestra el indicador de carga hasta que llega la respuesta', async () => {
      const { element, settle } = await open();
      expect(element.querySelector('app-loading-spinner')).not.toBeNull();

      listRequest().flush(buildSubmissionPage([buildSubmissionRow()]));
      await settle();

      expect(element.querySelector('app-loading-spinner')).toBeNull();
    });

    it('sin envíos lo dice sin ofrecer registrar nada', async () => {
      const { element, settle } = await open();
      listRequest().flush(buildSubmissionPage([]));
      await settle();

      expect(element.textContent).toContain('No hay envíos nuevos por revisar.');
      expect(element.querySelector('table')).toBeNull();
    });

    it('con filtros y sin resultados lo explica', async () => {
      const { element, settle } = await open(`${INBOX}?search=nada`);
      listRequest().flush(buildSubmissionPage([]));
      await settle();

      expect(element.textContent).toContain('Ningún envío coincide con los filtros aplicados.');
    });

    it('un error del servidor se muestra con un mensaje accionable y permite reintentar', async () => {
      const { element, settle } = await open();
      listRequest().flush(errorEnvelope('SERVER_ERROR', 'Error interno.'), {
        status: 500,
        statusText: 'Server Error',
      });
      await settle();

      expect(element.querySelector('app-error-state')).not.toBeNull();
      expect(element.querySelector('table')).toBeNull();

      (element.querySelector('app-error-state button') as HTMLButtonElement).click();
      await settle();
      listRequest().flush(buildSubmissionPage([buildSubmissionRow()]));
      await settle();

      expect(element.querySelector('app-error-state')).toBeNull();
      expect(rowsOf(element).length).toBe(1);
    });
  });
});

describe('toInboxParams', () => {
  const parse = (query: Record<string, string>) => toInboxParams(convertToParamMap(query));

  it('conserva solo valores válidos y recorta los textos', () => {
    expect(
      parse({
        search: '  clima ',
        area: ' Agronomía ',
        date_from: '2026-10-01',
        date_to: '2026-10-31',
        ordering: '-updated_at',
        page: '2',
      }),
    ).toEqual({
      page_size: PAGE_SIZE,
      search: 'clima',
      area: 'Agronomía',
      date_from: '2026-10-01',
      date_to: '2026-10-31',
      ordering: '-updated_at',
      page: 2,
    });
  });

  it('ignora órdenes, fechas y páginas inválidas', () => {
    expect(parse({ ordering: 'drop', date_from: '01/10/2026', page: '0', search: '   ' })).toEqual(
      { page_size: PAGE_SIZE },
    );
  });

  it('la primera página no se envía', () => {
    expect(parse({ page: '1' })).toEqual({ page_size: PAGE_SIZE });
  });
});
