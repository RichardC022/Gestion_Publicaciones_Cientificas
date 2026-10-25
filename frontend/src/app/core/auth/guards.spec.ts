import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { ActivatedRouteSnapshot, Router, RouterStateSnapshot } from '@angular/router';
import { provideRouter } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { vi } from 'vitest';

import { API_BASE_URL } from '../http/api-base-url.token';
import { Role } from '../models/role.model';
import { SessionUser } from '../models/session-user.model';
import { authGuard } from './auth.guard';
import { AuthService } from './auth.service';
import { AuthStore } from './auth.store';
import { publicOnlyGuard } from './public-only.guard';
import { rolesGuard } from './roles.guard';
import { unsavedChangesGuard } from './unsaved-changes.guard';
import { routes } from '../../app.routes';

const USER: SessionUser = {
  id: 'uuid-1',
  institutional_id: 'INST-0001',
  username: 'a.lopez',
  email: 'a.lopez@unl.edu.ec',
  first_name: 'Ana',
  last_name: 'López',
  full_name: 'Ana López',
};

const SESSION = { user: USER, roles: ['AUTHOR'] as Role[], access: 'access-1' };

const ENVELOPE_401 = {
  error: {
    code: 'AUTH_INVALID',
    message: 'Credenciales institucionales inválidas.',
    details: {},
    request_id: 'rid-1',
  },
};

const stateWithUrl = (url: string) => ({ url }) as unknown as RouterStateSnapshot;

const routeWithData = (data: Record<string, unknown>) =>
  ({ data }) as unknown as ActivatedRouteSnapshot;

describe('authGuard', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideRouter(routes),
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: API_BASE_URL, useValue: '/api/' },
      ],
    });
  });

  it('permite el paso con sesión activa', () => {
    TestBed.inject(AuthStore).setSession(SESSION);

    const result = TestBed.runInInjectionContext(() =>
      authGuard(routeWithData({}), stateWithUrl('/app/dashboard')),
    );
    expect(result).toBe(true);
  });

  it('sin sesión: un único refresh y paso si restaura la sesión', async () => {
    const guardResult = TestBed.runInInjectionContext(() =>
      authGuard(routeWithData({}), stateWithUrl('/app/dashboard')),
    );
    const promise = firstValueFrom(guardResult as never);

    const httpMock = TestBed.inject(HttpTestingController);
    httpMock.expectOne('/api/auth/refresh/').flush({
      access: 'access-nuevo',
      user: USER,
      roles: ['AUTHOR'],
    });

    expect(await promise).toBe(true);
    expect(TestBed.inject(AuthStore).isAuthenticated()).toBe(true);
  });

  it('refresh fallido: redirige a /login con returnUrl', async () => {
    const guardResult = TestBed.runInInjectionContext(() =>
      authGuard(routeWithData({}), stateWithUrl('/app/author/manuscripts')),
    );
    const promise = firstValueFrom(guardResult as never);

    const httpMock = TestBed.inject(HttpTestingController);
    httpMock
      .expectOne('/api/auth/refresh/')
      .flush(ENVELOPE_401, { status: 401, statusText: 'Unauthorized' });

    const result = await promise;
    const url = TestBed.inject(Router).serializeUrl(result as never);
    expect(url).toBe('/login?returnUrl=%2Fapp%2Fauthor%2Fmanuscripts');
  });
});

describe('rolesGuard', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideRouter(routes)] });
  });

  it('permite el paso cuando la sesión tiene uno de los roles exigidos', () => {
    TestBed.inject(AuthStore).setSession(SESSION);
    const result = TestBed.runInInjectionContext(() =>
      rolesGuard(
        routeWithData({ roles: ['AUTHOR', 'EDITOR'] }),
        stateWithUrl('/app/author/manuscripts'),
      ),
    );
    expect(result).toBe(true);
  });

  it('sin el rol del módulo muestra el 403', () => {
    TestBed.inject(AuthStore).setSession(SESSION);
    const result = TestBed.runInInjectionContext(() =>
      rolesGuard(routeWithData({ roles: ['ADMIN'] }), stateWithUrl('/app/admin/audit')),
    );
    const url = TestBed.inject(Router).serializeUrl(result as never);
    expect(url).toBe('/forbidden');
  });

  it('sin sesión redirige a /login con returnUrl (no a 403)', () => {
    const result = TestBed.runInInjectionContext(() =>
      rolesGuard(routeWithData({ roles: ['ADMIN'] }), stateWithUrl('/app/admin/audit')),
    );
    const url = TestBed.inject(Router).serializeUrl(result as never);
    expect(url).toBe('/login?returnUrl=%2Fapp%2Fadmin%2Faudit');
  });

  it('sin roles exigidos solo pide sesión', () => {
    TestBed.inject(AuthStore).setSession(SESSION);
    expect(
      TestBed.runInInjectionContext(() =>
        rolesGuard(routeWithData({}), stateWithUrl('/app/dashboard')),
      ),
    ).toBe(true);
  });
});

describe('publicOnlyGuard', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideRouter(routes)] });
  });

  it('con sesión redirige al panel unificado', () => {
    TestBed.inject(AuthStore).setSession(SESSION);
    const result = TestBed.runInInjectionContext(() =>
      publicOnlyGuard(routeWithData({}), stateWithUrl('/login')),
    );
    const url = TestBed.inject(Router).serializeUrl(result as never);
    expect(url).toBe('/app/dashboard');
  });

  it('anónimo puede ver el login', () => {
    expect(
      TestBed.runInInjectionContext(() =>
        publicOnlyGuard(routeWithData({}), stateWithUrl('/login')),
      ),
    ).toBe(true);
  });
});

describe('unsavedChangesGuard', () => {
  it('permite salir de componentes sin formulario sucio', () => {
    expect(
      unsavedChangesGuard({}, routeWithData({}), stateWithUrl('/app'), stateWithUrl('/login')),
    ).toBe(true);
    expect(
      unsavedChangesGuard(
        { hasUnsavedChanges: () => false },
        routeWithData({}),
        stateWithUrl('/app'),
        stateWithUrl('/login'),
      ),
    ).toBe(true);
  });

  it('un formulario sucio advierte y respeta la respuesta', () => {
    const dirty = { hasUnsavedChanges: () => true };
    const confirmSpy = vi.spyOn(window, 'confirm');

    confirmSpy.mockReturnValue(false);
    expect(
      unsavedChangesGuard(dirty, routeWithData({}), stateWithUrl('/app'), stateWithUrl('/login')),
    ).toBe(false);

    confirmSpy.mockReturnValue(true);
    expect(
      unsavedChangesGuard(dirty, routeWithData({}), stateWithUrl('/app'), stateWithUrl('/login')),
    ).toBe(true);

    expect(confirmSpy).toHaveBeenCalledTimes(2);
    expect(confirmSpy.mock.calls[0][0]).toContain('cambios sin guardar');
    confirmSpy.mockRestore();
  });
});

describe('rutas internas con guards (integración)', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideRouter(routes),
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: API_BASE_URL, useValue: '/api/' },
      ],
    });
  });

  it('una persona multirrol accede a todas sus secciones sin conmutar', async () => {
    const router = TestBed.inject(Router);
    TestBed.inject(AuthStore).setSession({
      user: USER,
      roles: ['AUTHOR', 'EDITOR'],
      access: 'access-1',
    });

    expect(await router.navigateByUrl('/app/author/manuscripts')).toBe(true);
    expect(router.url).toBe('/app/author/manuscripts');

    expect(await router.navigateByUrl('/app/editor/submissions')).toBe(true);
    expect(router.url).toBe('/app/editor/submissions');

    // Sin el rol ADMIN: 403 visual, no 404 ni login. El guard redirige,
    // así que la navegación al destino original no se completa.
    await router.navigateByUrl('/app/admin/audit');
    expect(router.url).toBe('/forbidden');
  });

  it('una cuenta autenticada sin roles solo alcanza el panel vacío', async () => {
    const router = TestBed.inject(Router);
    TestBed.inject(AuthStore).setSession({ user: USER, roles: [], access: 'access-1' });

    expect(await router.navigateByUrl('/app/dashboard')).toBe(true);

    await router.navigateByUrl('/app/author/manuscripts');
    expect(router.url).toBe('/forbidden');
  });

  it('anónimo en rutas internas: refresh fallido y vuelta a login con returnUrl', async () => {
    const router = TestBed.inject(Router);
    const httpMock = TestBed.inject(HttpTestingController);

    const navigation = router.navigateByUrl('/app/author/manuscripts');
    // El router procesa la navegación en microtareas: cede el control
    // antes de que el guard dispare el refresh.
    await new Promise((resolve) => setTimeout(resolve, 0));
    httpMock
      .expectOne('/api/auth/refresh/')
      .flush(ENVELOPE_401, { status: 401, statusText: 'Unauthorized' });
    await navigation;

    expect(router.url).toBe('/login?returnUrl=%2Fapp%2Fauthor%2Fmanuscripts');
  });

  it('no existe ruta de selección o conmutación de rol', () => {
    const serialized = JSON.stringify(routes).toLowerCase();
    expect(serialized).not.toMatch(/select|seleccion|switch|conmut/);
    const appRoute = routes.find((route) => route.path === 'app');
    expect(appRoute?.children?.map((child) => child.path)).not.toContain('select-role');
  });
});
