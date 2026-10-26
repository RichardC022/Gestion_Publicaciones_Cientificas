import { HttpEventType, provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import {
  buildManuscript,
  buildPage,
  errorEnvelope,
} from '../../features/author/testing/manuscript.fixtures';
import { API_BASE_URL } from '../http/api-base-url.token';
import { ApiError } from '../models/api-error.model';
import { DraftUploadEvent } from '../models/manuscript.model';
import { ManuscriptPayload } from '../models/manuscript.model';
import { ManuscriptService, filenameFrom } from './manuscript.service';

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

  describe('uploadDraft', () => {
    const FILE = new File(['%PDF-1.7 contenido'], 'articulo.pdf', { type: 'application/pdf' });
    const SUMMARY = {
      filename: 'articulo.pdf',
      size_bytes: 18,
      uploaded_at: '2026-10-25T12:00:00Z',
    };

    it('envía el archivo en el campo «file» de un multipart sin fijar Content-Type', () => {
      service.uploadDraft('m-1', FILE).subscribe();

      const request = http.expectOne('/api/manuscripts/m-1/draft-file/');
      expect(request.request.method).toBe('POST');
      expect(request.request.reportProgress).toBe(true);
      const body = request.request.body as FormData;
      expect(body).toBeInstanceOf(FormData);
      expect((body.get('file') as File).name).toBe('articulo.pdf');
      // El navegador añade el boundary; fijarlo a mano rompería el multipart.
      expect(request.request.headers.has('Content-Type')).toBe(false);
      request.flush(SUMMARY, { status: 201, statusText: 'Created' });
    });

    it('emite el avance en porcentaje y luego el resultado', () => {
      const events: DraftUploadEvent[] = [];
      service.uploadDraft('m-1', FILE).subscribe((event) => events.push(event));

      const request = http.expectOne('/api/manuscripts/m-1/draft-file/');
      request.event({ type: HttpEventType.Sent });
      request.event({ type: HttpEventType.UploadProgress, loaded: 50, total: 200 });
      request.event({ type: HttpEventType.UploadProgress, loaded: 200, total: 200 });
      request.flush(SUMMARY, { status: 201, statusText: 'Created' });

      expect(events).toEqual([
        { kind: 'progress', percent: 25 },
        { kind: 'progress', percent: 100 },
        { kind: 'done', draft: SUMMARY, replaced: false },
      ]);
    });

    it('si el navegador no conoce el total, el avance es nulo', () => {
      const events: DraftUploadEvent[] = [];
      service.uploadDraft('m-1', FILE).subscribe((event) => events.push(event));

      const request = http.expectOne('/api/manuscripts/m-1/draft-file/');
      request.event({ type: HttpEventType.UploadProgress, loaded: 50 });
      request.flush(SUMMARY, { status: 201, statusText: 'Created' });

      expect(events[0]).toEqual({ kind: 'progress', percent: null });
    });

    it('el avance nunca supera el 100 %', () => {
      const events: DraftUploadEvent[] = [];
      service.uploadDraft('m-1', FILE).subscribe((event) => events.push(event));

      const request = http.expectOne('/api/manuscripts/m-1/draft-file/');
      request.event({ type: HttpEventType.UploadProgress, loaded: 300, total: 200 });
      request.flush(SUMMARY, { status: 201, statusText: 'Created' });

      expect(events[0]).toEqual({ kind: 'progress', percent: 100 });
    });

    it('un 200 indica que reemplazó un borrador anterior', () => {
      let done: DraftUploadEvent | undefined;
      service.uploadDraft('m-1', FILE).subscribe((event) => (done = event));

      http
        .expectOne('/api/manuscripts/m-1/draft-file/')
        .flush(SUMMARY, { status: 200, statusText: 'OK' });

      expect(done).toEqual({ kind: 'done', draft: SUMMARY, replaced: true });
    });

    it('cancelar la suscripción aborta la solicitud', () => {
      const subscription = service.uploadDraft('m-1', FILE).subscribe();
      const request = http.expectOne('/api/manuscripts/m-1/draft-file/');

      subscription.unsubscribe();

      expect(request.cancelled).toBe(true);
    });

    it.each([
      [413, 'PDF_TOO_LARGE'],
      [415, 'PDF_UNSUPPORTED'],
      [400, 'PDF_INVALID'],
      [409, 'STATE_CONFLICT'],
    ])('normaliza un %s a ApiError con el código %s', (status, code) => {
      let error: ApiError | undefined;
      service.uploadDraft('m-1', FILE).subscribe({ error: (e: ApiError) => (error = e) });

      http
        .expectOne('/api/manuscripts/m-1/draft-file/')
        .flush(errorEnvelope(code, 'Mensaje del servidor.'), { status, statusText: 'Error' });

      expect(error?.status).toBe(status);
      expect(error?.code).toBe(code);
    });
  });

  describe('getHistory', () => {
    it('pide la primera página con 100 eventos y sin parámetro page', () => {
      service.getHistory('m-1').subscribe();

      const request = http.expectOne((r) => r.url === '/api/manuscripts/m-1/history/');
      expect(request.request.method).toBe('GET');
      expect(request.request.params.get('page_size')).toBe('100');
      expect(request.request.params.has('page')).toBe(false);
      request.flush({ count: 0, next: null, previous: null, results: [] });
    });

    it('pide páginas posteriores con page', () => {
      service.getHistory('m-1', 3, 50).subscribe();

      const request = http.expectOne((r) => r.url === '/api/manuscripts/m-1/history/');
      expect(request.request.params.get('page')).toBe('3');
      expect(request.request.params.get('page_size')).toBe('50');
      request.flush({ count: 0, next: null, previous: null, results: [] });
    });

    it('normaliza el error de un manuscrito ajeno', () => {
      let error: ApiError | undefined;
      service.getHistory('ajeno').subscribe({ error: (e: ApiError) => (error = e) });

      http
        .expectOne((r) => r.url === '/api/manuscripts/ajeno/history/')
        .flush(errorEnvelope('NOT_FOUND', 'No encontrado.'), {
          status: 404,
          statusText: 'Not Found',
        });

      expect(error?.code).toBe('NOT_FOUND');
    });
  });

  describe('downloadVersion', () => {
    const PDF = new Blob(['%PDF-1.7'], { type: 'application/pdf' });

    it('pide el archivo como Blob y toma el nombre de Content-Disposition', () => {
      let result: { blob: Blob; filename: string } | undefined;
      service.downloadVersion('m-1', 'v-9', 'respaldo.pdf').subscribe((value) => (result = value));

      const request = http.expectOne('/api/manuscripts/m-1/versions/v-9/file/');
      expect(request.request.method).toBe('GET');
      expect(request.request.responseType).toBe('blob');
      request.flush(PDF, {
        headers: { 'Content-Disposition': 'attachment; filename="GPC-2026-000001-v1.pdf"' },
      });

      expect(result?.filename).toBe('GPC-2026-000001-v1.pdf');
      expect(result?.blob).toBe(PDF);
    });

    it('sin Content-Disposition usa el nombre de respaldo', () => {
      let filename = '';
      service
        .downloadVersion('m-1', 'v-9', 'respaldo.pdf')
        .subscribe((value) => (filename = value.filename));

      http.expectOne('/api/manuscripts/m-1/versions/v-9/file/').flush(PDF);

      expect(filename).toBe('respaldo.pdf');
    });

    it('un error con cuerpo Blob se lee para conservar el envelope del backend', async () => {
      let error: ApiError | undefined;
      service
        .downloadVersion('m-1', 'v-9', 'x.pdf')
        .subscribe({ error: (e: ApiError) => (error = e) });

      const body = new Blob(
        [JSON.stringify(errorEnvelope('AUDIT_UNAVAILABLE', 'Sin auditoría.'))],
        {
          type: 'application/json',
        },
      );
      http
        .expectOne('/api/manuscripts/m-1/versions/v-9/file/')
        .flush(body, { status: 503, statusText: 'Service Unavailable' });
      await vi.waitFor(() => expect(error).toBeDefined());

      expect(error?.status).toBe(503);
      expect(error?.code).toBe('AUDIT_UNAVAILABLE');
      expect(error?.requestId).toBe('rid-1');
    });

    it('un 404 con Blob no revela nada más que el mensaje genérico', async () => {
      let error: ApiError | undefined;
      service
        .downloadVersion('m-1', 'v-9', 'x.pdf')
        .subscribe({ error: (e: ApiError) => (error = e) });

      http
        .expectOne('/api/manuscripts/m-1/versions/v-9/file/')
        .flush(new Blob([JSON.stringify(errorEnvelope('NOT_FOUND', 'No encontrado.'))]), {
          status: 404,
          statusText: 'Not Found',
        });
      await vi.waitFor(() => expect(error).toBeDefined());

      expect(error?.code).toBe('NOT_FOUND');
      expect(error?.userMessage).toContain('no existe o no está disponible');
    });

    it('un error cuyo cuerpo no es JSON se normaliza sin fallar', async () => {
      let error: ApiError | undefined;
      service
        .downloadVersion('m-1', 'v-9', 'x.pdf')
        .subscribe({ error: (e: ApiError) => (error = e) });

      http
        .expectOne('/api/manuscripts/m-1/versions/v-9/file/')
        .flush(new Blob(['<html>Bad Gateway</html>']), { status: 502, statusText: 'Bad Gateway' });
      await vi.waitFor(() => expect(error).toBeDefined());

      expect(error?.status).toBe(502);
      expect(error?.userMessage.length).toBeGreaterThan(0);
    });
  });

  describe('withdraw', () => {
    it('envía el motivo por POST y devuelve el manuscrito dado de baja con su ETag', () => {
      let snapshot: { manuscript: { is_active: boolean }; etag: string | null } | undefined;
      service.withdraw('m-1', 'Ya no deseo continuar.').subscribe((value) => (snapshot = value));

      const request = http.expectOne('/api/manuscripts/m-1/withdraw/');
      expect(request.request.method).toBe('POST');
      expect(request.request.body).toEqual({ reason: 'Ya no deseo continuar.' });
      request.flush(buildManuscript({ is_active: false }), { headers: { ETag: '"5"' } });

      expect(snapshot?.manuscript.is_active).toBe(false);
      expect(snapshot?.etag).toBe('"5"');
    });

    it('sin motivo envía un cuerpo vacío', () => {
      service.withdraw('m-1', null).subscribe();

      const request = http.expectOne('/api/manuscripts/m-1/withdraw/');
      expect(request.request.body).toEqual({});
      request.flush(buildManuscript({ is_active: false }));
    });

    it('conserva el detalle de validación cuando falta el motivo', () => {
      let error: ApiError | undefined;
      service.withdraw('m-1', null).subscribe({ error: (e: ApiError) => (error = e) });

      http.expectOne('/api/manuscripts/m-1/withdraw/').flush(
        errorEnvelope('VALIDATION_ERROR', 'Indique el motivo.', {
          reason: ['Indique el motivo de la baja.'],
        }),
        { status: 400, statusText: 'Bad Request' },
      );

      expect(error?.details).toEqual({ reason: ['Indique el motivo de la baja.'] });
    });

    it('una baja repetida llega como 409', () => {
      let error: ApiError | undefined;
      service.withdraw('m-1', null).subscribe({ error: (e: ApiError) => (error = e) });

      http
        .expectOne('/api/manuscripts/m-1/withdraw/')
        .flush(errorEnvelope('STATE_CONFLICT', 'Ya dado de baja.'), {
          status: 409,
          statusText: 'Conflict',
        });

      expect(error?.status).toBe(409);
    });
  });
});

describe('filenameFrom', () => {
  it.each([
    ['attachment; filename="GPC-2026-000001-v1.pdf"', 'GPC-2026-000001-v1.pdf'],
    ['attachment; filename=articulo.pdf', 'articulo.pdf'],
    ["attachment; filename*=UTF-8''art%C3%ADculo.pdf", 'artículo.pdf'],
    ['attachment; filename="../../etc/passwd.pdf"', 'passwd.pdf'],
    ['attachment; filename="C:\\Users\\x\\a.pdf"', 'a.pdf'],
  ])('lee %s', (header, expected) => {
    expect(filenameFrom(header)).toBe(expected);
  });

  it.each([[null], [''], ['attachment'], ['inline']])(
    'sin nombre en %j devuelve nulo',
    (header) => {
      expect(filenameFrom(header)).toBeNull();
    },
  );
});
