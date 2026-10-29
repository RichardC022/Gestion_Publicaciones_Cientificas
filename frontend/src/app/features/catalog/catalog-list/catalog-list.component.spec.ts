import { Component } from '@angular/core';
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import {
  HttpTestingController,
  TestRequest,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';

import { authInterceptor } from '../../../core/auth/auth.interceptor';
import { AuthStore } from '../../../core/auth/auth.store';
import { API_BASE_URL } from '../../../core/http/api-base-url.token';
import { errorInterceptor } from '../../../core/http/error.interceptor';
import { CatalogArticle } from '../../../core/models/catalog.model';
import { buildArticle, buildArticlePage } from '../testing/catalog.fixtures';
import { CatalogListComponent, PAGE_SIZE } from './catalog-list.component';

@Component({ template: '' })
class BlankComponent {}

const LIST = '/api/catalog/';

describe('CatalogListComponent', () => {
  let http: HttpTestingController;
  let router: Router;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideRouter([
          { path: 'catalog', component: CatalogListComponent },
          { path: 'catalog/:code', component: BlankComponent },
          { path: 'login', component: BlankComponent },
        ]),
        provideHttpClient(withInterceptors([authInterceptor, errorInterceptor])),
        provideHttpClientTesting(),
        { provide: API_BASE_URL, useValue: '/api/' },
      ],
    });
    http = TestBed.inject(HttpTestingController);
    router = TestBed.inject(Router);
  });

  afterEach(() => http.verify());

  const text = (node: Element | null) => (node?.textContent ?? '').replace(/\s+/g, ' ').trim();
  const listRequest = (): TestRequest => http.expectOne((r) => r.method === 'GET' && r.url === LIST);

  const open = async (url = '/catalog') => {
    const harness = await RouterTestingHarness.create();
    await harness.navigateByUrl(url, CatalogListComponent);
    const element = harness.routeNativeElement as HTMLElement;
    const settle = async () => {
      await harness.fixture.whenStable();
      harness.detectChanges();
    };
    return { harness, element, settle };
  };

  const render = async (articles: CatalogArticle[], count = articles.length, url = '/catalog') => {
    const view = await open(url);
    listRequest().flush(buildArticlePage(articles, count));
    await view.settle();
    return view;
  };

  const cards = (element: HTMLElement) => Array.from(element.querySelectorAll('.article'));

  it('muestra un estado de carga mientras espera', async () => {
    const { element } = await open();

    expect(element.querySelector('app-loading-spinner')).not.toBeNull();
    listRequest().flush(buildArticlePage([]));
  });

  it('es público: encabezado con acceso al login y petición sin Authorization', async () => {
    TestBed.inject(AuthStore).setSession({
      user: {
        id: 'u-1',
        institutional_id: 'INST-1',
        username: 'a.lopez',
        email: 'a.lopez@unl.edu.ec',
        first_name: 'Ana',
        last_name: 'López',
        full_name: 'Ana López',
      },
      roles: ['AUTHOR'],
      access: 'token-vigente',
    });
    const { element, settle } = await open();

    const request = listRequest();
    expect(request.request.headers.has('Authorization')).toBe(false);
    request.flush(buildArticlePage([]));
    await settle();
    expect(element.querySelector('app-public-header a[href="/login"]')).not.toBeNull();
  });

  describe('lista', () => {
    it('pide la primera página sin filtros', async () => {
      const { settle } = await open();

      const request = listRequest();
      expect(request.request.params.get('page_size')).toBe(String(PAGE_SIZE));
      expect(request.request.params.has('search')).toBe(false);
      expect(request.request.params.has('page')).toBe(false);
      request.flush(buildArticlePage([]));
      await settle();
    });

    it('muestra título, autores, metadatos, resumen y palabras clave de cada artículo', async () => {
      const { element } = await render([buildArticle()], 1);

      const card = cards(element)[0];
      expect(text(card.querySelector('h2'))).toBe('Glaciares tropicales del Chimborazo');
      expect(card.querySelector('h2 a')!.getAttribute('href')).toBe('/catalog/GPC-2026-000001');
      expect(text(card.querySelector('.article__authors'))).toBe('Ana Lucía Torres; Bruno Díaz');
      expect(text(card.querySelector('.article__meta'))).toBe(
        'GPC-2026-000001 · Agronomía · Español · Publicado el 22/10/2026',
      );
      expect(text(card.querySelector('.article__abstract'))).toBe(
        'Estudio del retroceso glaciar entre 2000 y 2025.',
      );
      expect(
        Array.from(card.querySelectorAll('.article__keywords li')).map((item) => text(item)),
      ).toEqual(['glaciares', 'clima']);
      expect(text(element.querySelector('.catalog__count'))).toBe('1 artículo');
    });

    it('recorta los resúmenes largos', async () => {
      const { element } = await render([buildArticle({ abstract: 'palabra '.repeat(100) })]);

      const abstract = text(cards(element)[0].querySelector('.article__abstract'));
      expect(abstract.endsWith('…')).toBe(true);
      expect(abstract.length).toBeLessThan(300);
    });

    it('pluraliza el conteo', async () => {
      const { element } = await render([buildArticle(), buildArticle({ code: 'GPC-2026-000002' })]);

      expect(text(element.querySelector('.catalog__count'))).toBe('2 artículos');
    });

    it('no muestra evaluaciones, revisores, historial, auditoría ni correos', async () => {
      const { element } = await render([buildArticle()]);

      const visible = text(element).toLowerCase();
      for (const word of ['revisor', 'evaluaci', 'historial', 'auditor', '@']) {
        expect(visible, word).not.toContain(word);
      }
    });

    it('sin artículos dice que aún no hay publicados', async () => {
      const { element } = await render([]);

      expect(text(element.querySelector('app-empty-state'))).toBe('Aún no hay artículos publicados.');
    });
  });

  describe('búsqueda y filtros', () => {
    it('toma los filtros combinados de la URL y los envía', async () => {
      const { settle } = await open(
        '/catalog?search=glaciares&area=Agronom%C3%ADa&language=es&date_from=2026-01-01&ordering=title&page=2',
      );

      const params = listRequest().request.params;
      expect(params.get('search')).toBe('glaciares');
      expect(params.get('area')).toBe('Agronomía');
      expect(params.get('language')).toBe('es');
      expect(params.get('date_from')).toBe('2026-01-01');
      expect(params.get('ordering')).toBe('title');
      expect(params.get('page')).toBe('2');
      http.expectNone(LIST);
      await settle();
    });

    it('descarta los parámetros manipulados en lugar de provocar un 400', async () => {
      const { settle } = await open('/catalog?language=espanol&date_from=ayer&ordering=code&page=-3');

      const params = listRequest().request.params;
      expect(params.has('language')).toBe(false);
      expect(params.has('date_from')).toBe(false);
      expect(params.has('ordering')).toBe(false);
      expect(params.has('page')).toBe(false);
      await settle();
    });

    it('al buscar pone los filtros en la URL y vuelve a la primera página', async () => {
      const { element, settle } = await render([buildArticle()], 30, '/catalog?page=2');
      const field = element.querySelector<HTMLInputElement>('#catalog-search')!;
      field.value = 'quinua';
      field.dispatchEvent(new Event('input'));

      element.querySelector('form')!.dispatchEvent(new Event('submit'));
      await settle();

      expect(router.url).toBe('/catalog?search=quinua');
      const params = listRequest().request.params;
      expect(params.get('search')).toBe('quinua');
      expect(params.has('page')).toBe(false);
    });

    it('Limpiar quita todos los filtros', async () => {
      const { element, settle } = await render([buildArticle()], 1, '/catalog?search=glaciares&area=Agronom%C3%ADa');

      element.querySelectorAll<HTMLButtonElement>('.search__actions button')[1].click();
      await settle();

      expect(router.url).toBe('/catalog');
      expect(listRequest().request.params.has('search')).toBe(false);
    });

    it('con filtros y sin resultados lo dice de forma distinta', async () => {
      const { element } = await render([], 0, '/catalog?search=nada');

      expect(text(element.querySelector('app-empty-state'))).toBe(
        'Ningún artículo coincide con la búsqueda.',
      );
    });
  });

  describe('paginación', () => {
    it('muestra la paginación y pide la página siguiente', async () => {
      const { element, settle } = await render([buildArticle()], 30);

      const next = Array.from(element.querySelectorAll<HTMLButtonElement>('app-pagination button')).find(
        (b) => text(b) === 'Siguiente',
      )!;
      next.click();
      await settle();

      expect(router.url).toBe('/catalog?page=2');
      expect(listRequest().request.params.get('page')).toBe('2');
    });

    it('conserva los filtros al cambiar de página', async () => {
      const { element, settle } = await render([buildArticle()], 30, '/catalog?search=glaciares');

      Array.from(element.querySelectorAll<HTMLButtonElement>('app-pagination button'))
        .find((b) => text(b) === 'Siguiente')!
        .click();
      await settle();

      expect(router.url).toBe('/catalog?search=glaciares&page=2');
      const params = listRequest().request.params;
      expect(params.get('search')).toBe('glaciares');
      expect(params.get('page')).toBe('2');
    });
  });

  describe('errores', () => {
    it('muestra el error con reintento y vuelve a pedir la lista', async () => {
      const { element, settle } = await open();
      listRequest().flush(
        { error: { code: 'SERVER_ERROR', message: 'Error interno', details: {} } },
        { status: 500, statusText: 'Server Error' },
      );
      await settle();
      expect(element.querySelector('app-error-state')).not.toBeNull();

      element.querySelector<HTMLButtonElement>('app-error-state button')!.click();
      await settle();
      listRequest().flush(buildArticlePage([buildArticle()]));
      await settle();

      expect(cards(element)).toHaveLength(1);
    });
  });
});
