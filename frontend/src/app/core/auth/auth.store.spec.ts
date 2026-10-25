import { TestBed } from '@angular/core/testing';

import { AuthStatus } from './auth.store';
import { AuthStore } from './auth.store';
import { SessionUser } from '../models/session-user.model';

const USER: SessionUser = {
  id: '9cfbf22d-ccbd-439f-96bc-c3af48c942da',
  institutional_id: 'INST-0001',
  username: 'a.lopez',
  email: 'a.lopez@unl.edu.ec',
  first_name: 'Ana',
  last_name: 'López',
  full_name: 'Ana López',
};

describe('AuthStore', () => {
  let store: AuthStore;

  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    TestBed.configureTestingModule({});
    store = TestBed.inject(AuthStore);
  });

  it('arranca anónimo', () => {
    expect(store.user()).toBeNull();
    expect(store.roles()).toEqual([]);
    expect(store.accessToken()).toBeNull();
    expect(store.status()).toBe<AuthStatus>('anonymous');
    expect(store.isAuthenticated()).toBe(false);
  });

  it('setSession guarda identidad, roles y access token en memoria', () => {
    store.setSession({ user: USER, roles: ['AUTHOR', 'EDITOR'], access: 'access-1' });

    expect(store.user()?.full_name).toBe('Ana López');
    expect(store.roles()).toEqual(['AUTHOR', 'EDITOR']);
    expect(store.accessToken()).toBe('access-1');
    expect(store.status()).toBe<AuthStatus>('authenticated');
    expect(store.isAuthenticated()).toBe(true);
    // El access token y los roles NUNCA llegan al almacenamiento del navegador.
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
  });

  it('markRefreshing conserva la sesión mientras el refresh está en vuelo', () => {
    store.setSession({ user: USER, roles: ['EDITOR'], access: 'access-1' });
    store.markRefreshing();

    expect(store.status()).toBe<AuthStatus>('refreshing');
    // La interfaz no parpadea: sigue habiendo sesión utilizable.
    expect(store.isAuthenticated()).toBe(true);
    expect(store.accessToken()).toBe('access-1');
  });

  it('clear limpia la sesión completa', () => {
    store.setSession({ user: USER, roles: ['ADMIN'], access: 'access-1' });
    store.clear();

    expect(store.user()).toBeNull();
    expect(store.roles()).toEqual([]);
    expect(store.accessToken()).toBeNull();
    expect(store.status()).toBe<AuthStatus>('anonymous');
    expect(localStorage.length).toBe(0);
  });

  it('conserva la API de roles del andamiaje (setRoles/hasAnyRole)', () => {
    store.setRoles(['REVIEWER']);

    expect(store.hasAnyRole(['REVIEWER'])).toBe(true);
    expect(store.hasAnyRole(['AUTHOR', 'EDITOR'])).toBe(false);

    store.clearRoles();
    expect(store.hasAnyRole(['REVIEWER'])).toBe(false);
  });
});
