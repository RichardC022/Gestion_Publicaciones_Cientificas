import { Component, inject, signal } from '@angular/core';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';

import { AuthService } from '../../../core/auth/auth.service';
import { ApiError } from '../../../core/models/api-error.model';

/**
 * Pantalla pública de acceso institucional (plan sección 3.5).
 *
 * * Credenciales institucionales (id, usuario o correo + contraseña).
 * * Todo fallo muestra el mensaje genérico del envelope del backend
 *   ("Credenciales institucionales inválidas.", bloqueo temporal…):
 *   nunca revela si la cuenta existe ni por qué falló.
 * * Tras entrar redirige a `returnUrl` cuando es una ruta interna
 *   segura; al panel unificado en caso contrario. El panel muestra
 *   los módulos de todos los roles activos: aquí no existe ninguna
 *   pantalla de selección de rol.
 */
@Component({
  selector: 'app-login',
  imports: [ReactiveFormsModule, RouterLink],
  template: `
    <main class="login">
      <section class="login__card" aria-labelledby="login-title">
        <h1 id="login-title">Iniciar sesión</h1>
        <p class="login__hint">
          Use sus credenciales institucionales para acceder al sistema.
        </p>

        <form [formGroup]="form" (ngSubmit)="submit()" novalidate>
          <div class="login__field">
            <label for="identifier">Identificador institucional</label>
            <input
              id="identifier"
              type="text"
              formControlName="identifier"
              autocomplete="username"
              [attr.aria-invalid]="form.controls.identifier.invalid && form.controls.identifier.touched"
            />
            @if (form.controls.identifier.invalid && form.controls.identifier.touched) {
              <p class="login__error" role="alert">
                Escriba su identificador institucional.
              </p>
            }
          </div>

          <div class="login__field">
            <label for="password">Contraseña</label>
            <input
              id="password"
              type="password"
              formControlName="password"
              autocomplete="current-password"
              [attr.aria-invalid]="form.controls.password.invalid && form.controls.password.touched"
            />
            @if (form.controls.password.invalid && form.controls.password.touched) {
              <p class="login__error" role="alert">
                Escriba su contraseña.
              </p>
            }
          </div>

          <!-- Mensaje genérico: nunca revela si la cuenta existe. -->
          <p
            class="login__error login__error--global"
            role="alert"
            aria-live="polite"
          >
            {{ errorMessage() }}
          </p>

          <button
            type="submit"
            class="btn btn--primary login__submit"
            [disabled]="submitting()"
          >
            {{ submitting() ? 'Ingresando…' : 'Ingresar' }}
          </button>
        </form>

        <p class="login__catalog">
          ¿Solo quiere consultar? <a routerLink="/catalog">Visite el catálogo público</a>
        </p>
      </section>
    </main>
  `,
  styles: `
    .login {
      display: grid;
      place-items: center;
      min-height: 70dvh;
      padding: 1.5rem;
    }
    .login__card {
      width: min(24rem, 100%);
      padding: 2rem;
      background: var(--gpc-surface);
      border: 1px solid var(--gpc-border);
      border-radius: var(--gpc-radius-lg);
      box-shadow: 0 8px 24px rgb(15 23 42 / 0.08);
    }
    .login__hint {
      margin: 0 0 1.5rem;
      color: var(--gpc-text-muted);
    }
    .login__field {
      display: flex;
      flex-direction: column;
      gap: 0.375rem;
      margin-bottom: 1rem;
    }
    .login__field label {
      font-weight: 600;
      font-size: 0.9rem;
    }
    .login__field input {
      padding: 0.625rem 0.75rem;
      border: 1px solid var(--gpc-border);
      border-radius: var(--gpc-radius);
      font: inherit;
    }
    .login__field input[aria-invalid='true'] {
      border-color: var(--gpc-danger-700);
    }
    .login__error {
      margin: 0 0 0.75rem;
      color: var(--gpc-danger-700);
      font-size: 0.875rem;
    }
    .login__error--global:empty {
      display: none;
    }
    .login__submit {
      width: 100%;
      padding: 0.75rem;
      font-weight: 700;
    }
    .login__catalog {
      margin: 1.25rem 0 0;
      font-size: 0.875rem;
      color: var(--gpc-text-muted);
    }
  `,
})
export class LoginComponent {
  private readonly formBuilder = inject(NonNullableFormBuilder);
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);

  /** Mensaje genérico del envelope; vacío cuando no hay fallo. */
  readonly errorMessage = signal('');
  readonly submitting = signal(false);

  readonly form = this.formBuilder.group({
    identifier: ['', [Validators.required]],
    password: ['', [Validators.required]],
  });

  submit(): void {
    if (this.form.invalid || this.submitting()) {
      this.form.markAllAsTouched();
      return;
    }

    const { identifier, password } = this.form.getRawValue();
    this.errorMessage.set('');
    this.submitting.set(true);

    this.auth.login(identifier.trim(), password).subscribe({
      complete: () => {
        this.submitting.set(false);
        void this.router.navigateByUrl(this.returnUrl());
      },
      error: (error: unknown) => {
        this.submitting.set(false);
        this.errorMessage.set(toLoginMessage(error));
      },
    });
  }

  /**
   * `returnUrl` solo se respeta si es una ruta interna segura del
   * propio origen (empieza por `/` y no por `//`); cualquier otra
   * cosa lleva al panel unificado.
   */
  private returnUrl(): string {
    const raw = this.route.snapshot.queryParamMap.get('returnUrl') ?? '';
    const isSafeInternal = raw.startsWith('/') && !raw.startsWith('//');
    return isSafeInternal ? raw : '/app/dashboard';
  }
}

/**
 * Mensaje genérico del login (plan sección 6.1): el envelope del
 * backend ya trae el texto neutro ("Credenciales institucionales
 * inválidas.", "Demasiados intentos fallidos…"); se usa tal cual y
 * solo se recurre al normalizado si el envelope llegó vacío.
 */
function toLoginMessage(error: unknown): string {
  const apiError = error as Partial<ApiError> | null;
  if (apiError?.message) {
    return apiError.message;
  }
  return apiError?.userMessage ?? 'No fue posible iniciar sesión. Intente de nuevo.';
}
