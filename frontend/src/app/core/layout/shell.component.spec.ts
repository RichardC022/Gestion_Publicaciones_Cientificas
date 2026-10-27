import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { NavigationEnd, Router } from '@angular/router';
import { provideRouter } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { filter } from 'rxjs/operators';

import { AuthService } from '../auth/auth.service';
import { AuthStore } from '../auth/auth.store';
import { API_BASE_URL } from '../http/api-base-url.token';
import { ApiFeedbackStore } from '../http/api-feedback.store';
import { ShellComponent } from './shell.component';

describe('ShellComponent', () => {
  let store: AuthStore;
  let feedback: ApiFeedbackStore;
  let httpMock: HttpTestingController;

  beforeEach(async () => {
    TestBed.configureTestingModule({
      providers: [
        provideRouter([
          { path: 'login', loadChildren: () => [] },
          { path: 'app/notifications', loadChildren: () => [] },
        ]),
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: API_BASE_URL, useValue: '/api/' },
      ],
    });
    store = TestBed.inject(AuthStore);
    feedback = TestBed.inject(ApiFeedbackStore);
    httpMock = TestBed.inject(HttpTestingController);
  });

  const render = async () => {
    const fixture = TestBed.createComponent(ShellComponent);
    await fixture.whenStable();
    return fixture;
  };

  const setSession = () =>
    store.setSession({
      user: {
        id: 'uuid-1',
        institutional_id: 'INST-0001',
        username: 'a.lopez',
        email: 'a.lopez@unl.edu.ec',
        first_name: 'Ana',
        last_name: 'López',
        full_name: 'Ana López',
      },
      roles: ['AUTHOR', 'EDITOR'],
      access: 'access-1',
    });

  it('muestra el nombre y los roles activos como insignias informativas', async () => {
    setSession();
    const fixture = await render();
    const element = fixture.nativeElement as HTMLElement;

    expect(element.textContent).toContain('Ana López');
    expect(element.textContent).toContain('Autor');
    expect(element.textContent).toContain('Editor');
  });

  it('no existe selector ni conmutador de rol', async () => {
    setSession();
    const fixture = await render();
    const element = fixture.nativeElement as HTMLElement;
    expect(element.querySelector('select')).toBeNull();
    expect(element.querySelector('[role="listbox"]')).toBeNull();
    const badges = element.querySelectorAll<HTMLElement>('.app-header__roles .badge');
    expect(badges.length).toBe(2);
    badges.forEach((badge) => {
      expect(badge.tagName).toBe('SPAN');
      expect(badge.querySelector('button, a, input')).toBeNull();
    });
  });

  it('la navegación muestra los módulos de todos los roles activos', async () => {
    setSession();
    const fixture = await render();
    const element = fixture.nativeElement as HTMLElement;

    expect(element.textContent).toContain('Mis manuscritos');
    expect(element.textContent).toContain('Nuevos envíos');
    // Sin apartados de roles inexistentes.
    expect(element.textContent).not.toContain('Mis asignaciones');
    expect(element.textContent).not.toContain('Auditoría');
  });

  it('con roles retirados los módulos desaparecen en la misma sesión', async () => {
    setSession();
    const fixture = await render();
    const element = () => fixture.nativeElement as HTMLElement;

    store.setSession({
      user: {
        id: 'uuid-1',
        institutional_id: 'INST-0001',
        username: 'a.lopez',
        email: 'a.lopez@unl.edu.ec',
        first_name: 'Ana',
        last_name: 'López',
        full_name: 'Ana López',
      },
      roles: ['EDITOR'],
      access: 'access-1',
    });
    await fixture.whenStable();
    expect(element().textContent).not.toContain('Mis manuscritos');
    expect(element().textContent).toContain('Nuevos envíos');
  });

  it('muestra la campana con etiqueta accesible y abre los avisos', async () => {
    setSession();
    const fixture = await render();
    const element = fixture.nativeElement as HTMLElement;
    const router = TestBed.inject(Router);

    const bell = element.querySelector<HTMLButtonElement>('app-notification-bell button');
    expect(bell?.getAttribute('aria-label')).toContain('Avisos');
    bell?.click();
    await fixture.whenStable();

    expect(router.url).toContain('/app/notifications');
  });

  it('el cierre de sesión revoca el refresh y vuelve al login', async () => {
    setSession();
    const fixture = await render();
    const element = fixture.nativeElement as HTMLElement;
    const router = TestBed.inject(Router);

    const navigationDone = firstValueFrom(
      router.events.pipe(filter((event): event is NavigationEnd => event instanceof NavigationEnd)),
    );
    const buttons = Array.from(element.querySelectorAll<HTMLButtonElement>('button'));
    buttons.find((button) => button.textContent?.includes('Cerrar sesión'))?.click();

    httpMock.expectOne('/api/auth/logout/').flush(null, {
      status: 204,
      statusText: 'No Content',
    });
    await navigationDone;

    expect(store.isAuthenticated()).toBe(false);
    expect(router.url).toBe('/login');
  });

  it('renderiza el mensaje accionable de la API y permite cerrarlo', async () => {
    const fixture = await render();
    const element = () => fixture.nativeElement as HTMLElement;

    feedback.show({
      status: 429,
      code: 'AUTH_LOCKED',
      message: 'Demasiados intentos fallidos. Intente de nuevo en unos minutos.',
      userMessage: 'Espere 120 segundos e intente de nuevo.',
      details: {},
      requestId: 'rid-9',
      retryAfterSeconds: 120,
    });
    await fixture.whenStable();

    expect(element().querySelector('.app-feedback--warning')).not.toBeNull();
    expect(element().textContent).toContain('120 segundos');

    element()
      .querySelector<HTMLButtonElement>('.app-feedback__dismiss')
      ?.click();
    await fixture.whenStable();
    expect(element().querySelector('.app-feedback')).toBeNull();
  });
});
