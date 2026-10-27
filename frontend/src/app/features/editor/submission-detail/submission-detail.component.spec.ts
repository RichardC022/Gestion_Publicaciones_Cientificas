import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';

import { API_BASE_URL } from '../../../core/http/api-base-url.token';
import { SubmissionDetail } from '../../../core/models/editor.model';
import { errorEnvelope } from '../../author/testing/manuscript.fixtures';
import { buildSubmissionDetail } from '../testing/editor.fixtures';
import { SubmissionDetailComponent } from './submission-detail.component';

const DETAIL_URL = '/api/editor/submissions/s-1/';

describe('SubmissionDetailComponent', () => {
  let http: HttpTestingController;

  beforeAll(() => {
    // jsdom no implementa el ciclo abierto/cerrado del diálogo nativo.
    if (typeof HTMLDialogElement.prototype.showModal !== 'function') {
      HTMLDialogElement.prototype.showModal = function (this: HTMLDialogElement) {
        this.setAttribute('open', '');
      };
    }
    if (typeof HTMLDialogElement.prototype.close !== 'function') {
      HTMLDialogElement.prototype.close = function (this: HTMLDialogElement) {
        this.removeAttribute('open');
      };
    }
  });

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideRouter([
          { path: 'app/editor/submissions/:id', component: SubmissionDetailComponent },
        ]),
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: API_BASE_URL, useValue: '/api/' },
      ],
    });
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  const text = (node: Element | null) => (node?.textContent ?? '').replace(/\s+/g, ' ').trim();

  /** Abre el detalle de `s-1` y responde con el envío indicado. */
  const open = async (overrides: Partial<SubmissionDetail> = {}, etag = '"0"') => {
    const harness = await RouterTestingHarness.create();
    await harness.navigateByUrl('/app/editor/submissions/s-1', SubmissionDetailComponent);
    const element = harness.routeNativeElement as HTMLElement;
    const settle = async () => {
      await harness.fixture.whenStable();
      harness.detectChanges();
    };
    http
      .expectOne(DETAIL_URL)
      .flush(buildSubmissionDetail(overrides), { headers: { ETag: etag } });
    await settle();
    return { harness, element, settle };
  };

  const dialog = (element: HTMLElement) => element.querySelector('dialog') as HTMLDialogElement;
  /** Botón de la página; el diálogo de confirmación siempre está en el DOM y no cuenta. */
  const button = (element: HTMLElement, label: string) =>
    Array.from(element.querySelectorAll('button')).find(
      (b) => !b.closest('dialog') && text(b) === label,
    ) as HTMLButtonElement | undefined;
  const dialogButton = (element: HTMLElement, label: string) =>
    Array.from(dialog(element).querySelectorAll('button')).find(
      (b) => text(b) === label,
    ) as HTMLButtonElement;

  describe('contenido', () => {
    it('muestra los metadatos completos y las insignias del envío', async () => {
      const { element } = await open({ current_version: 2, current_round: 1 });

      expect(text(element.querySelector('h1'))).toBe('Efecto del clima en cultivos andinos');
      expect(text(element.querySelector('.detail-code'))).toBe('GPC-2026-000001');
      const badges = text(element.querySelector('.detail-badges'));
      expect(badges).toContain('Enviado');
      expect(badges).toContain('Ronda 1');
      expect(badges).toContain('Versión v2');
      const metadata = text(element.querySelector('[aria-labelledby="metadata-title"]'));
      expect(metadata).toContain('Agronomía');
      expect(metadata).toContain('clima, cultivos');
      expect(metadata).toContain('Resumen del estudio de campo.');
    });

    it('lista a los autores con su correo y filiación', async () => {
      const { element } = await open();

      const rows = Array.from(element.querySelectorAll('[aria-labelledby="authors-title"] tbody tr'))
        .map((row) => Array.from(row.querySelectorAll('td')).map((c) => text(c)));
      expect(rows).toEqual([
        ['Ana López Correspondencia', 'a.lopez@unl.edu.ec', 'Universidad Nacional de Loja'],
        ['Luis Pérez', 'luis@otra.edu', 'Otra Universidad'],
      ]);
    });

    it('muestra cada versión con su sello de integridad y no expone rutas del volumen', async () => {
      const { element } = await open();

      const versions = text(element.querySelector('[aria-labelledby="versions-title"]'));
      expect(versions).toContain('Versión v1');
      expect(versions).toContain('articulo.pdf');
      expect(versions).toContain(`sha256:${'a'.repeat(64)}`);
      expect(versions).toContain('Vigente');
      const html = element.innerHTML;
      expect(html).not.toContain('file_url');
      expect(html).not.toContain('/api/manuscripts/s-1/versions');
      expect(html).not.toContain('/private/');
    });

    it('muestra el historial cronológico', async () => {
      const { element } = await open();

      const entries = Array.from(element.querySelectorAll('.timeline li')).map((li) => text(li));
      expect(entries.length).toBe(2);
      expect(entries[0]).toContain('Borrador creado.');
      expect(entries[1]).toContain('Versión v1 enviada (ronda 0).');
      // 15:30 UTC en la zona institucional (UTC-5) son las 10:30.
      expect(entries[1]).toContain('21/10/2026 10:30');
    });

    it('no muestra datos de auditoría global ni acciones de Administrador', async () => {
      const { element } = await open();

      const content = text(element).toLowerCase();
      expect(content).not.toContain('auditor');
      expect(content).not.toContain('administrador');
      expect(element.querySelector('a[href*="/admin"]')).toBeNull();
    });

    it('un envío dado de baja se muestra en solo lectura', async () => {
      const { element } = await open({ is_active: false, withdrawn_at: '2026-10-22T15:00:00Z' });

      expect(text(element)).toContain('Dado de baja');
      expect(button(element, 'Pasar a revisión')).toBeUndefined();
    });
  });

  describe('estados', () => {
    it('muestra el indicador de carga hasta que llega la respuesta', async () => {
      const harness = await RouterTestingHarness.create();
      await harness.navigateByUrl('/app/editor/submissions/s-1', SubmissionDetailComponent);
      const element = harness.routeNativeElement as HTMLElement;

      expect(element.querySelector('app-loading-spinner')).not.toBeNull();
      http.expectOne(DETAIL_URL).flush(buildSubmissionDetail());
      await harness.fixture.whenStable();
      harness.detectChanges();

      expect(element.querySelector('app-loading-spinner')).toBeNull();
    });

    it('un envío fuera del ámbito (404) se explica y permite reintentar', async () => {
      const harness = await RouterTestingHarness.create();
      await harness.navigateByUrl('/app/editor/submissions/s-1', SubmissionDetailComponent);
      const element = harness.routeNativeElement as HTMLElement;
      http
        .expectOne(DETAIL_URL)
        .flush(errorEnvelope('NOT_FOUND', 'No encontrado.'), {
          status: 404,
          statusText: 'Not Found',
        });
      await harness.fixture.whenStable();
      harness.detectChanges();

      expect(element.querySelector('app-error-state')).not.toBeNull();
      expect(element.querySelector('h1')).toBeNull();

      (element.querySelector('app-error-state button') as HTMLButtonElement).click();
      http.expectOne(DETAIL_URL).flush(buildSubmissionDetail());
      await harness.fixture.whenStable();
      harness.detectChanges();

      expect(element.querySelector('app-error-state')).toBeNull();
      expect(text(element.querySelector('h1'))).toContain('Efecto del clima');
    });
  });

  describe('paso a revisión', () => {
    const START_URL = '/api/editor/submissions/s-1/start-review/';

    it('solo se ofrece a un envío enviado y activo', async () => {
      const { element } = await open();

      expect(button(element, 'Pasar a revisión')).toBeDefined();
    });

    it.each(['UNDER_REVIEW', 'REQUIRES_CORRECTIONS', 'ACCEPTED', 'REJECTED'] as const)(
      'no se ofrece en estado %s',
      async (status) => {
        const { element } = await open({ status });

        expect(button(element, 'Pasar a revisión')).toBeUndefined();
      },
    );

    it('pide confirmación y explica la consecuencia antes de actuar', async () => {
      const { element, settle } = await open();
      expect(dialog(element).open).toBe(false);

      button(element, 'Pasar a revisión')!.click();
      await settle();

      expect(dialog(element).open).toBe(true);
      expect(text(dialog(element))).toContain('pasará a «En revisión»');
      http.expectNone(START_URL);
    });

    it('cancelar no cambia nada ni llama a la API', async () => {
      const { element, settle } = await open();
      button(element, 'Pasar a revisión')!.click();
      await settle();

      dialogButton(element, 'Cancelar').click();
      await settle();

      expect(dialog(element).open).toBe(false);
      http.expectNone(START_URL);
      expect(text(element.querySelector('.detail-badges'))).toContain('Enviado');
    });

    it('al confirmar llama a la API y refleja el estado actualizado', async () => {
      const { element, settle } = await open();
      button(element, 'Pasar a revisión')!.click();
      await settle();

      dialogButton(element, 'Pasar a revisión').click();
      await settle();
      const request = http.expectOne(START_URL);
      expect(request.request.method).toBe('POST');
      request.flush({ id: 's-1', code: 'GPC-2026-000001', status: 'UNDER_REVIEW', assignment: null });
      await settle();

      // Vuelve a leer el detalle: el estado mostrado es el del servidor.
      http.expectOne(DETAIL_URL).flush(buildSubmissionDetail({ status: 'UNDER_REVIEW' }), {
        headers: { ETag: '"1"' },
      });
      await settle();

      expect(text(element.querySelector('.detail-badges'))).toContain('En revisión');
      expect(text(element)).toContain('El envío pasó a revisión.');
      expect(text(element)).toContain('a la espera de asignar un Revisor');
      expect(button(element, 'Pasar a revisión')).toBeUndefined();
      expect(dialog(element).open).toBe(false);
    });

    it('mientras actúa bloquea el botón y no permite repetir la acción', async () => {
      const { element, settle } = await open();
      button(element, 'Pasar a revisión')!.click();
      await settle();
      dialogButton(element, 'Pasar a revisión').click();
      await settle();

      const busy = button(element, 'Pasando a revisión…');
      expect(busy?.disabled).toBe(true);
      http
        .expectOne(START_URL)
        .flush({ id: 's-1', code: 'GPC-2026-000001', status: 'UNDER_REVIEW', assignment: null });
      http.expectOne(DETAIL_URL).flush(buildSubmissionDetail({ status: 'UNDER_REVIEW' }));
    });

    it('si otro Editor se adelantó (409) lo explica y muestra el estado real', async () => {
      const { element, settle } = await open();
      button(element, 'Pasar a revisión')!.click();
      await settle();
      dialogButton(element, 'Pasar a revisión').click();
      await settle();

      http
        .expectOne(START_URL)
        .flush(errorEnvelope('STATE_CONFLICT', 'Solo un manuscrito enviado puede pasar a revisión.'), {
          status: 409,
          statusText: 'Conflict',
        });
      await settle();
      http.expectOne(DETAIL_URL).flush(buildSubmissionDetail({ status: 'UNDER_REVIEW' }));
      await settle();

      expect(element.querySelector('[role="alert"]')).not.toBeNull();
      expect(text(element.querySelector('.detail-badges'))).toContain('En revisión');
      expect(button(element, 'Pasar a revisión')).toBeUndefined();
    });

    it('un envío en revisión muestra al Revisor asignado y su plazo', async () => {
      const { element } = await open({
        status: 'UNDER_REVIEW',
        open_assignment: {
          id: 'a-1',
          status: 'ACTIVE',
          assigned_at: '2026-10-22T15:00:00Z',
          due_at: '2026-11-11T15:00:00Z',
          is_overdue: false,
          reviewer: { id: 'r-1', full_name: 'Marta Ruiz', email: 'marta@unl.edu.ec' },
        },
      });

      const info = text(element.querySelector('.callout--info'));
      expect(info).toContain('Marta Ruiz');
      expect(info).toContain('marta@unl.edu.ec');
      expect(info).toContain('11/11/2026 10:00');
    });
  });

  describe('descarga del PDF', () => {
    let clicked: HTMLAnchorElement[];
    let click: ReturnType<typeof vi.spyOn>;

    beforeEach(() => {
      clicked = [];
      Object.assign(URL, { createObjectURL: vi.fn(() => 'blob:gpc-test'), revokeObjectURL: vi.fn() });
      click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (
        this: HTMLAnchorElement,
      ) {
        clicked.push(this);
      });
    });

    afterEach(() => click.mockRestore());

    it('pide el archivo como Blob al endpoint autorizado y lo entrega con el nombre del servidor', async () => {
      const { element, settle } = await open();

      button(element, 'Descargar PDF')!.click();
      await settle();
      const request = http.expectOne('/api/manuscripts/s-1/versions/v-1/file/');
      expect(request.request.responseType).toBe('blob');
      request.flush(new Blob(['%PDF-1.7'], { type: 'application/pdf' }), {
        headers: { 'Content-Disposition': 'attachment; filename="GPC-2026-000001-v1.pdf"' },
      });
      await settle();

      expect(clicked[0].download).toBe('GPC-2026-000001-v1.pdf');
    });

    it('si falla lo explica y deja volver a intentar', async () => {
      const { element, settle } = await open();

      button(element, 'Descargar PDF')!.click();
      await settle();
      http
        .expectOne('/api/manuscripts/s-1/versions/v-1/file/')
        .flush(new Blob([JSON.stringify(errorEnvelope('AUDIT_UNAVAILABLE', 'Auditoría no disponible.'))]), {
          status: 503,
          statusText: 'Service Unavailable',
        });
      await new Promise((resolve) => setTimeout(resolve));
      await settle();

      expect(element.querySelector('[role="alert"]')).not.toBeNull();
      expect(clicked.length).toBe(0);
      expect(button(element, 'Descargar PDF')!.disabled).toBe(false);
    });
  });
});
