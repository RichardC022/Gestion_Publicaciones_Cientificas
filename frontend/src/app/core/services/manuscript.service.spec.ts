import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import {
  buildManuscript,
  buildPage,
  errorEnvelope,
} from '../../features/author/testing/manuscript.fixtures';
import { API_BASE_URL } from '../http/api-base-url.token';
import { ApiError } from '../models/api-error.model';
import { ManuscriptPayload } from '../models/manuscript.model';
import { ManuscriptService } from './manuscript.service';

const PAYLOAD: ManuscriptPayload = {
  title: 'Título',
  abstract: 'Resumen',
  keywords: ['clima'],
  area: 'Agronomía',
  language: 'es',
  authors: [
    {
      full_name: 'Ana López',
      email: 'a.lopez@unl.edu.ec',
      affiliation: 'UNL',
      is_corresponding: true,
    },
  ],
};

describe('ManuscriptService', () => {
  let service: ManuscriptService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: API_BASE_URL, useValue: '/api/' },
      ],
    });
    service = TestBed.inject(ManuscriptService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  describe('list', () => {
    it('consulta /api/manuscripts/ sin parámetros vacíos', () => {
      let result: unknown;
      service.list({}).subscribe((page) => (result = page));

      const request = http.expectOne('/api/manuscripts/');
      expect(request.request.method).toBe('GET');
      expect(request.request.params.keys()).toEqual([]);
      request.flush(buildPage([buildManuscript()]));

      expect((result as { count: number }).count).toBe(1);
    });

    it('envía solo los filtros con valor', () => {
      service
        .list({
          status: 'DRAFT',
          date_from: '2026-10-01',
          date_to: '',
          archived: true,
          page: 2,
          page_size: 20,
        })
        .subscribe();

      const request = http.expectOne((r) => r.url === '/api/manuscripts/');
      expect(request.request.params.get('status')).toBe('DRAFT');
      expect(request.request.params.get('date_from')).toBe('2026-10-01');
      expect(request.request.params.has('date_to')).toBe(false);
      expect(request.request.params.get('archived')).toBe('true');
      expect(request.request.params.get('page')).toBe('2');
      expect(request.request.params.get('page_size')).toBe('20');
      request.flush(buildPage([]));
    });

    it('no envía archived cuando es falso', () => {
      service.list({ archived: false }).subscribe();

      const request = http.expectOne((r) => r.url === '/api/manuscripts/');
      expect(request.request.params.has('archived')).toBe(false);
      request.flush(buildPage([]));
    });
  });

  describe('get', () => {
    it('devuelve el manuscrito con su ETag', () => {
      let snapshot: { manuscript: { id: string }; etag: string | null } | undefined;
      service.get('m-1').subscribe((value) => (snapshot = value));

      const request = http.expectOne('/api/manuscripts/m-1/');
      expect(request.request.method).toBe('GET');
      request.flush(buildManuscript(), { headers: { ETag: '"3"' } });

      expect(snapshot?.manuscript.id).toBe('m-1');
      expect(snapshot?.etag).toBe('"3"');
    });

    it('el ETag es nulo si el servidor no lo envía', () => {
      let etag: string | null | undefined;
      service.get('m-1').subscribe((value) => (etag = value.etag));

      http.expectOne('/api/manuscripts/m-1/').flush(buildManuscript());

      expect(etag).toBeNull();
    });
  });

  describe('create', () => {
    it('envía el borrador por POST y devuelve el ETag', () => {
      let snapshot: { etag: string | null } | undefined;
      service.create(PAYLOAD).subscribe((value) => (snapshot = value));

      const request = http.expectOne('/api/manuscripts/');
      expect(request.request.method).toBe('POST');
      expect(request.request.body).toEqual(PAYLOAD);
      request.flush(buildManuscript({ id: 'nuevo' }), {
        status: 201,
        statusText: 'Created',
        headers: { ETag: '"0"' },
      });

      expect(snapshot?.etag).toBe('"0"');
    });
  });

  describe('update', () => {
    it('edita por PATCH reenviando el ETag en If-Match', () => {
      service.update('m-1', PAYLOAD, '"2"').subscribe();

      const request = http.expectOne('/api/manuscripts/m-1/');
      expect(request.request.method).toBe('PATCH');
      expect(request.request.headers.get('If-Match')).toBe('"2"');
      expect(request.request.body).toEqual(PAYLOAD);
      request.flush(buildManuscript(), { headers: { ETag: '"3"' } });
    });
  });

  describe('errores', () => {
    it('normaliza un 404 a ApiError con el código del envelope', () => {
      let error: ApiError | undefined;
      service.get('ajeno').subscribe({ error: (e: ApiError) => (error = e) });

      http
        .expectOne('/api/manuscripts/ajeno/')
        .flush(errorEnvelope('NOT_FOUND', 'No encontrado.'), {
          status: 404,
          statusText: 'Not Found',
        });

      expect(error?.status).toBe(404);
      expect(error?.code).toBe('NOT_FOUND');
      expect(error?.requestId).toBe('rid-1');
    });

    it('conserva los detalles de validación de un 400', () => {
      let error: ApiError | undefined;
      service.create(PAYLOAD).subscribe({ error: (e: ApiError) => (error = e) });

      http.expectOne('/api/manuscripts/').flush(
        errorEnvelope('VALIDATION_ERROR', 'Los datos enviados no son válidos.', {
          authors: ['Debe indicar exactamente un autor responsable.'],
        }),
        { status: 400, statusText: 'Bad Request' },
      );

      expect(error?.details).toEqual({
        authors: ['Debe indicar exactamente un autor responsable.'],
      });
    });

    it('distingue el conflicto de versión del 409 genérico', () => {
      let error: ApiError | undefined;
      service.update('m-1', PAYLOAD, '"0"').subscribe({ error: (e: ApiError) => (error = e) });

      http
        .expectOne('/api/manuscripts/m-1/')
        .flush(errorEnvelope('VERSION_CONFLICT', 'El manuscrito cambió.', { lock_version: 1 }), {
          status: 409,
          statusText: 'Conflict',
        });

      expect(error?.code).toBe('VERSION_CONFLICT');
    });
  });
});
