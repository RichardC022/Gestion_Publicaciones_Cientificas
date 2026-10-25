import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { NavigationEnd, Router } from '@angular/router';
import { provideRouter } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { filter } from 'rxjs/operators';

import { API_BASE_URL } from '../http/api-base-url.token';
import { ApiError } from '../models/api-error.model';
import { LoginResponse } from '../models/session-user.model';
import { AuthService } from './auth.service';
import { AuthStore } from './auth.store';

@Component({ template: '' })
class DummyComponent {}

const SESSION: LoginResponse = {
  access: 'access-nuevo',
  user: {
    id: 'uuid-1',
    institutional_id: 'INST-0001',
    username: 'a.lopez',
    email: 'a.lopez@unl.edu.ec',
    first_name: 'Ana',
    last_name: 'López',
    full_name: 'Ana López',
  },
  roles: ['AUTHOR'],
};

const ENVELOPE_401 = {
  error: {
    code: 'AUTH_INVALID',
    message: 'Credenciales institucionales inválidas.',
    details: {},
    request_id: 'rid-1',
  },
};

describe('AuthService', () => {
  let service: AuthService;
  let store: AuthStore;
  let httpMock: HttpTestingController;
  let router: Router;

  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([
          { path: 'login', component: DummyComponent },
          { path: 'panel', component: DummyComponent },
        ]),
        { provide: API_BASE_URL, useValue: '/api/' },
      ],
    });
    service = TestBed.inject(AuthService);
    store = TestBed.inject(AuthStore);
    httpMock = TestBed.inject(HttpTestingController);
    router = TestBed.inject(Router);
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('login abre la sesión con withCredentials y sin tocar localStorage', () => {
    service.login('INST-0001', 'secreto-123').subscribe();

    const request = httpMock.expectOne('/api/auth/login/');
    expect(request.request.method).toBe('POST');
    expect(request.request.withCredentials).toBe(true);
    expect(request.request.body).toEqual({ identifier: 'INST-0001', password: 'secreto-123' });
    request.flush(SESSION);

    expect(store.accessToken()).toBe('access-nuevo');
    expect(store.roles()).toEqual(['AUTHOR']);
    expect(store.isAuthenticated()).toBe(true);
    expect(localStorage.length).toBe(0);
  });

  it('login fallido entrega un ApiError normalizado del envelope', () => {
    let failure: ApiError | undefined;
    service.login('INST-0001', 'mala').subscribe({ error: (error) => (failure = error) });

    httpMock.expectOne('/api/auth/login/').flush(ENVELOPE_401, { status: 401, statusText: 'Unauthorized' });

    expect(failure?.status).toBe(401);
    expect(failure?.code).toBe('AUTH_INVALID');
    expect(failure?.requestId).toBe('rid-1');
    expect(failure?.userMessage).toContain('Inicie sesión de nuevo');
    expect(store.isAuthenticated()).toBe(false);
  });

  it('refreshOnce comparte un ÚNICO refresh entre suscriptores concurrentes', () => {
    let first = '';
    let second = '';
    service.refreshOnce().subscribe((token) => (first = token));
    service.refreshOnce().subscribe((token) => (second = token));

    const refresh = httpMock.expectOne('/api/auth/refresh/');
    expect(refresh.request.withCredentials).toBe(true);
    refresh.flush(SESSION);

    expect(first).toBe('access-nuevo');
    expect(second).toBe('access-nuevo');
    expect(store.accessToken()).toBe('access-nuevo');
    // Una sola petición de refresh sirvió a las dos llamadas.
    httpMock.verify();
  });

  it('refreshOnce fallido propaga el error y la próxima ola reintenta', () => {
    let failure: unknown;
    service.refreshOnce().subscribe({ error: (error) => (failure = error) });
    httpMock.expectOne('/api/auth/refresh/').flush(ENVELOPE_401, { status: 401, statusText: 'Unauthorized' });
    expect(failure).toBeDefined();

    // La ola siguiente arranca de cero: hay una nueva petición.
    let secondFailure: unknown;
    service.refreshOnce().subscribe({ error: (error) => (secondFailure = error) });
    httpMock.expectOne('/api/auth/refresh/').flush(ENVELOPE_401, { status: 401, statusText: 'Unauthorized' });
    expect(secondFailure).toBeDefined();
  });

  it('restoreSession reconstruye la sesión desde la cookie', () => {
    let restored = false;
    service.restoreSession().subscribe((result) => (restored = result));

    httpMock.expectOne('/api/auth/refresh/').flush(SESSION);
    expect(restored).toBe(true);
    expect(store.isAuthenticated()).toBe(true);
  });

  it('restoreSession devuelve false y queda anónimo cuando la cookie no sirve', () => {
    let restored = true;
    service.restoreSession().subscribe((result) => (restored = result));

    httpMock.expectOne('/api/auth/refresh/').flush(ENVELOPE_401, { status: 401, statusText: 'Unauthorized' });

    expect(restored).toBe(false);
    expect(store.status()).toBe('anonymous');
    expect(store.isAuthenticated()).toBe(false);
  });

  it('logout limpia la sesión local', () => {
    service.login('INST-0001', 'secreto-123').subscribe();
    httpMock.expectOne('/api/auth/login/').flush(SESSION);
    expect(store.isAuthenticated()).toBe(true);

    service.logout().subscribe();
    const request = httpMock.expectOne('/api/auth/logout/');
    expect(request.request.withCredentials).toBe(true);
    request.flush(null, { status: 204, statusText: 'No Content' });

    expect(store.isAuthenticated()).toBe(false);
    expect(localStorage.length).toBe(0);
  });

  it('handleSessionExpired limpia la sesión y redirige a login con returnUrl', async () => {
    store.setSession({ user: SESSION.user, roles: ['AUTHOR'], access: 'access-1' });
    await router.navigateByUrl('/panel');
    expect(store.isAuthenticated()).toBe(true);

    const navigationDone = firstValueFrom(
      router.events.pipe(filter((event): event is NavigationEnd => event instanceof NavigationEnd)),
    );
    service.handleSessionExpired();
    await navigationDone;

    expect(store.isAuthenticated()).toBe(false);
    expect(router.url).toBe('/login?returnUrl=%2Fpanel');
  });
});
