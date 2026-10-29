import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import {
  EVENT_ID,
  buildEvent,
  buildEventDetail,
  buildEventPage,
} from '../../features/admin/testing/audit.fixtures';
import { authInterceptor } from '../auth/auth.interceptor';
import { API_BASE_URL } from '../http/api-base-url.token';
import { errorInterceptor } from '../http/error.interceptor';
import { ApiError } from '../models/api-error.model';
import { AuditService } from './audit.service';

describe('AuditService', () => {
  let service: AuditService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(withInterceptors([authInterceptor, errorInterceptor])),
        provideHttpClientTesting(),
        { provide: API_BASE_URL, useValue: '/api/' },
      ],
    });
    service = TestBed.inject(AuditService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('pide la primera página sin filtros', () => {
    service.list({}, 1, 25).subscribe();

    const request = http.expectOne((r) => r.url === '/api/admin/audit/');
    expect(request.request.method).toBe('GET');
    expect(request.request.params.get('page_size')).toBe('25');
    expect(request.request.params.has('page')).toBe(false);
    request.flush(buildEventPage([]));
  });

  it('envía solo los filtros con valor y la página pedida', () => {
    service
      .list({ date_from: '2026-10-01', action: 'LOGIN', result: 'FAILURE' }, 2, 25)
      .subscribe();

    const params = http.expectOne((r) => r.url === '/api/admin/audit/').request.params;
    expect(params.get('date_from')).toBe('2026-10-01');
    expect(params.get('action')).toBe('LOGIN');
    expect(params.get('result')).toBe('FAILURE');
    expect(params.get('page')).toBe('2');
    expect(params.has('actor')).toBe(false);
    expect(params.has('manuscript')).toBe(false);
  });

  it('entrega la página tal como llega', () => {
    let count = 0;
    service.list({}).subscribe((page) => (count = page.results.length));

    http.expectOne((r) => r.url === '/api/admin/audit/').flush(buildEventPage([buildEvent()]));

    expect(count).toBe(1);
  });

  it('pide el detalle por el id público del evento', () => {
    let can: boolean | undefined;
    service.get(EVENT_ID).subscribe((entry) => (can = entry.can_authorize_correction));

    const request = http.expectOne(`/api/admin/audit/${EVENT_ID}/`);
    expect(request.request.method).toBe('GET');
    request.flush(buildEventDetail({ can_authorize_correction: true }));

    expect(can).toBe(true);
  });

  it('normaliza un 403 a ApiError', () => {
    let error: ApiError | undefined;
    service.list({}).subscribe({ error: (e: ApiError) => (error = e) });

    http
      .expectOne((r) => r.url === '/api/admin/audit/')
      .flush(
        { error: { code: 'FORBIDDEN', message: 'No autorizado.' } },
        { status: 403, statusText: 'Forbidden' },
      );

    expect(error?.status).toBe(403);
  });

  it('normaliza un 404 del detalle a ApiError', () => {
    let error: ApiError | undefined;
    service.get(EVENT_ID).subscribe({ error: (e: ApiError) => (error = e) });

    http
      .expectOne(`/api/admin/audit/${EVENT_ID}/`)
      .flush({ error: { code: 'NOT_FOUND', message: 'No encontrado.' } }, { status: 404, statusText: 'Not Found' });

    expect(error?.status).toBe(404);
  });
});
