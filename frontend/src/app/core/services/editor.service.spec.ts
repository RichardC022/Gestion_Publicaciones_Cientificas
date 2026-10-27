import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import {
  buildAssignment,
  buildEvaluation,
  buildSubmissionDetail,
  buildSubmissionPage,
  buildSubmissionRow,
  buildVerdict,
  buildVerdictResult,
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

describe('EditorService · asignaciones', () => {
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

  it('lista los Revisores elegibles del manuscrito y conserva el diagnóstico', () => {
    const diagnosis = { reviewers: 3, conflict: 1, no_profile: 0, unavailable: 1, other_area: 1 };
    let page: { diagnosis?: unknown } | undefined;
    service.listEligibleReviewers('s-1').subscribe((value) => (page = value));

    const request = http.expectOne((r) => r.url === '/api/editor/reviewers/');
    expect(request.request.method).toBe('GET');
    expect(request.request.params.get('manuscript_id')).toBe('s-1');
    expect(request.request.params.get('page_size')).toBe('100');
    request.flush({ count: 0, next: null, previous: null, results: [], diagnosis });

    expect(page?.diagnosis).toEqual(diagnosis);
  });

  it('asigna al Revisor y devuelve la fecha límite fijada por el servidor', () => {
    const assignment = buildAssignment({ due_at: '2026-11-11T15:00:00Z' });
    let result: { due_at: string } | undefined;
    service.assignReviewer('s-1', 'r-1').subscribe((value) => (result = value));

    const request = http.expectOne('/api/editor/manuscripts/s-1/assignments/');
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual({ reviewer_id: 'r-1' });
    request.flush(assignment, { status: 201, statusText: 'Created' });

    expect(result?.due_at).toBe('2026-11-11T15:00:00Z');
  });

  it('una segunda asignación activa llega como 409 ASSIGNMENT_CONFLICT', () => {
    let error: ApiError | undefined;
    service.assignReviewer('s-1', 'r-2').subscribe({ error: (e: ApiError) => (error = e) });

    http
      .expectOne('/api/editor/manuscripts/s-1/assignments/')
      .flush(errorEnvelope('ASSIGNMENT_CONFLICT', 'El manuscrito ya tiene un Revisor activo.'), {
        status: 409,
        statusText: 'Conflict',
      });

    expect(error?.status).toBe(409);
    expect(error?.code).toBe('ASSIGNMENT_CONFLICT');
  });

  it('revoca con causa y motivo', () => {
    let status: string | undefined;
    service
      .revokeAssignment('a-1', 'ASSIGNMENT_ERROR', 'Se asignó al Revisor equivocado.')
      .subscribe((value) => (status = value.status));

    const request = http.expectOne('/api/editor/assignments/a-1/revoke/');
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual({
      cause: 'ASSIGNMENT_ERROR',
      reason: 'Se asignó al Revisor equivocado.',
    });
    request.flush(buildAssignment({ status: 'REVOKED' }));

    expect(status).toBe('REVOKED');
  });

  it('una causa temprana inválida llega como 400', () => {
    let error: ApiError | undefined;
    service.revokeAssignment('a-1', 'OVERDUE', 'x').subscribe({ error: (e: ApiError) => (error = e) });

    http
      .expectOne('/api/editor/assignments/a-1/revoke/')
      .flush(errorEnvelope('VALIDATION_ERROR', 'Causa inválida.'), {
        status: 400,
        statusText: 'Bad Request',
      });

    expect(error?.status).toBe(400);
  });
});

describe('EditorService · veredicto', () => {
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

  const page = <T>(results: T[]) => ({ count: results.length, next: null, previous: null, results });

  it('lista las evaluaciones finales del manuscrito con la identidad del Revisor', () => {
    let reviewer: string | undefined;
    service.listEvaluations('s-1').subscribe((value) => (reviewer = value.results[0].reviewer.full_name));

    const request = http.expectOne((r) => r.url === '/api/editor/manuscripts/s-1/evaluations/');
    expect(request.request.method).toBe('GET');
    expect(request.request.params.get('page_size')).toBe('100');
    request.flush(page([buildEvaluation()]));

    expect(reviewer).toBe('Marta Ruiz');
  });

  it('lista el historial de veredictos', () => {
    let decisions: string[] = [];
    service.listVerdicts('s-1').subscribe((value) => (decisions = value.results.map((v) => v.decision)));

    http
      .expectOne((r) => r.url === '/api/editor/manuscripts/s-1/verdicts/')
      .flush(page([buildVerdict({ decision: 'REQUIRES_CORRECTIONS' }), buildVerdict({ decision: 'ACCEPTED' })]));

    expect(decisions).toEqual(['REQUIRES_CORRECTIONS', 'ACCEPTED']);
  });

  it('registra el veredicto con If-Match e Idempotency-Key y devuelve el ETag nuevo', () => {
    const result = buildVerdictResult();
    let registered: { etag: string | null } | undefined;
    service
      .createVerdict(
        's-1',
        { decision: 'ACCEPTED', justification: null, observations: null },
        '"4"',
        'clave-1',
      )
      .subscribe((value) => (registered = value));

    const request = http.expectOne('/api/editor/manuscripts/s-1/verdicts/');
    expect(request.request.method).toBe('POST');
    expect(request.request.headers.get('If-Match')).toBe('"4"');
    expect(request.request.headers.get('Idempotency-Key')).toBe('clave-1');
    expect(request.request.body).toEqual({
      decision: 'ACCEPTED',
      justification: null,
      observations: null,
    });
    request.flush(result, { status: 201, statusText: 'Created', headers: { ETag: '"5"' } });

    expect(registered).toEqual({ result, etag: '"5"' });
  });

  it('un segundo veredicto llega como 409 VERDICT_CONFLICT', () => {
    let error: ApiError | undefined;
    service
      .createVerdict('s-1', { decision: 'ACCEPTED', justification: null, observations: null }, '"4"', 'k')
      .subscribe({ error: (e: ApiError) => (error = e) });

    http
      .expectOne('/api/editor/manuscripts/s-1/verdicts/')
      .flush(errorEnvelope('VERDICT_CONFLICT', 'La versión evaluada ya tiene un veredicto.'), {
        status: 409,
        statusText: 'Conflict',
      });

    expect(error?.status).toBe(409);
    expect(error?.code).toBe('VERDICT_CONFLICT');
  });

  it('un editor con conflicto de interés recibe 403', () => {
    let error: ApiError | undefined;
    service
      .createVerdict('s-1', { decision: 'ACCEPTED', justification: null, observations: null }, '"4"', 'k')
      .subscribe({ error: (e: ApiError) => (error = e) });

    http
      .expectOne('/api/editor/manuscripts/s-1/verdicts/')
      .flush(errorEnvelope('FORBIDDEN', 'Conflicto de interés.'), {
        status: 403,
        statusText: 'Forbidden',
      });

    expect(error?.status).toBe(403);
  });
});

describe('EditorService · vencidas', () => {
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

  it('pide solo la lectura de las vencidas, con la página pedida', () => {
    let codes: string[] = [];
    service.listExpiredAssignments(2, 20).subscribe(
      (value) => (codes = value.results.map((a) => a.manuscript_code)),
    );

    const request = http.expectOne((r) => r.url === '/api/editor/assignments/expired/');
    expect(request.request.method).toBe('GET');
    expect(request.request.params.get('page')).toBe('2');
    expect(request.request.params.get('page_size')).toBe('20');
    request.flush({
      count: 1,
      next: null,
      previous: null,
      results: [buildAssignment({ status: 'EXPIRED', manuscript_code: 'GPC-2026-000009' })],
    });

    expect(codes).toEqual(['GPC-2026-000009']);
  });

  it('la primera página no envía el parámetro page', () => {
    service.listExpiredAssignments().subscribe();

    const request = http.expectOne((r) => r.url === '/api/editor/assignments/expired/');
    expect(request.request.params.has('page')).toBe(false);
    request.flush({ count: 0, next: null, previous: null, results: [] });
  });

  it('un rol sin acceso llega como 403', () => {
    let error: ApiError | undefined;
    service.listExpiredAssignments().subscribe({ error: (e: ApiError) => (error = e) });

    http
      .expectOne((r) => r.url === '/api/editor/assignments/expired/')
      .flush(errorEnvelope('FORBIDDEN', 'Acceso denegado.'), { status: 403, statusText: 'Forbidden' });

    expect(error?.status).toBe(403);
  });
});
