import { Component } from '@angular/core';
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import {
  HttpTestingController,
  TestRequest,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';

import { authInterceptor } from '../../../core/auth/auth.interceptor';
import { API_BASE_URL } from '../../../core/http/api-base-url.token';
import { errorInterceptor } from '../../../core/http/error.interceptor';
import { AuditEvent } from '../../../core/models/audit.model';
import {
  ACTOR_ID,
  EVENT_ID,
  HASH,
  MANUSCRIPT_ID,
  buildEvent,
  buildEventPage,
} from '../testing/audit.fixtures';
import { AuditLogListComponent, PAGE_SIZE } from './audit-log-list.component';

@Component({ template: '' })
class BlankComponent {}

const LIST = '/api/admin/audit/';

describe('AuditLogListComponent', () => {
  let http: HttpTestingController;
  let router: Router;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideRouter([
          { path: 'app/admin/audit', component: AuditLogListComponent },
          { path: 'app/admin/audit/:id', component: BlankComponent },
        ]),
        provideHttpClient(withInterceptors([authInterceptor, errorInterceptor])),
        provideHttpClientTesting(),
        { provide: API_BASE_URL, useValue: '/api/' },
      ],
    });
    http = TestBed.inject(HttpTestingController);
    router = TestBed.inject(Router);
  });

  afterEach(() => http.verify());

  const text = (node: Element | null) => (node?.textContent ?? '').replace(/\s+/g, ' ').trim();
  const listRequest = (): TestRequest => http.expectOne((r) => r.method === 'GET' && r.url === LIST);

  const open = async (url = '/app/admin/audit') => {
    const harness = await RouterTestingHarness.create();
    await harness.navigateByUrl(url, AuditLogListComponent);
    const element = harness.routeNativeElement as HTMLElement;
    const settle = async () => {
      await harness.fixture.whenStable();
      harness.detectChanges();
    };
    return { harness, element, settle };
  };

  const render = async (events: AuditEvent[], count = events.length, url = '/app/admin/audit') => {
    const view = await open(url);
    listRequest().flush(buildEventPage(events, count));
    await view.settle();
    return view;
  };

  const rows = (element: HTMLElement) => Array.from(element.querySelectorAll('tbody tr'));

  it('muestra un estado de carga mientras espera', async () => {
    const { element } = await open();

    expect(element.querySelector('app-loading-spinner')).not.toBeNull();
    listRequest().flush(buildEventPage([]));
  });

  it('pide la primera página sin filtros', async () => {
    const { settle } = await open();

    const request = listRequest();
    expect(request.request.params.get('page_size')).toBe(String(PAGE_SIZE));
    expect(request.request.params.has('actor')).toBe(false);
    expect(request.request.params.has('page')).toBe(false);
    request.flush(buildEventPage([]));
    await settle();
  });

  it('muestra fecha, actor, rol, acción, entidad, manuscrito, resultado y hash', async () => {
    const { element } = await render([buildEvent()], 1);

    const cells = Array.from(rows(element)[0].querySelectorAll('td')).map(text);
    expect(cells[0]).toBe('22/10/2026 10:30:45');
    expect(cells[1]).toContain(ACTOR_ID.slice(0, 8));
    expect(cells[2]).toBe('Editor');
    expect(cells[3]).toContain('Veredicto registrado');
    expect(cells[3]).toContain('VERDICT_REGISTERED');
    expect(cells[4]).toBe('VERDICT');
    expect(cells[5]).toContain('GPC-2026-000001');
    expect(cells[6]).toBe('Éxito');
    expect(cells[7]).toBe(HASH.slice(0, 12));
    expect(element.querySelector('.events__hash')!.getAttribute('title')).toBe(HASH);
  });

  it('un evento sin actor se muestra como del sistema, sin rol ni manuscrito', async () => {
    const { element } = await render([
      buildEvent({ actor_id: null, actor_role: null, manuscript_id: null, manuscript_code: null }),
    ]);

    const cells = Array.from(rows(element)[0].querySelectorAll('td')).map(text);
    expect(cells[1]).toBe('Sistema');
    expect(cells[2]).toBe('—');
    expect(cells[5]).toBe('—');
  });

  it('no muestra datos personales ni contenido del manuscrito', async () => {
    const { element } = await render([buildEvent()]);

    const content = text(element);
    expect(content).not.toMatch(/@/);
    expect(content).not.toContain('ip_address');
    expect(content).not.toContain('user_agent');
    expect(element.querySelector('app-audit-filters')).not.toBeNull();
  });

  it('la lista no ofrece «Habilitar corrección»', async () => {
    const { element } = await render([buildEvent()]);

    expect(text(element)).not.toContain('Habilitar corrección');
  });

  it('cada fila enlaza al detalle por el id público del evento', async () => {
    const { element } = await render([buildEvent()]);

    const link = element.querySelector<HTMLAnchorElement>('tbody a[href^="/app/admin/audit/"]')!;
    expect(link.getAttribute('href')).toBe(`/app/admin/audit/${EVENT_ID}`);
  });

  it('cuenta los eventos en singular y plural', async () => {
    const one = await render([buildEvent()], 1);
    expect(text(one.element.querySelector('.list-header__count'))).toBe('1 evento');
  });

  it('sin eventos muestra el estado vacío', async () => {
    const { element } = await render([]);

    expect(text(element.querySelector('app-empty-state'))).toBe('Aún no hay eventos de auditoría.');
  });

  it('sin coincidencias con filtros lo dice', async () => {
    const { element } = await render([], 0, '/app/admin/audit?result=DENIED');

    expect(text(element.querySelector('app-empty-state'))).toBe(
      'Ningún evento coincide con los filtros aplicados.',
    );
  });

  describe('filtros en la URL', () => {
    it('pide los filtros combinados de la URL', async () => {
      const { settle } = await open(
        `/app/admin/audit?date_from=2026-10-01&date_to=2026-10-31&actor=${ACTOR_ID}&action=LOGIN&manuscript=${MANUSCRIPT_ID}&result=FAILURE&page=2`,
      );

      const params = listRequest().request.params;
      expect(params.get('date_from')).toBe('2026-10-01');
      expect(params.get('date_to')).toBe('2026-10-31');
      expect(params.get('actor')).toBe(ACTOR_ID);
      expect(params.get('action')).toBe('LOGIN');
      expect(params.get('manuscript')).toBe(MANUSCRIPT_ID);
      expect(params.get('result')).toBe('FAILURE');
      expect(params.get('page')).toBe('2');
      await settle();
    });

    it('descarta un parámetro manipulado en vez de provocar un 400', async () => {
      const { settle } = await open('/app/admin/audit?actor=no-uuid&result=MAYBE&date_from=ayer');

      const params = listRequest().request.params;
      expect(params.has('actor')).toBe(false);
      expect(params.has('result')).toBe(false);
      expect(params.has('date_from')).toBe(false);
      await settle();
    });

    it('al filtrar vuelve a la página 1 y lleva los filtros a la URL', async () => {
      const { element, settle } = await render([buildEvent()], 60, '/app/admin/audit?page=2');
      const select = element.querySelector<HTMLSelectElement>('#audit-result')!;

      select.value = 'DENIED';
      select.dispatchEvent(new Event('change'));
      element.querySelector('form')!.dispatchEvent(new Event('submit'));
      await settle();

      expect(router.url).toBe('/app/admin/audit?result=DENIED');
      expect(listRequest().request.params.get('result')).toBe('DENIED');
    });

    it('pulsar un manuscrito de la tabla filtra por él', async () => {
      const { element, settle } = await render([buildEvent()]);

      const link = Array.from(element.querySelectorAll<HTMLAnchorElement>('tbody a')).find((a) =>
        a.textContent!.includes('GPC-2026-000001'),
      )!;
      link.click();
      await settle();

      expect(router.url).toBe(`/app/admin/audit?manuscript=${MANUSCRIPT_ID}`);
      expect(listRequest().request.params.get('manuscript')).toBe(MANUSCRIPT_ID);
    });

    it('pulsar un actor de la tabla filtra por él', async () => {
      const { element, settle } = await render([buildEvent()]);

      element.querySelector<HTMLAnchorElement>('.events__id')!.click();
      await settle();

      expect(router.url).toBe(`/app/admin/audit?actor=${ACTOR_ID}`);
      expect(listRequest().request.params.get('actor')).toBe(ACTOR_ID);
    });
  });

  describe('paginación', () => {
    it('ofrece la página siguiente y la lleva a la URL', async () => {
      const { element, settle } = await render([buildEvent()], 60);

      Array.from(element.querySelectorAll<HTMLButtonElement>('app-pagination button'))
        .find((b) => b.textContent!.includes('Siguiente'))!
        .click();
      await settle();

      expect(router.url).toBe('/app/admin/audit?page=2');
      expect(listRequest().request.params.get('page')).toBe('2');
    });
  });

  describe('errores', () => {
    it('un 403 muestra un error controlado con reintento', async () => {
      const { element, settle } = await open();

      listRequest().flush(
        { error: { code: 'FORBIDDEN', message: 'No autorizado.' } },
        { status: 403, statusText: 'Forbidden' },
      );
      await settle();

      expect(element.querySelector('app-error-state')).not.toBeNull();
      expect(element.querySelector('table')).toBeNull();
    });

    it('un 503 (auditoría no disponible) permite reintentar', async () => {
      const { element, settle } = await open();
      listRequest().flush(
        { error: { code: 'AUDIT_UNAVAILABLE', message: 'No disponible.' } },
        { status: 503, statusText: 'Service Unavailable' },
      );
      await settle();

      element.querySelector<HTMLButtonElement>('app-error-state button')!.click();
      await settle();
      listRequest().flush(buildEventPage([buildEvent()]));
      await settle();

      expect(rows(element)).toHaveLength(1);
    });
  });
});
