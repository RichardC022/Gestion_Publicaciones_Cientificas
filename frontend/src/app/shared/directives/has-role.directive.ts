import {
  Directive,
  TemplateRef,
  ViewContainerRef,
  computed,
  effect,
  inject,
  input,
} from '@angular/core';

import { AuthStore } from '../../core/auth/auth.store';
import { Role } from '../../core/models/role.model';

/**
 * Directiva estructural que renderiza su plantilla solo cuando la
 * sesión tiene al menos uno de los roles indicados.
 *
 * Uso:
 * `<button *appHasRole="['EDITOR']">…</button>`
 * `<nav *appHasRole="'ADMIN'">…</nav>`
 *
 * Es una ayuda de interfaz: el backend vuelve a validar cada acción.
 */
@Directive({ selector: '[appHasRole]' })
export class HasRoleDirective {
  private readonly templateRef = inject<TemplateRef<unknown>>(TemplateRef);
  private readonly viewContainer = inject(ViewContainerRef);
  private readonly authStore = inject(AuthStore);

  readonly appHasRole = input.required<Role | Role[]>();

  private readonly visible = computed(() => {
    const required = this.appHasRole();
    const roles = Array.isArray(required) ? required : [required];
    return this.authStore.hasAnyRole(roles);
  });

  constructor() {
    effect(() => {
      if (this.visible()) {
        this.viewContainer.createEmbeddedView(this.templateRef);
      } else {
        this.viewContainer.clear();
      }
    });
  }
}
