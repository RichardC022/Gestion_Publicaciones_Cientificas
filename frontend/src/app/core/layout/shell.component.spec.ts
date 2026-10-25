import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { ShellComponent } from './shell.component';

describe('ShellComponent', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [ShellComponent],
      providers: [provideRouter([])],
    });
  });

  const render = async () => {
    const fixture = TestBed.createComponent(ShellComponent);
    fixture.componentRef.setInput('userName', 'Ana Pérez');
    fixture.componentRef.setInput('roles', ['AUTHOR', 'EDITOR']);
    fixture.componentRef.setInput('unreadCount', 3);
    await fixture.whenStable();
    return fixture;
  };

  it('muestra el nombre y los roles activos como insignias informativas', async () => {
    const fixture = await render();
    const element = fixture.nativeElement as HTMLElement;
    expect(element.textContent).toContain('Ana Pérez');
    expect(element.textContent).toContain('Autor');
    expect(element.textContent).toContain('Editor');
  });

  it('no existe selector ni conmutador de rol', async () => {
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

  it('muestra el contador de avisos con etiqueta accesible', async () => {
    const fixture = await render();
    const element = fixture.nativeElement as HTMLElement;
    const bell = element.querySelector<HTMLButtonElement>('app-notification-bell button');
    expect(bell?.getAttribute('aria-label')).toBe('Avisos: 3 sin leer');
  });

  it('emite logout al pulsar Cerrar sesión', async () => {
    const fixture = await render();
    let loggedOut = false;
    fixture.componentInstance.logout.subscribe(() => {
      loggedOut = true;
    });

    const element = fixture.nativeElement as HTMLElement;
    const buttons = Array.from(element.querySelectorAll<HTMLButtonElement>('button'));
    const logoutButton = buttons.find((button) =>
      button.textContent?.includes('Cerrar sesión'),
    );
    logoutButton?.click();
    await fixture.whenStable();

    expect(loggedOut).toBe(true);
  });

  it('incluye el enlace de salto al contenido y los módulos por rol', async () => {
    const fixture = await render();
    const element = fixture.nativeElement as HTMLElement;
    expect(element.querySelector('.skip-link')?.textContent).toContain(
      'Saltar al contenido principal',
    );
    // Navegación de todos los roles activos, sin apartados de roles inexistentes.
    expect(element.textContent).toContain('Mis manuscritos');
    expect(element.textContent).toContain('Nuevos envíos');
    expect(element.textContent).not.toContain('Auditoría');
  });
});
