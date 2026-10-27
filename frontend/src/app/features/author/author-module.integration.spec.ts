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
import { AUTHOR_ANA, buildManuscript, buildPage } from './testing/manuscript.fixtures';

/**
 * Integración del módulo Autor con las rutas REALES de la aplicación
 * (TSK-44): carga diferida, guards de rol, aviso de cambios sin guardar,
 * títulos, navegación por enlaces y estado del listado en la URL. Solo
 * se simula la API.
 */
const USER: SessionUser = {
  id: 'u-1',
  institutional_id: 'INST-0001',
  username: 'a.lopez',
  email: 'a.lopez@unl.edu.ec',
  first_name: 'Ana',
  last_name: 'López',
  full_name: 'Ana López',
};

const AUTHOR_ROUTES = [
  ['listado', '/app/author/manuscripts', 'app-manuscript-list', 'Mis manuscritos'],
  ['alta', '/app/author/manuscripts/new', 'app-manuscript-form', 'Nuevo manuscrito'],
  ['detalle', '/app/author/manuscripts/m-1', 'app-manuscript-detail', 'Detalle del manuscrito'],
  ['edición', '/app/author/manuscripts/m-1/edit', 'app-manuscript-form', 'Editar manuscrito'],
  [
    'historial',
    '/app/author/manuscripts/m-1/history',
    'app-version-history',
    'Historial de versiones',
  ],
] as const;

describe('Módulo Autor: integración con las rutas reales', () => {
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

  afterEach(() => {
    vi.restoreAllMocks();
    http.verify();
  });

  const signIn = (...roles: Role[]) => store.setSession({ user: USER, roles, access: 'token' });

  const list = () => http.expectOne((r) => r.url === '/api/manuscripts/');
  const detail = () => http.expectOne('/api/manuscripts/m-1/');

  /** Abre una URL y responde las solicitudes que cada pantalla hace al cargar. */
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
    it.each(AUTHOR_ROUTES)(
      '%s: el Autor llega a su pantalla, con el título correcto',
      async (_n, url, selector, title) => {
        signIn('AUTHOR');
        const { element, settle } = await open(url);

        // Cada pantalla pide sus datos al cargar.
        if (selector === 'app-manuscript-list') list().flush(buildPage([]));
        else if (selector === 'app-manuscript-form' && url.includes('m-1'))
          detail().flush(buildManuscript());
        else if (selector === 'app-manuscript-detail') detail().flush(buildManuscript());
        else if (selector === 'app-version-history') {
          detail().flush(buildManuscript());
          http
            .expectOne((r) => r.url === '/api/manuscripts/m-1/history/')
            .flush({ count: 0, next: null, previous: null, results: [] });
        }
        await settle();

        expect(element.querySelector(selector)).not.toBeNull();
        expect(document.title).toBe(title);
        expect(router.url).toBe(url);
      },
    );

    it.each(AUTHOR_ROUTES)(
      '%s: sin el rol de Autor se muestra el 403 y no se pide nada',
      async (_n, url) => {
        signIn('REVIEWER');
        const { settle } = await open(url);
        await settle();

        expect(router.url).toBe('/forbidden');
        // El 403 no vive dentro del shell: se busca en el documento.
        expect(document.querySelector('app-forbidden')).not.toBeNull();
        expect(
          document.querySelector(
            'app-manuscript-list, app-manuscript-form, app-manuscript-detail, app-version-history',
          ),
        ).toBeNull();
        http.expectNone(() => true);
      },
    );

    it.each(AUTHOR_ROUTES)('%s: el Administrador tampoco entra', async (_n, url) => {
      signIn('ADMIN');
      await open(url);

      expect(router.url).toBe('/forbidden');
    });

    it('una persona con Autor y Editor entra sin conmutar de rol', async () => {
      signIn('AUTHOR', 'EDITOR');
      const { element, settle } = await open('/app/author/manuscripts');
      list().flush(buildPage([buildManuscript()]));
      await settle();

      expect(element.querySelector('app-manuscript-list')).not.toBeNull();
      expect(element.querySelector('[role="tablist"], select[name="role"]')).toBeNull();
    });
  });

  describe('navegación por enlaces', () => {
    it('listado → detalle → edición → historial, usando los enlaces de cada pantalla', async () => {
      signIn('AUTHOR');
      const { element, settle } = await open('/app/author/manuscripts');
      list().flush(
        buildPage([buildManuscript({ id: 'm-1', code: 'GPC-2026-000001', status: 'DRAFT' })]),
      );
      await settle();

      await click(element, 'GPC-2026-000001', settle);
      expect(router.url).toBe('/app/author/manuscripts/m-1');
      detail().flush(buildManuscript({ status: 'DRAFT' }));
      await settle();
      expect(element.querySelector('app-manuscript-detail')).not.toBeNull();

      await click(element, 'Editar manuscrito', settle);
      expect(router.url).toBe('/app/author/manuscripts/m-1/edit');
      detail().flush(buildManuscript({ status: 'DRAFT' }), { headers: { ETag: '"3"' } });
      await settle();
      expect(element.querySelector('app-manuscript-form')).not.toBeNull();
      expect((element.querySelector('#title') as HTMLInputElement).value).toBe(
        'Efecto del clima en cultivos andinos',
      );

      await click(element, 'Cancelar', settle);
      expect(router.url).toBe('/app/author/manuscripts/m-1');
      detail().flush(buildManuscript({ status: 'DRAFT' }));
      await settle();

      await click(element, 'Historial de versiones', settle);
      expect(router.url).toBe('/app/author/manuscripts/m-1/history');
      detail().flush(buildManuscript({ status: 'DRAFT' }));
      http
        .expectOne((r) => r.url === '/api/manuscripts/m-1/history/')
        .flush({ count: 0, next: null, previous: null, results: [] });
      await settle();
      expect(element.querySelector('app-version-history')).not.toBeNull();
    });

    it('«Nuevo manuscrito» desde el listado abre el formulario de alta con el autor precargado', async () => {
      signIn('AUTHOR');
      const { element, settle } = await open('/app/author/manuscripts');
      list().flush(buildPage([buildManuscript()]));
      await settle();

      await click(element, 'Nuevo manuscrito', settle);

      expect(router.url).toBe('/app/author/manuscripts/new');
      expect((element.querySelector('#author-email-0') as HTMLInputElement).value).toBe(
        'a.lopez@unl.edu.ec',
      );
    });
  });

  describe('estado del listado en la URL', () => {
    it('filtrar deja el estado en la URL y recargar esa URL reproduce la misma vista', async () => {
      signIn('AUTHOR');
      const first = await open('/app/author/manuscripts');
      list().flush(buildPage([buildManuscript()]));
      await first.settle();

      const select = first.element.querySelector('#filter-status') as HTMLSelectElement;
      select.value = 'REQUIRES_CORRECTIONS';
      select.dispatchEvent(new Event('change'));
      (first.element.querySelector('form button[type="submit"]') as HTMLButtonElement).click();
      await first.settle();
      list().flush(buildPage([]));
      await first.settle();
      const persisted = router.url;
      expect(persisted).toBe('/app/author/manuscripts?status=REQUIRES_CORRECTIONS');

      // «Recargar»: salir y volver a la misma URL pide lo mismo y rellena el filtro.
      await first.harness.navigateByUrl('/app/author/manuscripts/new');
      await first.harness.navigateByUrl(persisted);
      const reload = list();
      expect(reload.request.params.get('status')).toBe('REQUIRES_CORRECTIONS');
      reload.flush(buildPage([]));
      await first.settle();
      expect((first.element.querySelector('#filter-status') as HTMLSelectElement).value).toBe(
        'REQUIRES_CORRECTIONS',
      );
    });
  });

  describe('cambios sin guardar en las rutas de formulario', () => {
    const editWithChanges = async () => {
      signIn('AUTHOR');
      const view = await open('/app/author/manuscripts/m-1/edit');
      detail().flush(buildManuscript({ status: 'DRAFT', authors: [{ ...AUTHOR_ANA }] }), {
        headers: { ETag: '"1"' },
      });
      await view.settle();
      const title = view.element.querySelector('#title') as HTMLInputElement;
      title.value = 'Título modificado';
      title.dispatchEvent(new Event('input'));
      await view.settle();
      return view;
    };

    it('advierte antes de abandonar y se queda si la persona no confirma', async () => {
      const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
      await editWithChanges();

      const left = await router.navigateByUrl('/app/author/manuscripts');

      expect(confirm).toHaveBeenCalledTimes(1);
      expect(left).toBe(false);
      expect(router.url).toBe('/app/author/manuscripts/m-1/edit');
    });

    it('permite abandonar si la persona confirma', async () => {
      vi.spyOn(window, 'confirm').mockReturnValue(true);
      await editWithChanges();

      const left = await router.navigateByUrl('/app/author/manuscripts');
      list().flush(buildPage([]));

      expect(left).toBe(true);
      expect(router.url).toBe('/app/author/manuscripts');
    });

    it('sin cambios no pregunta nada', async () => {
      const confirm = vi.spyOn(window, 'confirm');
      signIn('AUTHOR');
      const { settle } = await open('/app/author/manuscripts/new');
      await settle();

      const left = await router.navigateByUrl('/app/author/manuscripts');
      list().flush(buildPage([]));

      expect(confirm).not.toHaveBeenCalled();
      expect(left).toBe(true);
    });
  });
});
