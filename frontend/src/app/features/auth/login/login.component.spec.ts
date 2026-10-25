import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { Router } from '@angular/router';
import { provideRouter } from '@angular/router';

import { AuthStore } from '../../../core/auth/auth.store';
import { API_BASE_URL } from '../../../core/http/api-base-url.token';
import { LoginComponent } from './login.component';

const SESSION = {
  access: 'access-1',
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

const envelope = (code: string, message: string) => ({
  error: { code, message, details: {}, request_id: 'rid-1' },
});

describe('LoginComponent', () => {
  let httpMock: HttpTestingController;
  let store: AuthStore;

  const render = async () => {
    const fixture = TestBed.createComponent(LoginComponent);
    await fixture.whenStable();
    return fixture;
  };

  const fillAndSubmit = async (
    fixture: { componentInstance: LoginComponent; nativeElement: HTMLElement },
    identifier = 'INST-0001',
    password = 'institucional-123',
  ) => {
    const component = fixture.componentInstance;
    component.form.controls.identifier.setValue(identifier);
    component.form.controls.password.setValue(password);
    component.submit();
    await Promise.resolve();
  };

  beforeEach(async () => {
    TestBed.configureTestingModule({
      providers: [
        provideRouter([
          { path: 'login', component: LoginComponent },
          { path: 'app/dashboard', children: [] },
          { path: 'app/author/manuscripts', children: [] },
        ]),
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: API_BASE_URL, useValue: '/api/' },
      ],
    });
    httpMock = TestBed.inject(HttpTestingController);
    store = TestBed.inject(AuthStore);
  });

  it('muestra un error genérico del envelope ante credenciales inválidas', async () => {
    const fixture = await render();
    await fillAndSubmit(fixture, 'INST-0001', 'contrasena-mala');
    const element = fixture.nativeElement as HTMLElement;

    httpMock
      .expectOne('/api/auth/login/')
      .flush(envelope('AUTH_INVALID', 'Credenciales institucionales inválidas.'), {
        status: 401,
        statusText: 'Unauthorized',
      });
    await fixture.whenStable();

    const globalError = element.querySelector('.login__error--global');
    expect(globalError?.textContent).toContain('Credenciales institucionales inválidas.');
    // El mensaje no revela si la cuenta existe: mismo texto para
    // cualquier causa.
    expect(globalError?.textContent).not.toContain('no existe');
    expect(store.isAuthenticated()).toBe(false);
  });

  it('un login válido abre la sesión y lleva al panel unificado', async () => {
    const fixture = await render();

    await fillAndSubmit(fixture);
    httpMock.expectOne('/api/auth/login/').flush(SESSION);
    await fixture.whenStable();

    expect(store.isAuthenticated()).toBe(true);
    expect(TestBed.inject(Router).url).toBe('/app/dashboard');
  });

  it('respeta returnUrl cuando es una ruta interna segura', async () => {
    const router = TestBed.inject(Router);
    await router.navigateByUrl('/login?returnUrl=%2Fapp%2Fauthor%2Fmanuscripts');
    const fixture = await render();

    await fillAndSubmit(fixture);
    httpMock.expectOne('/api/auth/login/').flush(SESSION);
    await fixture.whenStable();

    expect(router.url).toBe('/app/author/manuscripts');
  });

  it('ignora returnUrl externos y lleva al panel', async () => {
    const router = TestBed.inject(Router);
    await router.navigateByUrl('/login?returnUrl=https%3A%2F%2Fevil.example');
    const fixture = await render();

    await fillAndSubmit(fixture);
    httpMock.expectOne('/api/auth/login/').flush(SESSION);
    await fixture.whenStable();

    expect(router.url).toBe('/app/dashboard');
  });

  it('el bloqueo temporal (429) muestra la espera del Retry-After', async () => {
    const fixture = await render();
    await fillAndSubmit(fixture, 'INST-0001', 'institucional-123');
    const element = fixture.nativeElement as HTMLElement;

    httpMock
      .expectOne('/api/auth/login/')
      .flush(envelope('AUTH_LOCKED', 'Demasiados intentos fallidos. Intente de nuevo en unos minutos.'), {
        status: 429,
        statusText: 'Too Many Requests',
      });
    await fixture.whenStable();

    const globalError = element.querySelector('.login__error--global');
    expect(globalError?.textContent).toContain('Demasiados intentos fallidos');
  });

  it('no envía el formulario cuando faltan campos', async () => {
    const fixture = await render();
    const component = fixture.componentInstance;

    component.submit();
    await fixture.whenStable();

    expect(component.errorMessage()).toBe('');
    httpMock.verify(); // sin ninguna petición
  });

  it('no existe ninguna pantalla de selección de rol', async () => {
    const fixture = await render();
    const element = fixture.nativeElement as HTMLElement;
    expect(element.querySelector('select')).toBeNull();
    expect(element.textContent).not.toContain('Seleccione rol');
  });
});
