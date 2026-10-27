import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { authInterceptor } from './auth.interceptor';
import { AuthStore } from './auth.store';
import { SessionUser } from '../models/session-user.model';

const USER: SessionUser = {
  id: 'uuid-1',
  institutional_id: 'INST-0001',
  username: 'a.lopez',
  email: 'a.lopez@unl.edu.ec',
  first_name: 'Ana',
  last_name: 'López',
  full_name: 'Ana López',
};

/**
 * El interceptor añade `Authorization: Bearer` solo a los endpoints
 * protegidos; login, refresh y catálogo público jamás lo llevan
 * (plan sección 3.7).
 */
describe('authInterceptor', () => {
  let store: AuthStore;
  let httpMock: HttpTestingController;
  let client: HttpClient;

  const getTokenOf = (url: string): string | null => {
    client.get(url).subscribe();
    return httpMock.expectOne(url).request.headers.get('Authorization');
  };

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(withInterceptors([authInterceptor])),
        provideHttpClientTesting(),
      ],
    });
    store = TestBed.inject(AuthStore);
    httpMock = TestBed.inject(HttpTestingController);
    client = TestBed.inject(HttpClient);
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('añade el bearer a un endpoint protegido', () => {
    store.setSession({ user: USER, roles: ['AUTHOR'], access: 'token-vigente' });
    expect(getTokenOf('/api/manuscripts/')).toBe('Bearer token-vigente');
  });

  it('sin sesión no añade cabecera', () => {
    expect(getTokenOf('/api/manuscripts/')).toBeNull();
  });

  it('login, refresh y catálogo público nunca llevan bearer', () => {
    store.setSession({ user: USER, roles: ['AUTHOR'], access: 'token-vigente' });

    const publicUrls = ['/api/auth/login/', '/api/auth/refresh/', '/api/catalog/'];
    for (const url of publicUrls) {
      client.post(url, {}).subscribe();
      expect(httpMock.expectOne(url).request.headers.get('Authorization')).toBeNull();
    }
  });

  it('no toca peticiones fuera de la API', () => {
    store.setSession({ user: USER, roles: ['AUTHOR'], access: 'token-vigente' });
    client.get('/assets/config.json').subscribe();
    const request = httpMock.expectOne('/assets/config.json');
    expect(request.request.headers.get('Authorization')).toBeNull();
  });
});
