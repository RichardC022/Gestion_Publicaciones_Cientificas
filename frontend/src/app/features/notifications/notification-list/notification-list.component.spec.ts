import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';

import { authInterceptor } from '../../../core/auth/auth.interceptor';
import { API_BASE_URL } from '../../../core/http/api-base-url.token';
import { errorInterceptor } from '../../../core/http/error.interceptor';
import { Notice, NoticePage } from '../../../core/models/notification.model';
import { NotificationService } from '../../../core/services/notification.service';
import { HTTP_ERROR_CASES, errorResponse } from '../../../core/testing/http-error.fixtures';
import { buildNotice, buildNoticePage, buildNoticePayload } from '../testing/notification.fixtures';
import { NotificationListComponent } from './notification-list.component';

const LIST = (r: { url: string }) => r.url === '/api/notifications/';

describe('NotificationListComponent', () => {
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideRouter([
          { path: 'app/notifications', component: NotificationListComponent },
          // Destino de los enlaces de los avisos de prueba.
          { path: 'app/editor/submissions/:id', children: [] },
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

  /** Abre `/app/notifications` (con la query indicada) y responde la lista. */
  const open = async (page: NoticePage | null = buildNoticePage([]), query = '') => {
    const harness = await RouterTestingHarness.create();
    await harness.navigateByUrl(`/app/notifications${query}`, NotificationListComponent);
    const element = harness.routeNativeElement as HTMLElement;
    const settle = async () => {
      await harness.fixture.whenStable();
      harness.detectChanges();
    };
    const request = http.expectOne(LIST);
    if (page) {
      request.flush(page);
    }
    await settle();
    return { harness, element, settle, request };
  };

  const items = (element: HTMLElement) =>
    Array.from(element.querySelectorAll('app-notification-item'));
  const markAllButton = (element: HTMLElement) =>
    Array.from(element.querySelectorAll<HTMLButtonElement>('button')).find((b) =>
      text(b).includes('Marcar todos como leídos'),
    )!;
  const markButton = (item: Element) =>
    Array.from(item.querySelectorAll<HTMLButtonElement>('button')).find((b) =>
      text(b).includes('Marcar como leído'),
    );

  it('muestra un estado de carga mientras espera', async () => {
    const harness = await RouterTestingHarness.create();
    await harness.navigateByUrl('/app/notifications', NotificationListComponent);

    expect(harness.routeNativeElement!.querySelector('app-loading-spinner')).not.toBeNull();
    http.expectOne(LIST).flush(buildNoticePage([]));
  });

  describe('lista', () => {
    it('muestra los avisos con el contador de no leídos', async () => {
      const { element } = await open(
        buildNoticePage(
          [
            buildNotice({ id: 'n-1' }),
            buildNotice({ id: 'n-2', is_read: true, read_at: '2026-11-07T15:00:00Z' }),
          ],
          1,
        ),
      );

      expect(items(element).length).toBe(2);
      expect(text(element.querySelector('.list-header__count'))).toBe('1 aviso sin leer');
    });

    it('sin avisos lo dice', async () => {
      const { element } = await open();

      expect(text(element.querySelector('app-empty-state'))).toBe('Todavía no tiene avisos.');
      expect(text(element.querySelector('.list-header__count'))).toBe('No tiene avisos sin leer.');
    });

    it('con «No leídos» y sin resultados lo dice', async () => {
      const { element } = await open(buildNoticePage([]), '?filter=unread');

      expect(text(element.querySelector('app-empty-state'))).toBe('No tiene avisos sin leer.');
    });

    it('un error del servidor se explica y permite reintentar', async () => {
      const harness = await RouterTestingHarness.create();
      await harness.navigateByUrl('/app/notifications', NotificationListComponent);
      const element = harness.routeNativeElement as HTMLElement;
      http
        .expectOne(LIST)
        .flush(
          { error: { code: 'SERVER_ERROR', message: 'Error.' } },
          { status: 500, statusText: 'Error' },
        );
      await harness.fixture.whenStable();
      harness.detectChanges();

      expect(element.querySelector('app-error-state')).not.toBeNull();
      (element.querySelector('app-error-state button') as HTMLButtonElement).click();
      http.expectOne(LIST).flush(buildNoticePage([buildNotice()]));
      await harness.fixture.whenStable();
      harness.detectChanges();

      expect(items(element).length).toBe(1);
    });
  });

  describe('errores HTTP al cargar', () => {
    it.each(HTTP_ERROR_CASES)(
      'un $status se explica sin mostrar avisos y permite reintentar',
      async (testCase) => {
        const harness = await RouterTestingHarness.create();
        await harness.navigateByUrl('/app/notifications', NotificationListComponent);
        const element = harness.routeNativeElement as HTMLElement;
        http.expectOne(LIST).flush(...errorResponse(testCase));
        await harness.fixture.whenStable();
        harness.detectChanges();

        expect(text(element.querySelector('app-error-state'))).toContain(testCase.shown);
        expect(items(element)).toHaveLength(0);
        expect(element.querySelector('app-error-state button')).not.toBeNull();
        expect(TestBed.inject(NotificationService).unreadCount()).toBe(0);
      },
    );
  });

  describe('filtro y página en la URL', () => {
    it('sin parámetros pide todos los avisos, primera página', async () => {
      const { request } = await open(null);

      expect(request.request.params.has('read')).toBe(false);
      expect(request.request.params.has('page')).toBe(false);
      request.flush(buildNoticePage([]));
    });

    it('?filter=unread pide solo los no leídos y marca la pestaña activa', async () => {
      const { element, request, settle } = await open(null, '?filter=unread');

      expect(request.request.params.get('read')).toBe('false');
      request.flush(buildNoticePage([]));
      await settle();
      const current = element.querySelector('.tabs__link[aria-current="page"]');
      expect(text(current)).toBe('No leídos');
    });

    it('un filtro manipulado vuelve a todos', async () => {
      const { element, request, settle } = await open(null, '?filter=%3Cscript%3E');

      expect(request.request.params.has('read')).toBe(false);
      request.flush(buildNoticePage([]));
      await settle();
      expect(text(element.querySelector('.tabs__link[aria-current="page"]'))).toBe('Todos');
    });

    it('la página de la URL se envía a la API', async () => {
      const { request } = await open(null, '?page=2');

      expect(request.request.params.get('page')).toBe('2');
      request.flush(buildNoticePage([]));
    });

    it('Siguiente avanza la página en la URL y vuelve a consultar', async () => {
      const { element, settle, harness } = await open(buildNoticePage([buildNotice()], 1, 45));

      (
        Array.from(element.querySelectorAll('app-pagination button')).find((b) =>
          text(b).includes('Siguiente'),
        ) as HTMLButtonElement
      ).click();
      await settle();

      expect(TestBed.inject(Router).url).toBe('/app/notifications?page=2');
      const request = http.expectOne(LIST);
      expect(request.request.params.get('page')).toBe('2');
      request.flush(buildNoticePage([buildNotice({ id: 'n-9' })], 1, 45));
      await settle();
      expect(harness.routeNativeElement!.querySelectorAll('app-notification-item').length).toBe(1);
    });
  });

  describe('marcar como leído', () => {
    it('marca uno: lo actualiza en la lista y baja el contador sin recargar', async () => {
      const { element, settle } = await open(
        buildNoticePage([buildNotice({ id: 'n-1' }), buildNotice({ id: 'n-2' })], 2),
      );
      const service = TestBed.inject(NotificationService);
      expect(service.unreadCount()).toBe(2);

      markButton(items(element)[0])!.click();
      await settle();
      http
        .expectOne('/api/notifications/n-1/read/')
        .flush(buildNotice({ id: 'n-1', is_read: true, read_at: '2026-11-07T15:00:00Z' }));
      await settle();

      expect(markButton(items(element)[0])).toBeUndefined();
      expect(markButton(items(element)[1])).toBeDefined();
      expect(service.unreadCount()).toBe(1);
      expect(text(element.querySelector('.list-header__count'))).toBe('1 aviso sin leer');
    });

    it('con «No leídos» el aviso marcado sigue a la vista hasta la próxima lectura', async () => {
      const { element, settle } = await open(
        buildNoticePage([buildNotice({ id: 'n-1' })], 1),
        '?filter=unread',
      );

      markButton(items(element)[0])!.click();
      await settle();
      http
        .expectOne('/api/notifications/n-1/read/')
        .flush(buildNotice({ id: 'n-1', is_read: true, read_at: '2026-11-07T15:00:00Z' }));
      await settle();

      expect(items(element).length).toBe(1);
      expect(markButton(items(element)[0])).toBeUndefined();
    });

    it('abrir el enlace de un aviso sin leer lo marca como leído', async () => {
      const { element, settle } = await open(buildNoticePage([buildNotice({ id: 'n-1' })], 1));

      (items(element)[0].querySelector('a') as HTMLAnchorElement).click();
      await settle();

      const request = http.expectOne('/api/notifications/n-1/read/');
      expect(request.request.method).toBe('PATCH');
      request.flush(buildNotice({ id: 'n-1', is_read: true }));
    });

    it('un error al marcar lo explica y el aviso sigue sin leer', async () => {
      const { element, settle } = await open(buildNoticePage([buildNotice({ id: 'n-1' })], 1));

      markButton(items(element)[0])!.click();
      await settle();
      http
        .expectOne('/api/notifications/n-1/read/')
        .flush(
          { error: { code: 'NOT_FOUND', message: 'No existe.' } },
          { status: 404, statusText: 'Not Found' },
        );
      await settle();

      expect(text(element.querySelector('[role="alert"]'))).toContain('no existe');
      expect(markButton(items(element)[0])).toBeDefined();
      expect(TestBed.inject(NotificationService).unreadCount()).toBe(1);
    });

    it.each(HTTP_ERROR_CASES)(
      'un $status al marcar uno se explica y el aviso sigue sin leer',
      async (testCase) => {
        const { element, settle } = await open(buildNoticePage([buildNotice({ id: 'n-1' })], 1));

        markButton(items(element)[0])!.click();
        await settle();
        http.expectOne('/api/notifications/n-1/read/').flush(...errorResponse(testCase));
        await settle();

        expect(text(element.querySelector('[role="alert"]'))).toContain(testCase.shown);
        expect(markButton(items(element)[0])).toBeDefined();
        expect(TestBed.inject(NotificationService).unreadCount()).toBe(1);
      },
    );

    it.each(HTTP_ERROR_CASES)(
      'un $status al marcar todos no cambia el contador ni los avisos',
      async (testCase) => {
        const { element, settle } = await open(buildNoticePage([buildNotice()], 1));

        markAllButton(element).click();
        await settle();
        http.expectOne('/api/notifications/read-all/').flush(...errorResponse(testCase));
        await settle();

        expect(text(element.querySelector('[role="alert"]'))).toContain(testCase.shown);
        expect(items(element)).toHaveLength(1);
        expect(TestBed.inject(NotificationService).unreadCount()).toBe(1);
      },
    );

    it('marca todos: envía una sola petición, vuelve a leer y deja el contador en cero', async () => {
      const { element, settle } = await open(
        buildNoticePage([buildNotice({ id: 'n-1' }), buildNotice({ id: 'n-2' })], 2),
      );

      markAllButton(element).click();
      await settle();
      http
        .expectOne('/api/notifications/read-all/')
        .flush(null, { status: 204, statusText: 'No Content' });
      await settle();
      // Se vuelve a leer la lista para mostrar el estado real.
      http
        .expectOne(LIST)
        .flush(
          buildNoticePage(
            [buildNotice({ id: 'n-1', is_read: true }), buildNotice({ id: 'n-2', is_read: true })],
            0,
          ),
        );
      await settle();

      expect(TestBed.inject(NotificationService).unreadCount()).toBe(0);
      expect(text(element.querySelector('.list-header__count'))).toBe('No tiene avisos sin leer.');
      expect(markAllButton(element).disabled).toBe(true);
      expect(element.querySelectorAll('app-notification-item button').length).toBe(0);
    });

    it('«Marcar todos» está bloqueado si no hay avisos sin leer', async () => {
      const { element } = await open(
        buildNoticePage([buildNotice({ is_read: true, read_at: '2026-11-07T15:00:00Z' })], 0),
      );

      expect(markAllButton(element).disabled).toBe(true);
    });

    it('si marcar todos falla, lo explica y no cambia el contador', async () => {
      const { element, settle } = await open(buildNoticePage([buildNotice()], 1));

      markAllButton(element).click();
      await settle();
      http
        .expectOne('/api/notifications/read-all/')
        .flush(
          { error: { code: 'SERVER_ERROR', message: 'Error.' } },
          { status: 500, statusText: 'Error' },
        );
      await settle();

      expect(element.querySelector('[role="alert"]')).not.toBeNull();
      expect(TestBed.inject(NotificationService).unreadCount()).toBe(1);
    });
  });

  describe('privacidad', () => {
    it('solo muestra el contenido sanitizado del aviso, sin identificadores internos', async () => {
      const notice: Notice = buildNotice({
        payload: buildNoticePayload(),
      });
      const { element } = await open(buildNoticePage([notice]));

      const content = text(element);
      expect(content).not.toContain(notice.id);
      expect(content).not.toMatch(/@|recipient|reviewer_id|author/i);
    });
  });
});
