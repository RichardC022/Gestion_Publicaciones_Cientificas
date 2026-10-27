import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import {
  buildSubmissionDetail,
  buildSubmissionPage,
  buildSubmissionRow,
} from '../../features/editor/testing/editor.fixtures';
import { errorEnvelope } from '../../features/author/testing/manuscript.fixtures';
import { API_BASE_URL } from '../http/api-base-url.token';
import { ApiError } from '../models/api-error.model';
import { EditorService } from './editor.service';

describe('EditorService', () => {
  let service: EditorService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: API_BASE_URL, useValue: '/api/' },
      ],
    });
    service = TestBed.inject(EditorService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  describe('listSubmissions', () => {
    it('pide la bandeja del Editor sin parámetros vacíos', () => {
      const page = buildSubmissionPage([buildSubmissionRow()]);
      let result: unknown;
      service
        .listSubmissions({ search: 'clima', area: '', page: 2, page_size: 20 })
        .subscribe((value) => (result = value));

      const request = http.expectOne((r) => r.url === '/api/editor/submissions/');
      expect(request.request.method).toBe('GET');
      expect(request.request.params.get('search')).toBe('clima');
      expect(request.request.params.get('page')).toBe('2');
      expect(request.request.params.get('page_size')).toBe('20');
      expect(request.request.params.has('area')).toBe(false);
      request.flush(page);

      expect(result).toEqual(page);
    });

    it('traduce un error del backend a ApiError', () => {
      let error: ApiError | undefined;
      service.listSubmissions().subscribe({ error: (e: ApiError) => (error = e) });

      http
        .expectOne('/api/editor/submissions/')
        .flush(errorEnvelope('FORBIDDEN', 'Acceso denegado.'), {
          status: 403,
          statusText: 'Forbidden',
        });

      expect(error?.status).toBe(403);
      expect(error?.code).toBe('FORBIDDEN');
    });
  });

  describe('getSubmission', () => {
    it('devuelve el detalle junto con el ETag vigente', () => {
      const detail = buildSubmissionDetail();
      let snapshot: { etag: string | null } | undefined;
      service.getSubmission('s-1').subscribe((value) => (snapshot = value));

      http.expectOne('/api/editor/submissions/s-1/').flush(detail, { headers: { ETag: '"3"' } });

      expect(snapshot).toEqual({ submission: detail, etag: '"3"' });
    });

    it('un envío fuera del ámbito del Editor llega como 404', () => {
      let error: ApiError | undefined;
      service.getSubmission('s-9').subscribe({ error: (e: ApiError) => (error = e) });

      http
        .expectOne('/api/editor/submissions/s-9/')
        .flush(errorEnvelope('NOT_FOUND', 'No encontrado.'), {
          status: 404,
          statusText: 'Not Found',
        });

      expect(error?.status).toBe(404);
    });
  });

  describe('startReview', () => {
    it('hace POST al paso a revisión sin cuerpo de asignación', () => {
      let status: string | undefined;
      service.startReview('s-1').subscribe((result) => (status = result.status));

      const request = http.expectOne('/api/editor/submissions/s-1/start-review/');
      expect(request.request.method).toBe('POST');
      expect(request.request.body).toEqual({});
      request.flush({ id: 's-1', code: 'GPC-2026-000001', status: 'UNDER_REVIEW', assignment: null });

      expect(status).toBe('UNDER_REVIEW');
    });

    it('un envío que ya no está enviado llega como 409', () => {
      let error: ApiError | undefined;
      service.startReview('s-1').subscribe({ error: (e: ApiError) => (error = e) });

      http
        .expectOne('/api/editor/submissions/s-1/start-review/')
        .flush(errorEnvelope('STATE_CONFLICT', 'Solo un manuscrito enviado puede pasar a revisión.'), {
          status: 409,
          statusText: 'Conflict',
        });

      expect(error?.status).toBe(409);
      expect(error?.code).toBe('STATE_CONFLICT');
    });
  });
});
