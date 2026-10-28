import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import {
  buildAssignmentDetail,
  buildAssignmentPage,
  buildAssignmentRow,
} from '../../features/reviewer/testing/reviewer.fixtures';
import { errorEnvelope } from '../../features/author/testing/manuscript.fixtures';
import { API_BASE_URL } from '../http/api-base-url.token';
import { ApiError } from '../models/api-error.model';
import { genericDocumentName, hasDetail } from '../models/reviewer.model';
import { ReviewerService, serverOffset } from './reviewer.service';

describe('ReviewerService', () => {
  let service: ReviewerService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: API_BASE_URL, useValue: '/api/' },
      ],
    });
    service = TestBed.inject(ReviewerService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  describe('listAssignments', () => {
    it('pide la bandeja propia con la página y el tamaño', () => {
      const page = buildAssignmentPage([buildAssignmentRow()]);
      let result: unknown;
      service.listAssignments(2, 20).subscribe((value) => (result = value));

      const request = http.expectOne((r) => r.url === '/api/reviewer/assignments/');
      expect(request.request.method).toBe('GET');
      expect(request.request.params.get('page')).toBe('2');
      expect(request.request.params.get('page_size')).toBe('20');
      request.flush(page);

      expect(result).toEqual(page);
    });

    it('en la primera página no envía el parámetro page', () => {
      service.listAssignments().subscribe();

      const request = http.expectOne((r) => r.url === '/api/reviewer/assignments/');
      expect(request.request.params.has('page')).toBe(false);
      request.flush(buildAssignmentPage([]));
    });

    it('traduce un error del backend a ApiError', () => {
      let error: ApiError | undefined;
      service.listAssignments().subscribe({ error: (e: ApiError) => (error = e) });

      http
        .expectOne((r) => r.url === '/api/reviewer/assignments/')
        .flush(errorEnvelope('FORBIDDEN', 'Acceso denegado.'), {
          status: 403,
          statusText: 'Forbidden',
        });

      expect(error?.status).toBe(403);
      expect(error?.code).toBe('FORBIDDEN');
    });
  });

  describe('getAssignment', () => {
    it('devuelve el detalle y la diferencia con el reloj del servidor', () => {
      vi.useFakeTimers();
      vi.setSystemTime(new Date('2026-10-27T12:00:00Z'));
      try {
        const detail = buildAssignmentDetail();
        let snapshot: { serverOffsetMs: number } | undefined;
        service.getAssignment('a-1').subscribe((value) => (snapshot = value));

        http
          .expectOne('/api/reviewer/assignments/a-1/')
          .flush(detail, { headers: { Date: 'Tue, 27 Oct 2026 12:00:30 GMT' } });

        expect(snapshot).toEqual({ assignment: detail, serverOffsetMs: 30_000 });
      } finally {
        vi.useRealTimers();
      }
    });

    it('sin cabecera Date la diferencia es cero', () => {
      let offset: number | undefined;
      service.getAssignment('a-1').subscribe((value) => (offset = value.serverOffsetMs));

      http.expectOne('/api/reviewer/assignments/a-1/').flush(buildAssignmentDetail());

      expect(offset).toBe(0);
    });

    it('una asignación ajena responde 404 sin revelar nada más', () => {
      let error: ApiError | undefined;
      service.getAssignment('ajena').subscribe({ error: (e: ApiError) => (error = e) });

      http
        .expectOne('/api/reviewer/assignments/ajena/')
        .flush(errorEnvelope('NOT_FOUND', 'No encontrado.'), {
          status: 404,
          statusText: 'Not Found',
        });

      expect(error?.status).toBe(404);
      expect(error?.userMessage).toContain('no existe o no está disponible');
    });
  });

  describe('downloadDocument', () => {
    const PDF = new Blob(['%PDF-1.7'], { type: 'application/pdf' });

    it('pide el PDF sanitizado de la asignación como Blob', () => {
      let blob: Blob | undefined;
      service.downloadDocument('a-1', 'GPC-2026-000001', 1).subscribe((v) => (blob = v.blob));

      const request = http.expectOne('/api/reviewer/assignments/a-1/document/');
      expect(request.request.method).toBe('GET');
      expect(request.request.responseType).toBe('blob');
      request.flush(PDF);

      expect(blob).toBe(PDF);
    });

    it('usa un nombre genérico aunque el servidor sugiera otro', () => {
      let filename = '';
      service
        .downloadDocument('a-1', 'GPC-2026-000001', 3)
        .subscribe((value) => (filename = value.filename));

      http.expectOne('/api/reviewer/assignments/a-1/document/').flush(PDF, {
        headers: { 'Content-Disposition': 'attachment; filename="ana-lopez-articulo.pdf"' },
      });

      expect(filename).toBe('manuscript-GPC-2026-000001-v3.pdf');
      expect(filename).not.toContain('ana');
    });

    it('un 410 con cuerpo Blob se convierte al envelope del backend', async () => {
      let error: ApiError | undefined;
      service
        .downloadDocument('a-1', 'GPC-2026-000001', 1)
        .subscribe({ error: (e: ApiError) => (error = e) });

      http
        .expectOne('/api/reviewer/assignments/a-1/document/')
        .flush(new Blob([JSON.stringify(errorEnvelope('STATE_CONFLICT', 'Ya no disponible.'))]), {
          status: 410,
          statusText: 'Gone',
        });
      await vi.waitFor(() => expect(error).toBeDefined());

      expect(error?.status).toBe(410);
      expect(error?.code).toBe('STATE_CONFLICT');
    });
  });
});

describe('serverOffset', () => {
  it('es la diferencia entre la hora del servidor y la del navegador', () => {
    const now = Date.parse('2026-10-27T12:00:00Z');

    expect(serverOffset('Tue, 27 Oct 2026 12:01:00 GMT', now)).toBe(60_000);
    expect(serverOffset('Tue, 27 Oct 2026 11:59:00 GMT', now)).toBe(-60_000);
  });

  it.each([null, '', 'no es una fecha'])('con %j no corrige nada', (header) => {
    expect(serverOffset(header)).toBe(0);
  });
});

describe('reviewer.model', () => {
  it('solo las asignaciones activas o completadas tienen detalle', () => {
    expect(hasDetail({ status: 'ACTIVE' })).toBe(true);
    expect(hasDetail({ status: 'COMPLETED' })).toBe(true);
    expect(hasDetail({ status: 'REVOKED' })).toBe(false);
    expect(hasDetail({ status: 'EXPIRED' })).toBe(false);
  });

  it('el nombre del PDF se deriva solo del código y la versión', () => {
    expect(genericDocumentName('GPC-2026-000009', 2)).toBe('manuscript-GPC-2026-000009-v2.pdf');
  });
});
