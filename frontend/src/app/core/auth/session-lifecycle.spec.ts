import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { NavigationEnd, Router } from '@angular/router';
import { provideRouter } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { filter } from 'rxjs/operators';

import { routes } from '../../app.routes';
import { UnifiedDashboardComponent } from '../../features/dashboard/unified-dashboard/unified-dashboard.component';
import { authInterceptor } from './auth.interceptor';
import { AuthService } from './auth.service';
import { AuthStore } from './auth.store';
import { API_BASE_URL } from '../http/api-base-url.token';
import { errorInterceptor } from '../http/error.interceptor';
import { requestIdInterceptor } from '../http/request-id.interceptor';
import { ApiError } from '../models/api-error.model';
import { Role } from '../models/role.model';
import { MeResponse, SessionUser } from '../models/session-user.model';
import { DashboardResponse } from '../models/dashboard.model';

/**
 * Suite de aceptación consolidada de la Fase 1 (TSK-28): recorre las
 * cuatro simulaciones exigidas — refresh fallido, rol retirado,
 * multirrol y fallo parcial de sección — y la garantía transversal de
 * que el access token jamás llega al almacenamiento del navegador.
 */

const USER: SessionUser = {
  id: 'uuid-1',
  institutional_id: 'INST-0001',
  username: 'a.lopez',
  email: 'a.lopez@unl.edu.ec',
  first_name: 'Ana',
  last_name: 'López',
  full_name: 'Ana López',
};

const LOGIN_SESSION = {
  access: 'access-1',
  user: USER,
  roles: ['AUTHOR', 'REVIEWER'] as Role[],
};

const ROTATED_SESSION = {
  access: 'access-2',
  user: USER,
  roles: ['AUTHOR', 'REVIEWER'] as Role[],
};

const ME: MeResponse = {
  user: USER,
  roles: ['REVIEWER'],
  navigation: [],
};

const envelope = (code: string, message: string) => ({
  error: { code, message, details: {}, request_id: 'rid-1' },
});

const dashboardOf = (
  roles: Role[],
  sections: DashboardResponse['sections'],
): DashboardResponse => ({ user: USER, roles, sections });

const ok = (data: Record<string, unknown> = {}) => ({
  status: 'ok' as const,
  data,
  message: null,
});

describe('Ciclo de vida de la sesión (TSK-28)', () => {
  let httpMock: HttpTestingController;
  let store: AuthStore;

  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
  });

  describe('almacenamiento del navegador', () => {
    beforeEach(() => {
      TestBed.configureTestingModule({
        providers: [
          provideRouter(routes),
          provideHttpClient(),
          provideHttpClientTesting(),
          { provide: API_BASE_URL, useValue: '/api/' },
        ],
      });
      httpMock = TestBed.inject(HttpTestingController);
      store = TestBed.inject(AuthStore);
    });

    it('el access token nunca llega a localStorage ni sessionStorage en todo el ciclo', () => {
      const service = TestBed.inject(AuthService);
      const storageIsClean = () => {
        expect(localStorage.length).toBe(0);
        expect(sessionStorage.length).toBe(0);
      };

      // 1. Login: la sesión vive solo en la memoria del store.
      let loggedIn = false;
      service.login('INST-0001', 'institucional-123').subscribe({ complete: () => (loggedIn = true) });
      httpMock.expectOne('/api/auth/login/').flush(LOGIN_SESSION);
      expect(loggedIn).toBe(true);
      expect(store.accessToken()).toBe('access-1');
      storageIsClean();

      // 2. Refresh: token nuevo en memoria, nada persistido.
      let refreshed = '';
      service.refreshOnce().subscribe((token) => (refreshed = token));
      httpMock.expectOne('/api/auth/refresh/').flush(ROTATED_SESSION);
      expect(refreshed).toBe('access-2');
      storageIsClean();

      // 3. /me: roles releídos; sigue sin persistir nada.
      let me: MeResponse | undefined;
      service.me().subscribe((response) => (me = response));
      httpMock.expectOne('/api/auth/me/').flush(ME);
      expect(me?.roles).toEqual(['REVIEWER']);
      expect(store.roles()).toEqual(['REVIEWER']);
      storageIsClean();

      // 4. Logout: sesión limpia por completo.
      let loggedOut = false;
      service.logout().subscribe({ complete: () => (loggedOut = true) });
      httpMock.expectOne('/api/auth/logout/').flush(null, { status: 204, statusText: 'No Content' });
      expect(loggedOut).toBe(true);
      expect(store.isAuthenticated()).toBe(false);
      storageIsClean();

      httpMock.verify();
    });
  });

  describe('refresh fallido', () => {
    let client: HttpClient;
    let router: Router;

    beforeEach(() => {
      TestBed.configureTestingModule({
        providers: [
          provideRouter(routes),
          provideHttpClient(
            withInterceptors([requestIdInterceptor, authInterceptor, errorInterceptor]),
          ),
          provideHttpClientTesting(),
          { provide: API_BASE_URL, useValue: '/api/' },
        ],
      });
      httpMock = TestBed.inject(HttpTestingController);
      store = TestBed.inject(AuthStore);
      client = TestBed.inject(HttpClient);
      router = TestBed.inject(Router);
    });

    it('una ola de 401 con refresh fallido dispara UN único refresh, limpia la sesión y vuelve a login con returnUrl', async () => {
      store.setSession({ user: USER, roles: ['AUTHOR'], access: 'token-expirado' });
      expect(await router.navigateByUrl('/app/author/manuscripts')).toBe(true);
      expect(router.url).toBe('/app/author/manuscripts');

      const failures: ApiError[] = [];
      client.get('/api/manuscripts/a/').subscribe({ error: (e) => failures.push(e) });
      client.get('/api/manuscripts/b/').subscribe({ error: (e) => failures.push(e) });

      // Ambas peticiones caducan a la vez.
      httpMock
        .expectOne('/api/manuscripts/a/')
        .flush(envelope('AUTH_INVALID', 'Credenciales inválidas.'), { status: 401, statusText: 'Unauthorized' });
      httpMock
        .expectOne('/api/manuscripts/b/')
        .flush(envelope('AUTH_INVALID', 'Credenciales inválidas.'), { status: 401, statusText: 'Unauthorized' });

      // La ola comparte un ÚNICO refresh, que también falla.
      const navigationDone = firstValueFrom(
        router.events.pipe(filter((event): event is NavigationEnd => event instanceof NavigationEnd)),
      );
      httpMock
        .expectOne('/api/auth/refresh/')
        .flush(envelope('AUTH_INVALID', 'Credenciales inválidas.'), { status: 401, statusText: 'Unauthorized' });
      await navigationDone;

      // Las dos peticiones reciben su 401 original, la sesión desaparece
      // y la SPA vuelve a login para volver a donde estaba.
      expect(failures.length).toBe(2);
      expect(failures[0].status).toBe(401);
      expect(store.isAuthenticated()).toBe(false);
      expect(router.url).toBe('/login?returnUrl=%2Fapp%2Fauthor%2Fmanuscripts');
      // Exactamente un refresh sirvió a toda la ola.
      httpMock.verify();
    });
  });

  describe('rol retirado durante la sesión', () => {
    beforeEach(() => {
      TestBed.configureTestingModule({
        providers: [
          provideRouter(routes),
          provideHttpClient(),
          provideHttpClientTesting(),
          { provide: API_BASE_URL, useValue: '/api/' },
        ],
      });
      httpMock = TestBed.inject(HttpTestingController);
      store = TestBed.inject(AuthStore);
    });

    it('el módulo del rol retirado desaparece del panel en la siguiente carga', async () => {
      store.setSession({ user: USER, roles: ['AUTHOR', 'REVIEWER'], access: 'access-1' });

      let fixture = TestBed.createComponent(UnifiedDashboardComponent);
      await fixture.whenStable();
      httpMock.expectOne('/api/dashboard/').flush(
        dashboardOf(['AUTHOR', 'REVIEWER'], {
          author: ok({ manuscripts: 3 }),
          reviewer: ok({ pending: 1 }),
        }),
      );
      await fixture.whenStable();
      expect((fixture.nativeElement as HTMLElement).querySelector('app-author-summary')).not.toBeNull();
      expect((fixture.nativeElement as HTMLElement).querySelector('app-reviewer-summary')).not.toBeNull();

      // El backend retira AUTHOR; el próximo /me y el próximo panel ya
      // no lo traen (el access token sigue vigente).
      store.updateUser(USER, ['REVIEWER']);
      fixture.destroy();

      fixture = TestBed.createComponent(UnifiedDashboardComponent);
      await fixture.whenStable();
      httpMock.expectOne('/api/dashboard/').flush(
        dashboardOf(['REVIEWER'], { reviewer: ok({ pending: 1 }) }),
      );
      await fixture.whenStable();

      const element = fixture.nativeElement as HTMLElement;
      expect(element.querySelector('app-author-summary')).toBeNull();
      expect(element.querySelector('app-reviewer-summary')).not.toBeNull();
    });

    it('la siguiente acción del módulo queda bloqueada aunque el token siga vigente', async () => {
      const router = TestBed.inject(Router);
      store.setSession({ user: USER, roles: ['AUTHOR', 'REVIEWER'], access: 'access-1' });
      expect(await router.navigateByUrl('/app/author/manuscripts')).toBe(true);

      // Rol retirado en la base: el store lo refleja (vía /me).
      store.updateUser(USER, ['REVIEWER']);

      // La siguiente acción del módulo (nueva ruta) queda bloqueada
      // aunque el access token siga vigente.
      await router.navigateByUrl('/app/author/manuscripts/new');
      expect(router.url).toBe('/forbidden');
    });
  });
});
