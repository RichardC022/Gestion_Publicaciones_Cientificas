import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { buildArticle, buildArticlePage } from '../../features/catalog/testing/catalog.fixtures';
import { authInterceptor } from '../auth/auth.interceptor';
import { AuthStore } from '../auth/auth.store';
import { API_BASE_URL } from '../http/api-base-url.token';
import { errorInterceptor } from '../http/error.interceptor';
import { ApiError } from '../models/api-error.model';
import { CatalogService } from './catalog.service';

describe('CatalogService', () => {
  let service: CatalogService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(withInterceptors([authInterceptor, errorInterceptor])),
        provideHttpClientTesting(),
        { provide: API_BASE_URL, useValue: '/api/' },
      ],
    });
    service = TestBed.inject(CatalogService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  describe('list', () => {
    it('pide la primera página con el tamaño indicado', () => {
      service.list({}, 1, 12).subscribe();

      const request = http.expectOne((r) => r.url === '/api/catalog/');
      expect(request.request.method).toBe('GET');
      expect(request.request.params.get('page_size')).toBe('12');
      expect(request.request.params.has('page')).toBe(false);
      request.flush(buildArticlePage([]));
    });

    it('envía solo los filtros con valor y la página siguiente', () => {
      service
        .list({ search: 'glaciares', area: 'Agronomía', language: 'es', ordering: 'title' }, 3, 12)
        .subscribe();

      const request = http.expectOne((r) => r.url === '/api/catalog/');
      const params = request.request.params;
      expect(params.get('search')).toBe('glaciares');
      expect(params.get('area')).toBe('Agronomía');
      expect(params.get('language')).toBe('es');
      expect(params.get('ordering')).toBe('title');
      expect(params.get('page')).toBe('3');
      expect(params.has('keyword')).toBe(false);
      expect(params.has('date_from')).toBe(false);
      request.flush(buildArticlePage([]));
    });

    it('devuelve la página tal como llega', () => {
      let page: unknown;
      service.list({}).subscribe((value) => (page = value));

      http.expectOne((r) => r.url === '/api/catalog/').flush(buildArticlePage([buildArticle()], 1));

      expect(page).toEqual(buildArticlePage([buildArticle()], 1));
    });

    it('un 400 llega normalizado', () => {
      let error!: ApiError;
      service.list({}).subscribe({ error: (e: ApiError) => (error = e) });

      http
        .expectOne((r) => r.url === '/api/catalog/')
        .flush(
          { error: { code: 'VALIDATION_ERROR', message: 'Filtro inválido.', details: {} } },
          { status: 400, statusText: 'Bad Request' },
        );

      expect(error.status).toBe(400);
      expect(error.code).toBe('VALIDATION_ERROR');
    });
  });

  describe('get', () => {
    it('pide la ficha por código', () => {
      let article: unknown;
      service.get('GPC-2026-000001').subscribe((value) => (article = value));

      http.expectOne('/api/catalog/GPC-2026-000001/').flush(buildArticle());

      expect(article).toEqual(buildArticle());
    });

    it('codifica el código en la ruta', () => {
      service.get('a/b ?').subscribe({ error: () => undefined });

      http.expectOne('/api/catalog/a%2Fb%20%3F/').flush({}, { status: 404, statusText: 'Not Found' });
    });

    it('un 404 llega normalizado', () => {
      let error!: ApiError;
      service.get('GPC-2026-999999').subscribe({ error: (e: ApiError) => (error = e) });

      http
        .expectOne('/api/catalog/GPC-2026-999999/')
        .flush(
          { error: { code: 'NOT_FOUND', message: 'Artículo no encontrado.', details: {} } },
          { status: 404, statusText: 'Not Found' },
        );

      expect(error.status).toBe(404);
    });
  });

  describe('document', () => {
    it('descarga el PDF como blob', () => {
      let blob: Blob | undefined;
      service.document('GPC-2026-000001').subscribe((value) => (blob = value));

      const request = http.expectOne('/api/catalog/GPC-2026-000001/document/');
      expect(request.request.responseType).toBe('blob');
      request.flush(new Blob(['%PDF'], { type: 'application/pdf' }));

      expect(blob?.type).toBe('application/pdf');
    });

    it('un 410 llega normalizado aunque el cuerpo sea un blob', async () => {
      let error!: ApiError;
      service.document('GPC-2026-000001').subscribe({ error: (e: ApiError) => (error = e) });

      const body = JSON.stringify({
        error: { code: 'STATE_CONFLICT', message: 'Documento no disponible.', details: {} },
      });
      http
        .expectOne('/api/catalog/GPC-2026-000001/document/')
        .flush(new Blob([body], { type: 'application/json' }), { status: 410, statusText: 'Gone' });
      await new Promise<void>((resolve) => setTimeout(resolve, 0));

      expect(error.status).toBe(410);
    });
  });

  describe('sin credenciales', () => {
    it('ninguna petición del catálogo lleva Authorization aunque haya sesión', () => {
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

      service.list({}).subscribe();
      service.get('GPC-2026-000001').subscribe();
      service.document('GPC-2026-000001').subscribe();

      for (const request of http.match(() => true)) {
        expect(request.request.headers.has('Authorization')).toBe(false);
        request.flush(null);
      }
    });

    it('un 401 del catálogo no intenta refrescar la sesión', () => {
      let error!: ApiError;
      service.list({}).subscribe({ error: (e: ApiError) => (error = e) });

      http
        .expectOne((r) => r.url === '/api/catalog/')
        .flush({ error: { code: 'AUTH_INVALID', message: 'x', details: {} } }, { status: 401, statusText: 'Unauthorized' });

      expect(error.status).toBe(401);
      http.expectNone('/api/auth/refresh/');
    });
  });
});
