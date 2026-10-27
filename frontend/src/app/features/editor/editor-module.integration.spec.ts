import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';

import { routes } from '../../app.routes';
import { AuthStore } from '../../core/auth/auth.store';
import { API_BASE_URL } from '../../core/http/api-base-url.token';
import { Role } from '../../core/models/role.model';
import { SessionUser } from '../../core/models/session-user.model';
import { errorEnvelope } from '../author/testing/manuscript.fixtures';
import {
  buildAssignment,
  buildSubmissionDetail,
  buildSubmissionPage,
  buildSubmissionRow,
} from './testing/editor.fixtures';

/**
 * Integración del módulo Editor con las rutas REALES de la aplicación
 * (TSK-57): carga diferida, guards de rol, títulos, navegación por enlaces,
 * estado de la bandeja en la URL y acceso por URL a un envío ajeno. Solo se
 * simula la API.
 */
const USER: SessionUser = {
  id: 'u-9',
  institutional_id: 'INST-0009',
  username: 'e.mora',
  email: 'e.mora@unl.edu.ec',
  first_name: 'Edgar',
  last_name: 'Mora',
  full_name: 'Edgar Mora',
};

const EDITOR_ROUTES = [
  ['bandeja', '/app/editor/submissions', 'app-submission-inbox', 'Nuevos envíos'],
  ['detalle', '/app/editor/submissions/s-1', 'app-submission-detail', 'Detalle del envío'],
  [
    'vencidas',
    '/app/editor/assignments/expired',
    'app-expired-assignments',
    'Asignaciones vencidas',
  ],
  ['incidentes', '/app/editor/incidents', 'app-incident-list', 'Incidentes confidenciales'],
] as const;

const EDITOR_SCREENS =
  'app-submission-inbox, app-submission-detail, app-expired-assignments, app-incident-list';

const emptyPage = { count: 0, next: null, previous: null, results: [] };

describe('Módulo Editor: integración con las rutas reales', () => {
  let http: HttpTestingController;
  let router: Router;
  let store: AuthStore;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideRouter(routes),
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: API_BASE_URL, useValue: '/api/' },
      ],
    });
    http = TestBed.inject(HttpTestingController);
    router = TestBed.inject(Router);
    store = TestBed.inject(AuthStore);
  });

  afterEach(() => http.verify());

  const signIn = (...roles: Role[]) => store.setSession({ user: USER, roles, access: 'token' });

  const inbox = () => http.expectOne((r) => r.url === '/api/editor/submissions/');
  const detail = () => http.expectOne('/api/editor/submissions/s-1/');
  const expired = () => http.expectOne((r) => r.url === '/api/editor/assignments/expired/');

  /** Abre una URL; `settle` además responde lo que el formulario de veredicto pide al montarse. */
  const open = async (url: string) => {
    const harness = await RouterTestingHarness.create();
    await harness.navigateByUrl(url);
    const element = harness.routeNativeElement as HTMLElement;
    const settle = async () => {
      await harness.fixture.whenStable();
      harness.detectChanges();
    };
    return { harness, element, settle };
  };

  const click = async (element: HTMLElement, label: string, settle: () => Promise<void>) => {
    const link = Array.from(element.querySelectorAll<HTMLElement>('a, button')).find(
      (e) => e.textContent?.trim() === label,
    );
    expect(link, `enlace «${label}»`).toBeDefined();
    link?.click();
    await settle();
  };

  describe('rutas y roles', () => {
    it.each(EDITOR_ROUTES)(
      '%s: el Editor llega a su pantalla, con el título correcto',
      async (_name, url, selector, title) => {
        signIn('EDITOR');
        const { element, settle } = await open(url);

        // Cada pantalla pide sus datos al cargar.
        if (selector === 'app-submission-inbox') inbox().flush(emptyPage);
        else if (selector === 'app-submission-detail') detail().flush(buildSubmissionDetail());
        else if (selector === 'app-expired-assignments') expired().flush(emptyPage);
        await settle();

        expect(element.querySelector(selector)).not.toBeNull();
        expect(document.title).toBe(title);
        expect(router.url).toBe(url);
      },
    );

    it.each(EDITOR_ROUTES)(
      '%s: sin el rol de Editor se muestra el 403 y no se pide nada',
      async (_name, url) => {
        signIn('REVIEWER');
        const { settle } = await open(url);
        await settle();

        expect(router.url).toBe('/forbidden');
        expect(document.querySelector('app-forbidden')).not.toBeNull();
        expect(document.querySelector(EDITOR_SCREENS)).toBeNull();
        http.expectNone(() => true);
      },
    );

    it.each(EDITOR_ROUTES)('%s: el Autor tampoco entra', async (_name, url) => {
      signIn('AUTHOR');
      await open(url);

      expect(router.url).toBe('/forbidden');
      http.expectNone(() => true);
    });

    it.each(EDITOR_ROUTES)('%s: el Administrador tampoco entra', async (_name, url) => {
      signIn('ADMIN');
      await open(url);

      expect(router.url).toBe('/forbidden');
      http.expectNone(() => true);
    });

    it('una persona con Autor y Editor entra sin conmutar de rol', async () => {
      signIn('AUTHOR', 'EDITOR');
      const { element, settle } = await open('/app/editor/submissions');
      inbox().flush(buildSubmissionPage([buildSubmissionRow()]));
      await settle();

      expect(element.querySelector('app-submission-inbox')).not.toBeNull();
      expect(element.querySelector('[role="tablist"], select[name="role"]')).toBeNull();
    });
  });

  describe('acceso por URL a un envío ajeno', () => {
    it('un envío fuera del ámbito del Editor (404) no muestra ningún dato del manuscrito', async () => {
      signIn('EDITOR');
      const { element, settle } = await open('/app/editor/submissions/s-1');
      detail().flush(errorEnvelope('NOT_FOUND', 'No encontrado.'), {
        status: 404,
        statusText: 'Not Found',
      });
      await settle();

      expect(element.querySelector('app-error-state')).not.toBeNull();
      expect(element.querySelector('h1')).toBeNull();
      expect(element.querySelector('table, dl, .timeline')).toBeNull();
      // Ni siquiera se intenta cargar la evaluación o los veredictos.
      http.expectNone((r) => r.url.includes('/evaluations/') || r.url.includes('/verdicts/'));
    });

    it('un Editor con conflicto de interés tampoco ve el envío por URL (404)', async () => {
      signIn('AUTHOR', 'EDITOR');
      const { element, settle } = await open('/app/editor/submissions/s-1');
      detail().flush(errorEnvelope('NOT_FOUND', 'No encontrado.'), {
        status: 404,
        statusText: 'Not Found',
      });
      await settle();

      expect(element.querySelector('app-submission-detail h1')).toBeNull();
      expect(element.querySelector('app-error-state')).not.toBeNull();
    });
  });

  describe('navegación por enlaces', () => {
    it('bandeja → detalle, usando el enlace del código', async () => {
      signIn('EDITOR');
      const { element, settle } = await open('/app/editor/submissions');
      inbox().flush(
        buildSubmissionPage([buildSubmissionRow({ id: 's-1', code: 'GPC-2026-000001' })]),
      );
      await settle();

      await click(element, 'GPC-2026-000001', settle);

      expect(router.url).toBe('/app/editor/submissions/s-1');
      detail().flush(buildSubmissionDetail());
      await settle();
      expect(element.querySelector('app-submission-detail')).not.toBeNull();
      expect(element.querySelector('h1')?.textContent).toContain('Efecto del clima');
    });

    it('detalle → bandeja con el enlace de regreso', async () => {
      signIn('EDITOR');
      const { element, settle } = await open('/app/editor/submissions/s-1');
      detail().flush(buildSubmissionDetail());
      await settle();

      await click(element, '← Volver a nuevos envíos', settle);

      expect(router.url).toBe('/app/editor/submissions');
      inbox().flush(emptyPage);
      await settle();
      expect(element.querySelector('app-submission-inbox')).not.toBeNull();
    });

    it('vencidas → detalle del envío con «Ver envío»', async () => {
      signIn('EDITOR');
      const { element, settle } = await open('/app/editor/assignments/expired');
      expired().flush({
        count: 1,
        next: null,
        previous: null,
        results: [buildAssignment({ status: 'EXPIRED', manuscript: 's-1' })],
      });
      await settle();

      const link = Array.from(element.querySelectorAll<HTMLAnchorElement>('tbody a')).find((a) =>
        a.textContent?.includes('Ver envío'),
      );
      link?.click();
      await settle();

      expect(router.url).toBe('/app/editor/submissions/s-1');
      detail().flush(buildSubmissionDetail({ status: 'UNDER_REVIEW' }));
      await settle();
      // El formulario de veredicto pide su evaluación y sus veredictos al montarse.
      http
        .match((r) => r.url.endsWith('/evaluations/') || r.url.endsWith('/verdicts/'))
        .forEach((r) => r.flush(emptyPage));
      await settle();
      expect(element.querySelector('app-submission-detail')).not.toBeNull();
    });
  });

  describe('estado de la bandeja en la URL', () => {
    it('filtrar deja el estado en la URL y recargar esa URL reproduce la misma vista', async () => {
      signIn('EDITOR');
      const first = await open('/app/editor/submissions');
      inbox().flush(buildSubmissionPage([buildSubmissionRow()]));
      await first.settle();

      const search = first.element.querySelector('#filter-search') as HTMLInputElement;
      search.value = 'clima';
      search.dispatchEvent(new Event('input'));
      const ordering = first.element.querySelector('#filter-ordering') as HTMLSelectElement;
      ordering.value = 'title';
      ordering.dispatchEvent(new Event('change'));
      (first.element.querySelector('form button[type="submit"]') as HTMLButtonElement).click();
      await first.settle();
      inbox().flush(emptyPage);
      await first.settle();
      const persisted = router.url;
      expect(persisted).toBe('/app/editor/submissions?search=clima&ordering=title');

      // «Recargar»: salir y volver a la misma URL pide lo mismo y rellena los filtros.
      await first.harness.navigateByUrl('/app/editor/assignments/expired');
      expired().flush(emptyPage);
      await first.settle();
      await first.harness.navigateByUrl(persisted);
      const reload = inbox();
      expect(reload.request.params.get('search')).toBe('clima');
      expect(reload.request.params.get('ordering')).toBe('title');
      reload.flush(emptyPage);
      await first.settle();
      expect((first.element.querySelector('#filter-search') as HTMLInputElement).value).toBe(
        'clima',
      );
      expect((first.element.querySelector('#filter-ordering') as HTMLSelectElement).value).toBe(
        'title',
      );
    });
  });
});
