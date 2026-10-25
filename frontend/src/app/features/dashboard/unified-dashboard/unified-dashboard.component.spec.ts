import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { API_BASE_URL } from '../../../core/http/api-base-url.token';
import { DashboardResponse } from '../../../core/models/dashboard.model';
import { Role } from '../../../core/models/role.model';
import { UnifiedDashboardComponent } from './unified-dashboard.component';

const USER = {
  id: 'uuid-1',
  institutional_id: 'INST-0001',
  username: 'a.lopez',
  email: 'a.lopez@unl.edu.ec',
  first_name: 'Ana',
  last_name: 'López',
  full_name: 'Ana López',
};

const dashboardOf = (
  roles: Role[],
  sections: DashboardResponse['sections'],
): DashboardResponse => ({ user: USER, roles, sections });

const ok = (data: Record<string, unknown> = {}) => ({
  status: 'ok' as const,
  data,
  message: null,
});

const failed = (message: string) => ({
  status: 'error' as const,
  data: null,
  message,
});

describe('UnifiedDashboardComponent', () => {
  let httpMock: HttpTestingController;

  const render = async () => {
    const fixture = TestBed.createComponent(UnifiedDashboardComponent);
    await fixture.whenStable();
    return fixture;
  };

  const flush = (response: DashboardResponse) =>
    httpMock.expectOne('/api/dashboard/').flush(response);

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: API_BASE_URL, useValue: '/api/' },
      ],
    });
    httpMock = TestBed.inject(HttpTestingController);
  });

  it('consume el panel UNA sola vez y renderiza las secciones de todos los roles activos simultáneamente', async () => {
    const fixture = TestBed.createComponent(UnifiedDashboardComponent);
    await fixture.whenStable();

    flush(
      dashboardOf(['AUTHOR', 'REVIEWER', 'EDITOR', 'ADMIN'], {
        author: ok({ manuscripts: 3 }),
        reviewer: ok({ pending: 1 }),
        editor: ok({ new_submissions: 7 }),
        admin: ok({ audit_events: 42 }),
      }),
    );
    await fixture.whenStable();

    const element = fixture.nativeElement as HTMLElement;
    expect(element.querySelector('app-author-summary')).not.toBeNull();
    expect(element.querySelector('app-reviewer-summary')).not.toBeNull();
    expect(element.querySelector('app-editor-summary')).not.toBeNull();
    expect(element.querySelector('app-admin-summary')).not.toBeNull();
    expect(element.textContent).toContain('3');
    expect(element.textContent).toContain('42');
    // Una sola petición al backend por carga.
    httpMock.verify();
  });

  it('un solo rol ve únicamente su sección, sin apartados vacíos de roles inexistentes', async () => {
    const fixture = await render();
    flush(
      dashboardOf(['REVIEWER'], {
        reviewer: ok({ pending: 2 }),
      }),
    );
    await fixture.whenStable();

    const element = fixture.nativeElement as HTMLElement;
    expect(element.querySelector('app-reviewer-summary')).not.toBeNull();
    expect(element.querySelector('app-author-summary')).toBeNull();
    expect(element.querySelector('app-editor-summary')).toBeNull();
    expect(element.querySelector('app-admin-summary')).toBeNull();
  });

  it('el fallo de una sección no oculta las demás y ofrece Reintentar', async () => {
    const fixture = await render();
    flush(
      dashboardOf(['AUTHOR', 'EDITOR'], {
        author: ok({ manuscripts: 5 }),
        editor: failed('No se pudo cargar esta sección. Intente de nuevo.'),
      }),
    );
    await fixture.whenStable();

    const element = fixture.nativeElement as HTMLElement;
    // La sección sana sigue visible con sus datos.
    expect(element.querySelector('app-author-summary')).not.toBeNull();
    // La fallida muestra el aviso reintentable del backend.
    const editorSection = element.querySelector('[data-section="editor"]');
    expect(editorSection?.querySelector('app-error-state')).not.toBeNull();
    expect(editorSection?.textContent).toContain('Intente de nuevo');
    const retryButton = editorSection?.querySelector<HTMLButtonElement>('button');
    expect(retryButton?.textContent).toContain('Reintentar');

    // Reintentar: vuelve a llamar al panel una única vez y restaura.
    retryButton?.click();
    await fixture.whenStable();
    flush(
      dashboardOf(['AUTHOR', 'EDITOR'], {
        author: ok({ manuscripts: 5 }),
        editor: ok({ new_submissions: 1 }),
      }),
    );
    await fixture.whenStable();

    const restored = fixture.nativeElement as HTMLElement;
    const editorAfter = restored.querySelector('[data-section="editor"]');
    expect(editorAfter?.querySelector('app-editor-summary')).not.toBeNull();
    expect(editorAfter?.querySelector('app-error-state')).toBeNull();
    httpMock.verify();
  });

  it('una cuenta sin roles activos ve el mensaje explícito', async () => {
    const fixture = await render();
    flush(dashboardOf([], {}));
    await fixture.whenStable();

    const element = fixture.nativeElement as HTMLElement;
    expect(element.textContent).toContain('Sin roles habilitados');
    expect(element.querySelector('app-author-summary')).toBeNull();
  });

  it('un fallo global del panel muestra error con Reintentar', async () => {
    const fixture = await render();
    httpMock
      .expectOne('/api/dashboard/')
      .flush({ error: { code: 'SERVER_ERROR', message: 'Error interno.' } }, {
        status: 500,
        statusText: 'Server Error',
      });
    await fixture.whenStable();

    const element = fixture.nativeElement as HTMLElement;
    expect(element.querySelector('app-error-state')).not.toBeNull();
    expect(element.textContent).toContain('Error interno');

    element.querySelector<HTMLButtonElement>('app-error-state button')?.click();
    await fixture.whenStable();
    flush(dashboardOf(['AUTHOR'], { author: ok({ manuscripts: 1 }) }));
    await fixture.whenStable();

    expect((fixture.nativeElement as HTMLElement).querySelector('app-author-summary')).not.toBeNull();
  });

  it('no existe paso de selección de rol ni selector en el panel', async () => {
    const fixture = await render();
    flush(
      dashboardOf(['AUTHOR', 'EDITOR'], {
        author: ok(),
        editor: ok(),
      }),
    );
    await fixture.whenStable();

    const element = fixture.nativeElement as HTMLElement;
    expect(element.querySelector('select')).toBeNull();
    expect(element.textContent).not.toContain('Seleccione rol');
    // No pide el panel por sección: una única llamada HTTP en total.
    httpMock.verify();
  });
});
