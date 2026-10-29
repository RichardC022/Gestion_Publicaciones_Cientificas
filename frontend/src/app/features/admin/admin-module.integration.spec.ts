import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';

import { routes } from '../../app.routes';
import { AuthStore } from '../../core/auth/auth.store';
import { API_BASE_URL } from '../../core/http/api-base-url.token';
import { Role } from '../../core/models/role.model';
import { SessionUser } from '../../core/models/session-user.model';
import { EVENT_ID, buildEvent, buildEventDetail, buildEventPage } from './testing/audit.fixtures';

/**
 * Auditoría del Administrador con las rutas REALES de la SPA (TSK-81):
 * carga diferida, guard de rol, títulos y navegación lista → detalle.
 */
const USER: SessionUser = {
  id: 'u-1',
  institutional_id: 'INST-0001',
  username: 'a.admin',
  email: 'a.admin@unl.edu.ec',
  first_name: 'Ada',
  last_name: 'Admin',
  full_name: 'Ada Admin',
};

describe('Módulo Administrador: integración con las rutas reales', () => {
  let http: HttpTestingController;
  let router: Router;
  let store: AuthStore;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideRouter(routes),
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: API_BASE_URL, useValue: '/api/' },
      ],
    });
    http = TestBed.inject(HttpTestingController);
    router = TestBed.inject(Router);
    store = TestBed.inject(AuthStore);
  });

  afterEach(() => http.verify());

  const signIn = (...roles: Role[]) => store.setSession({ user: USER, roles, access: 'token' });
  const listRequest = () => http.expectOne((r) => r.url === '/api/admin/audit/');

  it('un Administrador abre la auditoría y llega al detalle de un evento', async () => {
    signIn('ADMIN');
    const harness = await RouterTestingHarness.create();
    await harness.navigateByUrl('/app/admin/audit');

    expect(router.url).toBe('/app/admin/audit');
    listRequest().flush(buildEventPage([buildEvent()]));
    await harness.fixture.whenStable();
    harness.detectChanges();
    const element = harness.routeNativeElement as HTMLElement;
    expect(element.querySelector('app-audit-log-list')).not.toBeNull();

    element.querySelector<HTMLAnchorElement>('tbody a[href^="/app/admin/audit/"]')!.click();
    await harness.fixture.whenStable();

    expect(router.url).toBe(`/app/admin/audit/${EVENT_ID}`);
    http.expectOne(`/api/admin/audit/${EVENT_ID}/`).flush(buildEventDetail());
    await harness.fixture.whenStable();
    harness.detectChanges();
    expect(element.querySelector('app-audit-log-detail')).not.toBeNull();
  });

  it('el detalle puede abrirse directamente por URL', async () => {
    signIn('ADMIN');
    const harness = await RouterTestingHarness.create();
    await harness.navigateByUrl(`/app/admin/audit/${EVENT_ID}`);

    http.expectOne(`/api/admin/audit/${EVENT_ID}/`).flush(buildEventDetail());
    await harness.fixture.whenStable();
    harness.detectChanges();

    expect((harness.routeNativeElement as HTMLElement).querySelector('h1')!.textContent).toContain(
      'Detalle del evento',
    );
  });

  it.each([['AUTHOR'], ['REVIEWER'], ['EDITOR']] as const)(
    'un %s va a /forbidden sin pedir nada a la auditoría',
    async (role) => {
      signIn(role);
      const harness = await RouterTestingHarness.create();
      await harness.navigateByUrl('/app/admin/audit');

      expect(router.url).toBe('/forbidden');

      await harness.navigateByUrl(`/app/admin/audit/${EVENT_ID}`);
      expect(router.url).toBe('/forbidden');
    },
  );

  it('las rutas tienen título', () => {
    const app = routes.find((r) => r.path === 'app')!;
    const titles = Object.fromEntries(app.children!.map((r) => [r.path, r.title]));

    expect(titles['admin/audit']).toBe('Auditoría');
    expect(titles['admin/audit/:id']).toBe('Detalle del evento');
  });
});
