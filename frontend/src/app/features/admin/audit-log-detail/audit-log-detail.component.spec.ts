import { Component } from '@angular/core';
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';

import { authInterceptor } from '../../../core/auth/auth.interceptor';
import { API_BASE_URL } from '../../../core/http/api-base-url.token';
import { errorInterceptor } from '../../../core/http/error.interceptor';
import { AuditEventDetail } from '../../../core/models/audit.model';
import {
  EVENT_ID,
  HASH,
  MANUSCRIPT_ID,
  PREVIOUS_HASH,
  buildEventDetail,
} from '../testing/audit.fixtures';
import { AuditLogDetailComponent } from './audit-log-detail.component';

@Component({ template: '' })
class BlankComponent {}

const URL = `/api/admin/audit/${EVENT_ID}/`;

describe('AuditLogDetailComponent', () => {
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideRouter([
          { path: 'app/admin/audit', component: BlankComponent },
          { path: 'app/admin/audit/:id', component: AuditLogDetailComponent },
        ]),
        provideHttpClient(withInterceptors([authInterceptor, errorInterceptor])),
        provideHttpClientTesting(),
        { provide: API_BASE_URL, useValue: '/api/' },
      ],
    });
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  const text = (node: Element | null) => (node?.textContent ?? '').replace(/\s+/g, ' ').trim();

  const open = async () => {
    const harness = await RouterTestingHarness.create();
    await harness.navigateByUrl(`/app/admin/audit/${EVENT_ID}`, AuditLogDetailComponent);
    const element = harness.routeNativeElement as HTMLElement;
    const settle = async () => {
      await harness.fixture.whenStable();
      harness.detectChanges();
    };
    return { element, settle };
  };

  const render = async (detail: AuditEventDetail) => {
    const view = await open();
    http.expectOne(URL).flush(detail);
    await view.settle();
    return view;
  };

  const fact = (element: HTMLElement, term: string) =>
    Array.from(element.querySelectorAll('dl > div')).find(
      (row) => text(row.querySelector('dt')) === term,
    );

  const correctionButton = (element: HTMLElement) =>
    Array.from(element.querySelectorAll<HTMLButtonElement>('button')).find((b) =>
      b.textContent!.includes('Habilitar corrección'),
    );

  it('muestra un estado de carga mientras espera', async () => {
    const { element } = await open();

    expect(element.querySelector('app-loading-spinner')).not.toBeNull();
    http.expectOne(URL).flush(buildEventDetail());
  });

  it('muestra actor, rol, acción, entidad, resultado, fecha y los dos hashes', async () => {
    const { element } = await render(buildEventDetail());

    expect(text(fact(element, 'Fecha')!.querySelector('dd'))).toBe('22/10/2026 10:30:45');
    expect(text(fact(element, 'Acción')!.querySelector('dd'))).toContain('Veredicto registrado');
    expect(text(fact(element, 'Resultado')!.querySelector('dd'))).toBe('Éxito');
    expect(text(fact(element, 'Rol')!.querySelector('dd'))).toBe('Editor');
    expect(text(fact(element, 'Actor')!.querySelector('dd'))).toContain('3f2b1c9e');
    expect(text(fact(element, 'Entidad')!.querySelector('dd'))).toContain('VERDICT');
    expect(text(fact(element, 'Hash del evento')!.querySelector('dd'))).toBe(HASH);
    expect(text(fact(element, 'Hash anterior')!.querySelector('dd'))).toBe(PREVIOUS_HASH);
  });

  it('el primer evento de la cadena no tiene hash anterior', async () => {
    const { element } = await render(buildEventDetail({ previous_hash: null }));

    expect(text(fact(element, 'Hash anterior')!.querySelector('dd'))).toBe('—');
  });

  it('un evento del sistema se muestra sin actor ni rol', async () => {
    const { element } = await render(buildEventDetail({ actor_id: null, actor_role: null }));

    expect(text(fact(element, 'Actor')!.querySelector('dd'))).toBe('Sistema');
    expect(text(fact(element, 'Rol')!.querySelector('dd'))).toBe('—');
  });

  it('el manuscrito enlaza a la lista filtrada por él', async () => {
    const { element } = await render(buildEventDetail());

    const link = fact(element, 'Manuscrito')!.querySelector<HTMLAnchorElement>('a')!;
    expect(text(link)).toBe('GPC-2026-000001');
    expect(link.getAttribute('href')).toBe(`/app/admin/audit?manuscript=${MANUSCRIPT_ID}`);
  });

  it('muestra los datos permitidos del evento con etiquetas en español', async () => {
    const { element } = await render(buildEventDetail());

    const section = element.querySelector('dl[aria-label="Datos del evento"]')!;
    const rows = Array.from(section.querySelectorAll('div')).map((row) => [
      text(row.querySelector('dt')),
      text(row.querySelector('dd')),
    ]);
    expect(rows).toEqual([
      ['Decisión', 'ACCEPTED'],
      ['Versión', '1'],
    ]);
  });

  it('sin datos adicionales no muestra la sección', async () => {
    const { element } = await render(buildEventDetail({ details: {} }));

    expect(element.querySelector('dl[aria-label="Datos del evento"]')).toBeNull();
  });

  it('no muestra contenido del manuscrito ni datos personales', async () => {
    const { element } = await render(buildEventDetail());

    const content = text(element);
    expect(content).not.toMatch(/@/);
    expect(content).not.toContain('ip_address');
    expect(content).not.toContain('user_agent');
    expect(content).not.toContain('abstract');
    expect(content).not.toContain('reason');
  });

  describe('«Habilitar corrección»', () => {
    it('aparece cuando el backend la autoriza', async () => {
      const { element } = await render(
        buildEventDetail({
          can_authorize_correction: true,
          verdict: {
            id: 'v-1',
            manuscript_code: 'GPC-2026-000001',
            decision: 'ACCEPTED',
            decided_at: '2026-10-22T15:00:00Z',
          },
        }),
      );

      expect(correctionButton(element)).toBeDefined();
      expect(text(element)).toContain('La decisión anterior se conserva');
    });

    it('no aparece si el backend responde false', async () => {
      const { element } = await render(buildEventDetail({ can_authorize_correction: false }));

      expect(correctionButton(element)).toBeUndefined();
    });

    it('no aparece si el backend no envía la marca (evento que no es de veredicto)', async () => {
      const { element } = await render(buildEventDetail({ action: 'LOGIN' }));

      expect(correctionButton(element)).toBeUndefined();
    });

    it('no se deduce del tipo de evento: un VERDICT_REGISTERED sin marca no la ofrece', async () => {
      const { element } = await render(buildEventDetail({ action: 'VERDICT_REGISTERED' }));

      expect(correctionButton(element)).toBeUndefined();
    });

    it('muestra el resumen del veredicto con la decisión en español', async () => {
      const { element } = await render(
        buildEventDetail({
          can_authorize_correction: false,
          verdict: {
            id: 'v-1',
            manuscript_code: 'GPC-2026-000001',
            decision: 'REQUIRES_CORRECTIONS',
            decided_at: '2026-10-22T15:00:00Z',
          },
        }),
      );

      const section = element.querySelector('dl[aria-label="Veredicto"]')!;
      expect(text(section)).toContain('Requiere correcciones');
      expect(text(section)).toContain('22/10/2026 10:00');
    });

    it('al pulsarla no envía nada al servidor', async () => {
      const { element, settle } = await render(buildEventDetail({ can_authorize_correction: true }));

      correctionButton(element)!.click();
      await settle();

      expect(text(element.querySelector('[role="status"]'))).toContain('aún no está disponible');
    });
  });

  describe('errores', () => {
    it('un evento inexistente (404) muestra un aviso controlado', async () => {
      const { element, settle } = await open();

      http
        .expectOne(URL)
        .flush({ error: { code: 'NOT_FOUND', message: 'No encontrado.' } }, { status: 404, statusText: 'Not Found' });
      await settle();

      expect(text(element.querySelector('[role="alert"]'))).toContain('El evento solicitado no existe.');
      expect(element.querySelector('a[href="/app/admin/audit"]')).not.toBeNull();
    });

    it('un 403 muestra un error con reintento', async () => {
      const { element, settle } = await open();

      http
        .expectOne(URL)
        .flush({ error: { code: 'FORBIDDEN', message: 'No autorizado.' } }, { status: 403, statusText: 'Forbidden' });
      await settle();

      expect(element.querySelector('app-error-state')).not.toBeNull();
    });

    it('un 503 permite reintentar y entonces carga el evento', async () => {
      const { element, settle } = await open();
      http
        .expectOne(URL)
        .flush({ error: { code: 'AUDIT_UNAVAILABLE', message: 'No disponible.' } }, { status: 503, statusText: 'Service Unavailable' });
      await settle();

      element.querySelector<HTMLButtonElement>('app-error-state button')!.click();
      await settle();
      http.expectOne(URL).flush(buildEventDetail());
      await settle();

      expect(fact(element, 'Resultado')).toBeDefined();
    });
  });
});
