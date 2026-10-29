import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { Route, Router, provideRouter } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';

import { routes } from '../../app.routes';
import { authInterceptor } from '../../core/auth/auth.interceptor';
import { AuthStore } from '../../core/auth/auth.store';
import { API_BASE_URL } from '../../core/http/api-base-url.token';
import { errorInterceptor } from '../../core/http/error.interceptor';
import { buildArticle, buildArticlePage } from './testing/catalog.fixtures';

/**
 * El catálogo público a través de las rutas reales de la SPA (TSK-80):
 * sin guards, sin sesión y sin credenciales en ninguna petición.
 */
describe('Catálogo público (rutas reales)', () => {
  let http: HttpTestingController;

  const route = (path: string): Route => routes.find((r) => r.path === path)!;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideRouter(routes),
        provideHttpClient(withInterceptors([authInterceptor, errorInterceptor])),
        provideHttpClientTesting(),
        { provide: API_BASE_URL, useValue: '/api/' },
      ],
    });
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('/catalog y /catalog/:code se registran sin ningún guard', () => {
    for (const path of ['catalog', 'catalog/:code']) {
      const entry = route(path);
      expect(entry, path).toBeDefined();
      expect(entry.canActivate ?? [], path).toEqual([]);
      expect(entry.canMatch ?? [], path).toEqual([]);
      expect(entry.canActivateChild ?? [], path).toEqual([]);
    }
  });

  it('la raíz lleva al catálogo', async () => {
    const harness = await RouterTestingHarness.create();
    await harness.navigateByUrl('/');

    expect(TestBed.inject(Router).url).toBe('/catalog');
    http.expectOne((r) => r.url === '/api/catalog/').flush(buildArticlePage([]));
  });

  it('un visitante anónimo ve el listado y abre la ficha sin ir a /login', async () => {
    const router = TestBed.inject(Router);
    const harness = await RouterTestingHarness.create();
    await harness.navigateByUrl('/catalog');

    const listing = http.expectOne((r) => r.url === '/api/catalog/');
    expect(listing.request.headers.has('Authorization')).toBe(false);
    listing.flush(buildArticlePage([buildArticle()]));
    await harness.fixture.whenStable();
    harness.detectChanges();
    (harness.routeNativeElement as HTMLElement).querySelector<HTMLAnchorElement>('h2 a')!.click();
    await harness.fixture.whenStable();

    expect(router.url).toBe('/catalog/GPC-2026-000001');
    http.expectOne('/api/catalog/GPC-2026-000001/').flush(buildArticle());
    await harness.fixture.whenStable();
    harness.detectChanges();
    expect(
      (harness.routeNativeElement as HTMLElement).querySelector('h1')!.textContent,
    ).toContain('Glaciares tropicales del Chimborazo');
  });

  it('con sesión iniciada el catálogo tampoco envía el token', async () => {
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
    const harness = await RouterTestingHarness.create();
    await harness.navigateByUrl('/catalog');

    const listing = http.expectOne((r) => r.url === '/api/catalog/');
    expect(listing.request.headers.has('Authorization')).toBe(false);
    listing.flush(buildArticlePage([]));
  });
});
