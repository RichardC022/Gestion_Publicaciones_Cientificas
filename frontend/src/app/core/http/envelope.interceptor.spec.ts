import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { successEnvelope } from '../testing/api-envelope.fixtures';
import { envelopeInterceptor } from './envelope.interceptor';

describe('envelopeInterceptor', () => {
  let client: HttpClient;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(withInterceptors([envelopeInterceptor])),
        provideHttpClientTesting(),
      ],
    });
    client = TestBed.inject(HttpClient);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  it('entrega `data` de un éxito', () => {
    let body: unknown;
    client.get('/api/v1/auth/me/').subscribe((value) => (body = value));

    httpMock.expectOne('/api/v1/auth/me/').flush(successEnvelope({ user: { id: 'u-1' } }));

    expect(body).toEqual({ user: { id: 'u-1' } });
  });

  it('reconstruye la página { count, next, previous, results } desde meta.pagination', () => {
    let body: unknown;
    client.get('/api/v1/manuscripts/').subscribe((value) => (body = value));

    httpMock.expectOne('/api/v1/manuscripts/').flush(
      successEnvelope([{ id: 'a' }], {
        pagination: { count: 41, next: '/api/v1/manuscripts/?page=2', previous: null },
      }),
    );

    expect(body).toEqual({
      count: 41,
      next: '/api/v1/manuscripts/?page=2',
      previous: null,
      results: [{ id: 'a' }],
    });
  });

  it('conserva los datos extra de la vista que viajan en meta (diagnosis)', () => {
    let body: { diagnosis?: unknown } | undefined;
    client.get('/api/v1/editor/reviewers/').subscribe((value) => (body = value as typeof body));

    httpMock.expectOne('/api/v1/editor/reviewers/').flush(
      successEnvelope([], {
        pagination: { count: 0, next: null, previous: null },
        diagnosis: { reviewers_total: 3 },
      }),
    );

    expect(body?.diagnosis).toEqual({ reviewers_total: 3 });
  });

  it('deja intactos los cuerpos que no cumplen el contrato', () => {
    let body: unknown;
    client.get('/api/v1/otra/').subscribe((value) => (body = value));

    httpMock.expectOne('/api/v1/otra/').flush({ status: 'ok' });

    expect(body).toEqual({ status: 'ok' });
  });

  it('no toca las descargas Blob', async () => {
    let body: unknown;
    client.get('/api/v1/catalog/X/document/', { responseType: 'blob' }).subscribe((v) => (body = v));

    httpMock
      .expectOne('/api/v1/catalog/X/document/')
      .flush(new Blob(['%PDF'], { type: 'application/pdf' }));

    expect(body instanceof Blob).toBe(true);
  });
});
