import { Component } from '@angular/core';
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import {
  HttpTestingController,
  TestRequest,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';

import { authInterceptor } from '../../../core/auth/auth.interceptor';
import { AuthStore } from '../../../core/auth/auth.store';
import { API_BASE_URL } from '../../../core/http/api-base-url.token';
import { errorInterceptor } from '../../../core/http/error.interceptor';
import { CatalogArticle } from '../../../core/models/catalog.model';
import { buildArticle } from '../testing/catalog.fixtures';
import { CatalogDetailComponent } from './catalog-detail.component';

@Component({ template: '' })
class BlankComponent {}

const CODE = 'GPC-2026-000001';
const PAGE = `/api/catalog/${CODE}/`;
const DOCUMENT = `/api/catalog/${CODE}/document/`;

function fail(status: number, code: string, message: string) {
  return [
    { error: { code, message, details: {} } },
    { status, statusText: String(status) },
  ] as const;
}

describe('CatalogDetailComponent', () => {
  let http: HttpTestingController;

  beforeAll(() => {
    // jsdom no implementa las URL de objeto que usa el visor.
    if (typeof URL.createObjectURL !== 'function') {
      URL.createObjectURL = () => 'blob:prueba';
      URL.revokeObjectURL = () => undefined;
    }
  });

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideRouter([
          { path: 'catalog', component: BlankComponent },
          { path: 'catalog/:code', component: CatalogDetailComponent },
          { path: 'login', component: BlankComponent },
        ]),
        provideHttpClient(withInterceptors([authInterceptor, errorInterceptor])),
        provideHttpClientTesting(),
        { provide: API_BASE_URL, useValue: '/api/' },
      ],
    });
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  const text = (node: Element | null) => (node?.textContent ?? '').replace(/\s+/g, ' ').trim();
  const pageRequest = (): TestRequest => http.expectOne(PAGE);

  const open = async (code = CODE) => {
    const harness = await RouterTestingHarness.create();
    await harness.navigateByUrl(`/catalog/${code}`, CatalogDetailComponent);
    const element = harness.routeNativeElement as HTMLElement;
    const settle = async () => {
      await harness.fixture.whenStable();
      harness.detectChanges();
    };
    return { harness, element, settle };
  };

  const render = async (article: CatalogArticle = buildArticle()) => {
    const view = await open();
    pageRequest().flush(article);
    await view.settle();
    return view;
  };

  const documentButton = (element: HTMLElement) =>
    Array.from(element.querySelectorAll<HTMLButtonElement>('#document-title ~ button, section button')).find(
      (b) => text(b).includes('documento') || text(b).includes('Reintentar'),
    )!;

  it('muestra un estado de carga mientras espera', async () => {
    const { element } = await open();

    expect(element.querySelector('app-loading-spinner')).not.toBeNull();
    pageRequest().flush(buildArticle());
  });

  describe('ficha', () => {
    it('muestra título, código, área, idioma, versión y fecha', async () => {
      const { element } = await render();

      expect(text(element.querySelector('h1'))).toBe('Glaciares tropicales del Chimborazo');
      expect(text(element.querySelector('.detail__meta'))).toBe(
        'GPC-2026-000001 · Agronomía · Español · Versión 1 · Publicado el 22/10/2026',
      );
    });

    it('muestra autores con su filiación, el resumen y las palabras clave', async () => {
      const { element } = await render();

      const authors = Array.from(element.querySelectorAll('.authors li')).map((li) => text(li));
      expect(authors).toEqual([
        'Ana Lucía Torres Universidad Nacional de Loja',
        'Bruno Díaz UTPL',
      ]);
      expect(text(element.querySelector('.detail__abstract'))).toBe(
        'Estudio del retroceso glaciar entre 2000 y 2025.',
      );
      const keywords = Array.from(element.querySelectorAll('.keywords a'));
      expect(keywords.map((a) => text(a))).toEqual(['glaciares', 'clima']);
      expect(keywords[0].getAttribute('href')).toBe('/catalog?keyword=glaciares');
    });

    it('no incluye evaluaciones, revisores, historial, auditoría ni correos', async () => {
      const { element } = await render();

      const visible = text(element).toLowerCase();
      for (const word of ['revisor', 'evaluaci', 'historial', 'auditor', '@']) {
        expect(visible, word).not.toContain(word);
      }
      expect(
        Array.from(element.querySelectorAll('h2')).map((h) => text(h)),
      ).toEqual(['Autores', 'Resumen', 'Palabras clave', 'Documento']);
    });

    it('ofrece volver al catálogo y el acceso al login', async () => {
      const { element } = await render();

      expect(element.querySelector('.detail__back a')!.getAttribute('href')).toBe('/catalog');
      expect(element.querySelector('app-public-header a[href="/login"]')).not.toBeNull();
    });

    it('no envía credenciales aunque haya sesión', async () => {
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
      await open();

      const request = pageRequest();
      expect(request.request.headers.has('Authorization')).toBe(false);
      request.flush(buildArticle());
    });
  });

  describe('artículo no disponible', () => {
    it.each([404, 410])('un %s muestra un estado controlado, no un error', async (status) => {
      const { element, settle } = await open('GPC-2026-000001');
      pageRequest().flush(...fail(status, 'NOT_FOUND', 'Artículo no encontrado.'));
      await settle();

      expect(text(element.querySelector('h1'))).toBe('Artículo no disponible');
      expect(text(element.querySelector('.unavailable'))).toContain('fue dado de baja');
      expect(element.querySelector('.unavailable a')!.getAttribute('href')).toBe('/catalog');
      expect(element.querySelector('app-error-state')).toBeNull();
      expect(element.querySelector('article')).toBeNull();
    });

    it('un fallo del servidor sí muestra el error con reintento', async () => {
      const { element, settle } = await open();
      pageRequest().flush(...fail(503, 'STORAGE_UNAVAILABLE', 'No disponible'));
      await settle();
      expect(element.querySelector('app-error-state')).not.toBeNull();

      element.querySelector<HTMLButtonElement>('app-error-state button')!.click();
      await settle();
      pageRequest().flush(buildArticle());
      await settle();

      expect(text(element.querySelector('h1'))).toBe('Glaciares tropicales del Chimborazo');
    });
  });

  describe('documento', () => {
    it('no pide el PDF hasta que se solicita', async () => {
      const { element } = await render();

      http.expectNone(DOCUMENT);
      expect(text(documentButton(element))).toBe('Ver el documento (PDF)');
    });

    it('al solicitarlo lo pide sin credenciales y lo muestra en el visor', async () => {
      const { element, settle } = await render();

      documentButton(element).click();
      await settle();
      const request = http.expectOne(DOCUMENT);
      expect(request.request.responseType).toBe('blob');
      expect(request.request.headers.has('Authorization')).toBe(false);
      request.flush(new Blob(['%PDF-1.7'], { type: 'application/pdf' }));
      await settle();

      const viewer = element.querySelector('app-pdf-viewer');
      expect(viewer).not.toBeNull();
      expect(viewer!.querySelector('iframe')!.getAttribute('title')).toBe('Documento GPC-2026-000001');
    });

    it('evita pedirlo dos veces mientras carga', async () => {
      const { element, settle } = await render();

      documentButton(element).click();
      await settle();
      expect(documentButton(element).disabled).toBe(true);
      documentButton(element).click();

      http.expectOne(DOCUMENT).flush(new Blob(['%PDF'], { type: 'application/pdf' }));
      await settle();
    });

    it.each([404, 410])('un %s dice «Documento no disponible»', async (status) => {
      const { element, settle } = await render();

      documentButton(element).click();
      await settle();
      http
        .expectOne(DOCUMENT)
        .flush(
          new Blob([JSON.stringify({ error: { code: 'STATE_CONFLICT', message: 'x', details: {} } })], {
            type: 'application/json',
          }),
          { status, statusText: String(status) },
        );
      await new Promise<void>((resolve) => setTimeout(resolve, 0));
      await settle();

      expect(text(element.querySelector('#document-title')!.parentElement!.querySelector('.callout'))).toBe(
        'Documento no disponible.',
      );
      expect(element.querySelector('app-pdf-viewer')).toBeNull();
      expect(element.querySelector('article')).not.toBeNull();
    });

    it('un fallo del servidor permite reintentar', async () => {
      const { element, settle } = await render();

      documentButton(element).click();
      await settle();
      http
        .expectOne(DOCUMENT)
        .flush(new Blob(['{}'], { type: 'application/json' }), { status: 503, statusText: 'Unavailable' });
      await new Promise<void>((resolve) => setTimeout(resolve, 0));
      await settle();
      expect(text(element.querySelector('.callout'))).not.toBe('');
      expect(element.querySelector('app-pdf-viewer')).toBeNull();

      documentButton(element).click();
      await settle();
      http.expectOne(DOCUMENT).flush(new Blob(['%PDF'], { type: 'application/pdf' }));
      await settle();

      expect(element.querySelector('app-pdf-viewer')).not.toBeNull();
    });
  });
});
