import { provideHttpClient } from '@angular/common/http';
import {
  HttpTestingController,
  TestRequest,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';
import { vi } from 'vitest';

import { API_BASE_URL } from '../../../core/http/api-base-url.token';
import { ReviewerAssignmentDetail } from '../../../core/models/reviewer.model';
import { errorEnvelope } from '../../author/testing/manuscript.fixtures';
import { buildAssignmentDetail } from '../testing/reviewer.fixtures';
import { AssignmentDetailComponent } from './assignment-detail.component';

const DETAIL = '/api/reviewer/assignments/a-1/';
const DOCUMENT = '/api/reviewer/assignments/a-1/document/';
const PAGE_URL = '/app/reviewer/assignments/a-1';
const NOW = new Date('2026-10-27T12:00:00Z');

describe('AssignmentDetailComponent', () => {
  let http: HttpTestingController;

  beforeEach(() => {
    Object.assign(URL, { createObjectURL: vi.fn(() => 'blob:gpc-test'), revokeObjectURL: vi.fn() });
    TestBed.configureTestingModule({
      providers: [
        provideRouter([
          { path: 'app/reviewer/assignments/:id', component: AssignmentDetailComponent },
        ]),
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: API_BASE_URL, useValue: '/api/' },
      ],
    });
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    http.verify();
    vi.useRealTimers();
  });

  const text = (node: Element | null) => (node?.textContent ?? '').replace(/\s+/g, ' ').trim();
  const detailRequest = (): TestRequest => http.expectOne((r) => r.url === DETAIL);

  const open = async (
    detail: ReviewerAssignmentDetail = buildAssignmentDetail({ due_at: '2026-11-10T15:00:00Z' }),
  ) => {
    const harness = await RouterTestingHarness.create();
    await harness.navigateByUrl(PAGE_URL, AssignmentDetailComponent);
    const element = harness.routeNativeElement as HTMLElement;
    const settle = async () => {
      await harness.fixture.whenStable();
      harness.detectChanges();
    };
    detailRequest().flush(detail);
    await settle();
    return { harness, element, settle };
  };

  const button = (element: HTMLElement, label: string) =>
    Array.from(element.querySelectorAll<HTMLButtonElement>('button')).find(
      (b) => text(b) === label,
    );
  const evaluateLink = (element: HTMLElement) =>
    Array.from(element.querySelectorAll<HTMLAnchorElement>('a')).find(
      (a) => text(a) === 'Evaluar manuscrito',
    );

  describe('contenido', () => {
    it('muestra código, título, resumen, área, ronda, versión y plazo', async () => {
      const { element } = await open();

      expect(text(element.querySelector('.detail-code'))).toBe('GPC-2026-000001');
      expect(text(element.querySelector('h1'))).toBe('Efecto del clima en cultivos andinos');
      expect(text(element.querySelector('.prose'))).toBe('Resumen del estudio de campo.');
      const data = text(element.querySelector('.data'));
      expect(data).toContain('Agronomía');
      expect(data).toContain('clima, cultivos');
      expect(data).toContain('v1, enviada el 20/10/2026 10:30');
      expect(text(element.querySelector('.detail-badges'))).toContain('Ronda 0');
      expect(text(element.querySelector('.detail-badges'))).toContain('Versión v1');
      expect(text(element.querySelector('app-deadline-countdown'))).toContain('10/11/2026 10:00');
    });

    it('declara el doble ciego y no contiene campos de autoría', async () => {
      const { element } = await open();

      expect(text(element)).toContain('no se muestra información de los autores');
      const headings = Array.from(element.querySelectorAll('dt, th, h2, h3')).map((n) => text(n));
      expect(headings.join(' | ')).not.toMatch(/autor(?!ía)|filiaci|correo|contacto|original/i);
    });

    it('no pinta ningún dato de autoría ni archivo original aunque la respuesta lo trajera', async () => {
      const leaky = {
        ...buildAssignmentDetail(),
        authors: [{ full_name: 'Ana López Reservada', email: 'ana@unl.edu.ec' }],
        manuscript: {
          ...buildAssignmentDetail().manuscript,
          authors: [{ full_name: 'Ana López Reservada', affiliation: 'Universidad Secreta' }],
          created_by: 'ana@unl.edu.ec',
        },
        version: {
          ...buildAssignmentDetail().version,
          original_filename: 'ana-lopez-articulo.pdf',
          original_file_path: '/storage/original.pdf',
        },
      } as ReviewerAssignmentDetail;

      const { element } = await open(leaky);

      const html = element.innerHTML;
      for (const secret of [
        'Ana López Reservada',
        'ana@unl.edu.ec',
        'Universidad Secreta',
        'ana-lopez-articulo',
        'original.pdf',
      ]) {
        expect(html).not.toContain(secret);
      }
    });

    it('no ofrece enlaces al PDF original ni a rutas de almacenamiento', async () => {
      const { element } = await open();

      const links = Array.from(element.querySelectorAll('a')).map((a) => a.getAttribute('href'));
      expect(links.join(' ')).not.toMatch(/original|storage|versions|\.pdf/i);
    });

    it('una asignación ajena o inexistente muestra el error genérico', async () => {
      const harness = await RouterTestingHarness.create();
      await harness.navigateByUrl(PAGE_URL, AssignmentDetailComponent);
      detailRequest().flush(errorEnvelope('NOT_FOUND', 'No encontrado.'), {
        status: 404,
        statusText: 'Not Found',
      });
      await harness.fixture.whenStable();
      harness.detectChanges();

      const element = harness.routeNativeElement as HTMLElement;
      expect(text(element.querySelector('[role="alert"]'))).toContain(
        'no existe o no está disponible',
      );
      expect(element.querySelector('h1')).toBeNull();
    });
  });

  describe('documento', () => {
    let clicked: HTMLAnchorElement[];
    let click: ReturnType<typeof vi.spyOn>;

    beforeEach(() => {
      clicked = [];
      click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (
        this: HTMLAnchorElement,
      ) {
        clicked.push(this);
      });
    });

    afterEach(() => click.mockRestore());

    const pdf = () => new Blob(['%PDF-1.7'], { type: 'application/pdf' });

    it('no pide el PDF al abrir el detalle: cada lectura queda auditada', async () => {
      await open();

      http.expectNone(DOCUMENT);
    });

    it('descarga el PDF sanitizado de la asignación con un nombre genérico', async () => {
      const { element, settle } = await open();

      button(element, 'Descargar PDF')!.click();
      await settle();
      const request = http.expectOne(DOCUMENT);
      expect(request.request.responseType).toBe('blob');
      request.flush(pdf(), {
        headers: { 'Content-Disposition': 'attachment; filename="ana-lopez-articulo.pdf"' },
      });
      await settle();

      expect(clicked).toHaveLength(1);
      expect(clicked[0].download).toBe('manuscript-GPC-2026-000001-v1.pdf');
    });

    it('el visor muestra el PDF y se puede ocultar sin volver a pedirlo', async () => {
      const { element, settle } = await open();

      button(element, 'Ver documento')!.click();
      await settle();
      http.expectOne(DOCUMENT).flush(pdf());
      await settle();

      expect(element.querySelector('app-pdf-viewer iframe')).not.toBeNull();
      expect(button(element, 'Ocultar documento')).toBeDefined();

      button(element, 'Ocultar documento')!.click();
      await settle();
      expect(element.querySelector('app-pdf-viewer')).toBeNull();

      button(element, 'Ver documento')!.click();
      await settle();
      http.expectNone(DOCUMENT);
      expect(element.querySelector('app-pdf-viewer iframe')).not.toBeNull();
    });

    it('tras ver el PDF, descargarlo reutiliza el ya obtenido', async () => {
      const { element, settle } = await open();

      button(element, 'Ver documento')!.click();
      await settle();
      http.expectOne(DOCUMENT).flush(pdf());
      await settle();
      button(element, 'Descargar PDF')!.click();
      await settle();

      http.expectNone(DOCUMENT);
      expect(clicked).toHaveLength(1);
    });

    it('mientras descarga no admite una segunda petición', async () => {
      const { element, settle } = await open();

      button(element, 'Descargar PDF')!.click();
      await settle();

      expect(button(element, 'Descargar PDF')!.disabled).toBe(true);
      http.expectOne(DOCUMENT).flush(pdf());
    });

    it('si falla lo explica y deja volver a intentar', async () => {
      const { element, settle } = await open();

      button(element, 'Descargar PDF')!.click();
      await settle();
      http
        .expectOne(DOCUMENT)
        .flush(new Blob([JSON.stringify(errorEnvelope('AUDIT_UNAVAILABLE', 'Sin auditoría.'))]), {
          status: 503,
          statusText: 'Service Unavailable',
        });
      await new Promise((resolve) => setTimeout(resolve));
      await settle();

      expect(element.querySelector('.document-error[role="alert"]')).not.toBeNull();
      expect(clicked).toHaveLength(0);
      expect(button(element, 'Descargar PDF')!.disabled).toBe(false);
    });

    it('con 410 vuelve a leer la asignación y retira el documento', async () => {
      const { element, settle } = await open();

      button(element, 'Ver documento')!.click();
      await settle();
      http
        .expectOne(DOCUMENT)
        .flush(new Blob([JSON.stringify(errorEnvelope('STATE_CONFLICT', 'Ya no disponible.'))]), {
          status: 410,
          statusText: 'Gone',
        });
      await new Promise((resolve) => setTimeout(resolve));
      detailRequest().flush(
        buildAssignmentDetail({
          status: 'REVOKED',
          state: 'REVOKED',
          document_url: null,
        }),
      );
      await settle();

      expect(text(element)).toContain('El documento ya no está disponible');
      expect(button(element, 'Ver documento')).toBeUndefined();
    });

    it('una asignación completada no ofrece el documento', async () => {
      const { element } = await open(
        buildAssignmentDetail({
          status: 'COMPLETED',
          state: 'EVALUATED',
          completed_at: '2026-10-25T20:00:00Z',
          document_url: null,
        }),
      );

      expect(button(element, 'Descargar PDF')).toBeUndefined();
      expect(text(element)).toContain('El documento ya no está disponible');
    });
  });

  describe('plazo y evaluación', () => {
    it('con plazo vigente enlaza a la evaluación', async () => {
      const { element } = await open();

      expect(evaluateLink(element)?.getAttribute('href')).toBe(
        '/app/reviewer/assignments/a-1/evaluate',
      );
    });

    it('si el servidor la dio por vencida deshabilita la evaluación', async () => {
      const { element } = await open(buildAssignmentDetail({ is_overdue: true, state: 'OVERDUE' }));

      expect(evaluateLink(element)).toBeUndefined();
      const disabled = button(element, 'Evaluar manuscrito')!;
      expect(disabled.disabled).toBe(true);
      expect(text(element)).toContain('El plazo venció');
      expect(text(element.querySelector('app-deadline-countdown'))).toContain('Plazo vencido');
    });

    it('al vencer el plazo con la vista abierta deshabilita la evaluación', async () => {
      vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval', 'Date'] });
      vi.setSystemTime(NOW);
      const { element, settle } = await open(
        buildAssignmentDetail({ due_at: '2026-10-27T12:00:02Z' }),
      );
      expect(evaluateLink(element)).toBeDefined();

      vi.advanceTimersByTime(2_000);
      await settle();

      expect(evaluateLink(element)).toBeUndefined();
      expect(button(element, 'Evaluar manuscrito')!.disabled).toBe(true);
      expect(text(element.querySelector('app-deadline-countdown'))).toContain('Plazo vencido');
    });

    it('cuenta contra la hora del servidor, no la del navegador', async () => {
      vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval', 'Date'] });
      vi.setSystemTime(NOW);
      const harness = await RouterTestingHarness.create();
      await harness.navigateByUrl(PAGE_URL, AssignmentDetailComponent);
      // El servidor va 10 minutos adelantado respecto del navegador.
      detailRequest().flush(buildAssignmentDetail({ due_at: '2026-10-27T12:30:00Z' }), {
        headers: { Date: 'Tue, 27 Oct 2026 12:10:00 GMT' },
      });
      await harness.fixture.whenStable();
      harness.detectChanges();

      const element = harness.routeNativeElement as HTMLElement;
      expect(text(element.querySelector('.countdown__value'))).toContain('20:00');
    });

    it('una asignación completada muestra cuándo se envió y no ofrece evaluar', async () => {
      const { element } = await open(
        buildAssignmentDetail({
          status: 'COMPLETED',
          state: 'EVALUATED',
          completed_at: '2026-10-25T20:00:00Z',
          document_url: null,
        }),
      );

      expect(text(element)).toContain('Evaluación enviada el 25/10/2026 15:00');
      expect(element.querySelector('app-deadline-countdown')).toBeNull();
      expect(evaluateLink(element)).toBeUndefined();
      expect(
        Array.from(element.querySelectorAll('a')).some((a) => text(a) === 'Ver mi historial'),
      ).toBe(true);
    });
  });
});
