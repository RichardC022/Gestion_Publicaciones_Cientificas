import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import {
  buildNotice,
  buildNoticePage,
} from '../../features/notifications/testing/notification.fixtures';
import { authInterceptor } from '../auth/auth.interceptor';
import { API_BASE_URL } from '../http/api-base-url.token';
import { errorInterceptor } from '../http/error.interceptor';
import { ApiError } from '../models/api-error.model';
import { NotificationService } from './notification.service';

describe('NotificationService', () => {
  let service: NotificationService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(withInterceptors([authInterceptor, errorInterceptor])),
        provideHttpClientTesting(),
        { provide: API_BASE_URL, useValue: '/api/' },
      ],
    });
    service = TestBed.inject(NotificationService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  describe('list', () => {
    it('pide todos los avisos sin filtro de lectura', () => {
      service.list('ALL', 1, 20).subscribe();

      const request = http.expectOne((r) => r.url === '/api/notifications/');
      expect(request.request.method).toBe('GET');
      expect(request.request.params.has('read')).toBe(false);
      expect(request.request.params.has('page')).toBe(false);
      expect(request.request.params.get('page_size')).toBe('20');
      request.flush(buildNoticePage([]));
    });

    it('«No leídos» envía read=false y la página pedida', () => {
      service.list('UNREAD', 3, 20).subscribe();

      const request = http.expectOne((r) => r.url === '/api/notifications/');
      expect(request.request.params.get('read')).toBe('false');
      expect(request.request.params.get('page')).toBe('3');
      request.flush(buildNoticePage([]));
    });

    it('el contador sale del total de no leídos de la respuesta, no de la página', () => {
      service.list('UNREAD', 1, 20).subscribe();

      http
        .expectOne((r) => r.url === '/api/notifications/')
        .flush(buildNoticePage([buildNotice()], 7));

      expect(service.unreadCount()).toBe(7);
    });

    it('normaliza el error y deja el contador como estaba', () => {
      let failure: ApiError | undefined;
      service.list('ALL').subscribe({ error: (e: ApiError) => (failure = e) });

      http
        .expectOne((r) => r.url === '/api/notifications/')
        .flush(
          { error: { code: 'SERVER_ERROR', message: 'Error.' } },
          { status: 500, statusText: 'Server Error' },
        );

      expect(failure?.status).toBe(500);
      expect(service.unreadCount()).toBe(0);
    });
  });

  describe('refresh', () => {
    it('lee solo el contador con una página mínima de no leídos', () => {
      service.refresh();

      const request = http.expectOne((r) => r.url === '/api/notifications/');
      expect(request.request.params.get('read')).toBe('false');
      expect(request.request.params.get('page_size')).toBe('1');
      request.flush(buildNoticePage([buildNotice()], 4));
      expect(service.unreadCount()).toBe(4);
    });

    it('un fallo no se propaga ni cambia el contador', () => {
      service.refresh();

      http
        .expectOne((r) => r.url === '/api/notifications/')
        .flush(
          { error: { code: 'SERVER_ERROR', message: 'Error.' } },
          { status: 500, statusText: 'Server Error' },
        );

      expect(service.unreadCount()).toBe(0);
    });
  });

  describe('markRead', () => {
    const prime = (count: number) => {
      service.list('ALL').subscribe();
      http
        .expectOne((r) => r.url === '/api/notifications/')
        .flush(buildNoticePage([buildNotice()], count));
    };

    it('marca el aviso con PATCH y baja el contador', () => {
      prime(3);
      const notice = buildNotice({ id: 'n-1' });
      let result;
      service.markRead(notice).subscribe((value) => (result = value));

      const request = http.expectOne('/api/notifications/n-1/read/');
      expect(request.request.method).toBe('PATCH');
      const updated = buildNotice({ id: 'n-1', is_read: true, read_at: '2026-11-07T15:00:00Z' });
      request.flush(updated);

      expect(result).toEqual(updated);
      expect(service.unreadCount()).toBe(2);
    });

    it('un aviso ya leído no baja el contador', () => {
      prime(3);
      service.markRead(buildNotice({ is_read: true })).subscribe();

      http.expectOne('/api/notifications/n-1/read/').flush(buildNotice({ is_read: true }));

      expect(service.unreadCount()).toBe(3);
    });

    it('el contador nunca queda por debajo de cero', () => {
      service.markRead(buildNotice()).subscribe();

      http.expectOne('/api/notifications/n-1/read/').flush(buildNotice({ is_read: true }));

      expect(service.unreadCount()).toBe(0);
    });

    it('un 404 (aviso ajeno) se normaliza y no toca el contador', () => {
      prime(3);
      let failure: ApiError | undefined;
      service.markRead(buildNotice()).subscribe({ error: (e: ApiError) => (failure = e) });

      http
        .expectOne('/api/notifications/n-1/read/')
        .flush(
          { error: { code: 'NOT_FOUND', message: 'No existe.' } },
          { status: 404, statusText: 'Not Found' },
        );

      expect(failure?.status).toBe(404);
      expect(service.unreadCount()).toBe(3);
    });

    it('codifica el identificador en la ruta', () => {
      service.markRead(buildNotice({ id: 'a/b' })).subscribe();

      http.expectOne('/api/notifications/a%2Fb/read/').flush(buildNotice());
    });
  });

  describe('markAllRead', () => {
    it('envía POST y deja el contador en cero', () => {
      service.list('ALL').subscribe();
      http.expectOne((r) => r.url === '/api/notifications/').flush(buildNoticePage([], 5));
      let done = false;
      service.markAllRead().subscribe(() => (done = true));

      const request = http.expectOne('/api/notifications/read-all/');
      expect(request.request.method).toBe('POST');
      request.flush(null, { status: 204, statusText: 'No Content' });

      expect(done).toBe(true);
      expect(service.unreadCount()).toBe(0);
    });

    it('si falla, el contador no cambia', () => {
      service.list('ALL').subscribe();
      http.expectOne((r) => r.url === '/api/notifications/').flush(buildNoticePage([], 5));
      let failure: ApiError | undefined;
      service.markAllRead().subscribe({ error: (e: ApiError) => (failure = e) });

      http
        .expectOne('/api/notifications/read-all/')
        .flush(
          { error: { code: 'SERVER_ERROR', message: 'Error.' } },
          { status: 500, statusText: 'Error' },
        );

      expect(failure?.status).toBe(500);
      expect(service.unreadCount()).toBe(5);
    });
  });
});
