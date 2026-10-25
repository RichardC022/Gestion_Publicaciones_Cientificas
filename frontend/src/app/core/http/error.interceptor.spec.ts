import {
  HttpClient,
  HttpHeaders,
  provideHttpClient,
  withInterceptors,
} from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { NavigationEnd, Router } from '@angular/router';
import { provideRouter } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { filter } from 'rxjs/operators';

import { authInterceptor } from '../auth/auth.interceptor';
import { AuthStore } from '../auth/auth.store';
import { ApiError } from '../models/api-error.model';
import { LoginResponse, SessionUser } from '../models/session-user.model';
import { API_BASE_URL } from './api-base-url.token';
import { requestIdInterceptor } from './request-id.interceptor';
import { ApiFeedbackStore } from './api-feedback.store';
import { errorInterceptor } from './error.interceptor';

@Component({ template: '' })
class DummyComponent {}

const USER: SessionUser = {
  id: 'uuid-1',
  institutional_id: 'INST-0001',
  username: 'a.lopez',
  email: 'a.lopez@unl.edu.ec',
  first_name: 'Ana',
  last_name: 'López',
  full_name: 'Ana López',
};

const SESSION: LoginResponse = { access: 'access-nuevo', user: USER, roles: ['AUTHOR'] };

const envelope = (code: string, message: string) => ({
  error: { code, message, details: {}, request_id: 'rid-9' },
});

describe('errorInterceptor', () => {
  let client: HttpClient;
  let store: AuthStore;
  let feedback: ApiFeedbackStore;
  let httpMock: HttpTestingController;
  let router: Router;

  beforeEach(() => {
    localStorage.clear();
    TestBed.configureTestingModule({
      providers: [
        provideRouter([
          { path: 'login', component: DummyComponent },
          { path: 'panel', component: DummyComponent },
        ]),
        provideHttpClient(
          withInterceptors([requestIdInterceptor, authInterceptor, errorInterceptor]),
        ),
        provideHttpClientTesting(),
        { provide: API_BASE_URL, useValue: '/api/' },
      ],
    });
    client = TestBed.inject(HttpClient);
    store = TestBed.inject(AuthStore);
    feedback = TestBed.inject(ApiFeedbackStore);
    httpMock = TestBed.inject(HttpTestingController);
    router = TestBed.inject(Router);
  });

  afterEach(() => {
    httpMock.verify();
  });

  const awaitNavigation = () =>
    firstValueFrom(
      router.events.pipe(filter((event): event is NavigationEnd => event instanceof NavigationEnd)),
    );

  it('un 401 refresca una sola vez y reintenta con el token nuevo', () => {
    store.setSession({ user: USER, roles: ['AUTHOR'], access: 'access-viejo' });
    let result: unknown;
    client.get('/api/manuscripts/').subscribe((response) => (result = response));

    // Primer intento: expirado.
    httpMock
      .expectOne('/api/manuscripts/')
      .flush(envelope('AUTH_INVALID', 'Credenciales inválidas.'), {
        status: 401,
        statusText: 'Unauthorized',
      });

    // Un único refresh, compartido por la ola de 401.
    const refresh = httpMock.expectOne('/api/auth/refresh/');
    expect(refresh.request.headers.get('Authorization')).toBeNull();
    refresh.flush(SESSION);

    // Reintento con el token renovado.
    const retried = httpMock.expectOne('/api/manuscripts/');
    expect(retried.request.headers.get('Authorization')).toBe('Bearer access-nuevo');
    retried.flush({ ok: true });

    expect(result).toEqual({ ok: true });
    expect(feedback.feedback()).toBeNull();
  });

  it('una ola de 401 concurrentes comparte el mismo refresh', () => {
    store.setSession({ user: USER, roles: ['AUTHOR'], access: 'access-viejo' });
    let first: unknown;
    let second: unknown;
    client.get('/api/manuscripts/a/').subscribe((value) => (first = value));
    client.get('/api/manuscripts/b/').subscribe((value) => (second = value));

    httpMock
      .expectOne('/api/manuscripts/a/')
      .flush(envelope('AUTH_INVALID', 'Credenciales inválidas.'), { status: 401, statusText: 'Unauthorized' });
    httpMock
      .expectOne('/api/manuscripts/b/')
      .flush(envelope('AUTH_INVALID', 'Credenciales inválidas.'), { status: 401, statusText: 'Unauthorized' });

    const refresh = httpMock.expectOne('/api/auth/refresh/');
    refresh.flush(SESSION);

    httpMock.expectOne('/api/manuscripts/a/').flush('a');
    httpMock.expectOne('/api/manuscripts/b/').flush('b');

    expect(first).toBe('a');
    expect(second).toBe('b');
    // Solo existió una petición de refresh para toda la ola.
    httpMock.verify();
  });

  it('refresh fallido: limpia la sesión y redirige a /login', async () => {
    store.setSession({ user: USER, roles: ['AUTHOR'], access: 'access-viejo' });
    await router.navigateByUrl('/panel');

    let failure: { status: number } | undefined;
    client.get('/api/manuscripts/').subscribe({ error: (error) => (failure = error) });
    httpMock
      .expectOne('/api/manuscripts/')
      .flush(envelope('AUTH_INVALID', 'Credenciales inválidas.'), {
        status: 401,
        statusText: 'Unauthorized',
      });
    httpMock
      .expectOne('/api/auth/refresh/')
      .flush(envelope('AUTH_INVALID', 'Credenciales inválidas.'), {
        status: 401,
        statusText: 'Unauthorized',
      });

    expect(failure?.status).toBe(401);
    expect(store.isAuthenticated()).toBe(false);
    await awaitNavigation();
    expect(router.url).toBe('/login?returnUrl=%2Fpanel');
  });

  it('el 401 del propio login no dispara refresh', () => {
    let failure: { code: string } | undefined;
    client.post('/api/auth/login/', {}).subscribe({ error: (error) => (failure = error) });

    httpMock
      .expectOne('/api/auth/login/')
      .flush(envelope('AUTH_INVALID', 'Credenciales institucionales inválidas.'), {
        status: 401,
        statusText: 'Unauthorized',
      });

    expect(failure?.code).toBe('AUTH_INVALID');
    // Ni refresh ni ninguna otra petición.
    httpMock.verify();
    expect(store.isAuthenticated()).toBe(false);
  });

  it('429 publica un aviso accionable que respeta Retry-After', () => {
    let failure: { retryAfterSeconds: number | null } | undefined;
    client.get('/api/manuscripts/').subscribe({ error: (error) => (failure = error) });

    httpMock
      .expectOne('/api/manuscripts/')
      .flush(envelope('AUTH_LOCKED', 'Demasiados intentos fallidos. Intente de nuevo en unos minutos.'), {
        status: 429,
        statusText: 'Too Many Requests',
        headers: new HttpHeaders({ 'Retry-After': '120' }),
      });

    expect(failure?.retryAfterSeconds).toBe(120);
    const message = feedback.feedback();
    expect(message?.kind).toBe('warning');
    expect(message?.retryAfterSeconds).toBe(120);
    // El mensaje accionable incluye la espera exigida por el backend.
    expect(message?.message).toContain('120 segundos');
  });

  it('409 publica el conflicto de estado como aviso accionable', () => {
    client.get('/api/manuscripts/').subscribe({ error: () => undefined });

    httpMock
      .expectOne('/api/manuscripts/')
      .flush(envelope('STATE_CONFLICT', 'La acción no es válida en el estado actual.'), {
        status: 409,
        statusText: 'Conflict',
      });

    const message = feedback.feedback();
    expect(message?.kind).toBe('error');
    expect(message?.status).toBe(409);
    expect(message?.message).toContain('estado actual');
  });

  it('413 y 503 publican mensajes accionables específicos', () => {
    client.get('/api/manuscripts/1/draft-file/').subscribe({ error: () => undefined });
    httpMock
      .expectOne('/api/manuscripts/1/draft-file/')
      .flush(envelope('PDF_TOO_LARGE', 'El archivo supera el límite de 50 MB.'), {
        status: 413,
        statusText: 'Payload Too Large',
      });
    expect(feedback.feedback()?.message).toContain('50 MB');

    feedback.dismiss();

    client.get('/api/dashboard/').subscribe({ error: () => undefined });
    httpMock
      .expectOne('/api/dashboard/')
      .flush(envelope('AUDIT_UNAVAILABLE', 'No se pudo registrar la auditoría.'), {
        status: 503,
        statusText: 'Service Unavailable',
      });
    expect(feedback.feedback()?.status).toBe(503);
    expect(feedback.feedback()?.message).toContain('no disponible');
  });

  it('403 publica acceso denegado y conserva el request_id', () => {
    client.get('/api/manuscripts/').subscribe({ error: () => undefined });

    httpMock
      .expectOne('/api/manuscripts/')
      .flush(envelope('FORBIDDEN', 'Acceso denegado.'), { status: 403, statusText: 'Forbidden' });

    const message = feedback.feedback();
    expect(message?.status).toBe(403);
    expect(message?.message).toContain('Acceso denegado');
    expect(message?.requestId).toBe('rid-9');
  });

  it('toda petición de API sale con X-Request-ID válido', () => {
    client.get('/api/manuscripts/').subscribe({ error: () => undefined });
    const request = httpMock.expectOne('/api/manuscripts/');
    const requestId = request.request.headers.get('X-Request-ID');
    expect(requestId).toMatch(/^[A-Za-z0-9@._~-]{1,64}$/);
    request.flush(envelope('NOT_FOUND', 'No encontrado.'), { status: 404, statusText: 'Not Found' });
  });

  it('un 401 del login llega al componente con el mensaje del envelope (regresión TSK-26)', () => {
    let failure: ApiError | undefined;
    client.post('/api/auth/login/', {}).subscribe({ error: (error) => (failure = error) });

    httpMock
      .expectOne('/api/auth/login/')
      .flush(envelope('AUTH_INVALID', 'Credenciales institucionales inválidas.'), {
        status: 401,
        statusText: 'Unauthorized',
      });

    // Con la cadena real de interceptores el mensaje genérico del
    // backend sobrevive a la doble normalización: nunca aparece la
    // "falla de conexión".
    expect(failure?.status).toBe(401);
    expect(failure?.message).toBe('Credenciales institucionales inválidas.');
    expect(failure?.userMessage).not.toContain('conectar con el servidor');
  });

  it('una URL relativa de la API sale al backend con slash absoluto (regresión TSK-26)', () => {
    client.post('api/auth/refresh/', {}).subscribe({ error: () => undefined });

    // El interceptor más externo la normaliza ANTES de que el navegador
    // la resuelva contra la ruta del documento (`/catalog` ->
    // `/catalogapi/auth/refresh`).
    const request = httpMock.expectOne('/api/auth/refresh/');
    expect(request.request.headers.get('X-Request-ID')).toMatch(/^[A-Za-z0-9@._~-]{1,64}$/);
    request.flush(envelope('AUTH_INVALID', 'Credenciales inválidas.'), {
      status: 401,
      statusText: 'Unauthorized',
    });
  });
});
