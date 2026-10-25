import { Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';

import { AuthStore } from '../../core/auth/auth.store';
import { HasRoleDirective } from './has-role.directive';

@Component({
  imports: [HasRoleDirective],
  template: `<p *appHasRole="['EDITOR']">Acceso editorial</p>`,
})
class DirectiveHostComponent {}

describe('HasRoleDirective', () => {
  const render = async () => {
    const fixture = TestBed.createComponent(DirectiveHostComponent);
    await fixture.whenStable();
    return fixture;
  };

  it('oculta el contenido cuando la sesión no tiene el rol requerido', async () => {
    const fixture = await render();
    const store = TestBed.inject(AuthStore);
    const element = () => fixture.nativeElement as HTMLElement;

    store.setRoles(['AUTHOR']);
    await fixture.whenStable();
    expect(element().querySelector('p')).toBeNull();

    store.setRoles(['AUTHOR', 'EDITOR']);
    await fixture.whenStable();
    expect(element().querySelector('p')?.textContent).toContain('Acceso editorial');
  });

  it('vuelve a ocultar el contenido cuando el rol se retira', async () => {
    const fixture = await render();
    const store = TestBed.inject(AuthStore);
    const element = () => fixture.nativeElement as HTMLElement;

    store.setRoles(['EDITOR']);
    await fixture.whenStable();
    expect(element().querySelector('p')).not.toBeNull();

    store.setRoles([]);
    await fixture.whenStable();
    expect(element().querySelector('p')).toBeNull();
  });
});
