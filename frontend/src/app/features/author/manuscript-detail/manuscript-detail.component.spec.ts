import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { beforeAll } from 'vitest';
import { provideRouter } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';

import { API_BASE_URL } from '../../../core/http/api-base-url.token';
import { MANUSCRIPT_STATUSES, Manuscript, nextAction } from '../../../core/models/manuscript.model';
import {
  AUTHOR_ANA,
  AUTHOR_LUIS,
  buildManuscript,
  errorEnvelope,
} from '../testing/manuscript.fixtures';
import { ManuscriptDetailComponent } from './manuscript-detail.component';

describe('ManuscriptDetailComponent', () => {
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
          { path: 'app/author/manuscripts/:id', component: ManuscriptDetailComponent },
        ]),
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: API_BASE_URL, useValue: '/api/' },
      ],
    });
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  /** Abre el detalle de `m-1` y responde con el manuscrito indicado. */
  const open = async (overrides: Partial<Manuscript> | Record<string, unknown> = {}) => {
    const harness = await RouterTestingHarness.create();
    await harness.navigateByUrl('/app/author/manuscripts/m-1', ManuscriptDetailComponent);
    const element = harness.routeNativeElement as HTMLElement;
    const settle = async () => {
      await harness.fixture.whenStable();
      harness.detectChanges();
    };
    http
      .expectOne('/api/manuscripts/m-1/')
      .flush(buildManuscript(overrides as Partial<Manuscript>), { headers: { ETag: '"2"' } });
    await settle();
    return { element, settle };
  };

  const hasEditLink = (element: HTMLElement) =>
    Array.from(element.querySelectorAll<HTMLAnchorElement>('a')).some(
      (a) => a.textContent?.trim() === 'Editar manuscrito',
    );

  const text = (element: HTMLElement) => (element.textContent ?? '').replace(/\s+/g, ' ');
  const links = (element: HTMLElement) =>
    Array.from(element.querySelectorAll<HTMLAnchorElement>('a')).map((a) => [
      (a.textContent ?? '').trim(),
      a.getAttribute('href'),
    ]);

  describe('contenido', () => {
    it('muestra código, título, estado, versión, ronda y datos generales', async () => {
      const { element } = await open({
        code: 'GPC-2026-000042',
        title: 'Suelos del páramo',
        status: 'UNDER_REVIEW',
        current_version: 2,
        current_round: 1,
        area: 'Agronomía',
        language: 'es',
        keywords: ['suelo', 'páramo'],
        abstract: 'Estudio de campo en tres sitios.',
      });

      const content = text(element);
      expect(content).toContain('GPC-2026-000042');
      expect(element.querySelector('h1')?.textContent).toBe('Suelos del páramo');
      expect(content).toContain('En revisión');
      expect(content).toContain('Versión v2');
      expect(content).toContain('Ronda 1');
      expect(content).toContain('Agronomía');
      expect(content).toContain('suelo, páramo');
      expect(content).toContain('Estudio de campo en tres sitios.');
    });

    it('un borrador aún sin versión formal lo indica', async () => {
      const { element } = await open({ current_version: 0 });

      expect(text(element)).toContain('Sin versión formal');
      expect(text(element)).toContain('Ronda 0');
    });

    it('lista los autores con contacto, filiación y el responsable', async () => {
      const { element } = await open({ authors: [{ ...AUTHOR_ANA }, { ...AUTHOR_LUIS }] });

      const rows = Array.from(element.querySelectorAll('table.authors tbody tr'));
      expect(rows.length).toBe(2);
      expect(text(rows[0] as HTMLElement)).toContain('Ana López');
      expect(text(rows[0] as HTMLElement)).toContain('Responsable');
      expect(text(rows[0] as HTMLElement)).toContain('Universidad Nacional de Loja');
      expect(text(rows[1] as HTMLElement)).toContain('luis@otra.edu');
      expect(text(rows[1] as HTMLElement)).not.toContain('Responsable');
    });

    it('muestra las fechas en la zona institucional (UTC-5)', async () => {
      const { element } = await open({
        created_at: '2026-10-20T15:30:00Z',
        updated_at: '2026-10-21T01:45:00Z',
      });

      expect(text(element)).toContain('20/10/2026 10:30');
      expect(text(element)).toContain('20/10/2026 20:45');
    });

    const DRAFT_FILE = {
      filename: 'articulo.pdf',
      size_bytes: 2_621_440,
      uploaded_at: '2026-10-20T15:30:00Z',
    };

    it('un borrador muestra el cargador con el PDF actual, su nombre y tamaño legible', async () => {
      const { element } = await open({ status: 'DRAFT', draft_file: DRAFT_FILE });

      const uploader = element.querySelector('app-pdf-uploader') as HTMLElement;
      expect(text(uploader)).toContain('articulo.pdf');
      expect(text(uploader)).toContain('2,5 MB');
      expect(text(uploader)).toContain('Reemplazar el PDF');
    });

    it('un borrador sin PDF invita a adjuntarlo', async () => {
      const { element } = await open({ status: 'DRAFT', draft_file: null });

      const uploader = element.querySelector('app-pdf-uploader') as HTMLElement;
      expect(text(uploader)).toContain('Aún no hay un PDF adjunto.');
      expect(text(uploader)).toContain('Adjuntar el PDF');
    });

    it.each(MANUSCRIPT_STATUSES.filter((status) => status !== 'DRAFT'))(
      'en %s no se ofrece el cargador del borrador',
      async (status) => {
        const { element } = await open({ status });

        expect(element.querySelector('app-pdf-uploader')).toBeNull();
      },
    );

    it('un borrador dado de baja muestra el PDF en solo lectura, sin cargador', async () => {
      const { element } = await open({
        status: 'DRAFT',
        is_active: false,
        withdrawn_at: '2026-10-22T17:00:00Z',
        draft_file: DRAFT_FILE,
      });

      expect(element.querySelector('app-pdf-uploader')).toBeNull();
      const section = text(element.querySelector('[aria-labelledby="draft-title"]') as HTMLElement);
      expect(section).toContain('articulo.pdf');
      expect(section).toContain('2,5 MB');
    });

    it('al subir el PDF el detalle refleja el nuevo borrador sin recargar', async () => {
      const { element, settle } = await open({ status: 'DRAFT', draft_file: null });
      const input = element.querySelector('#pdf-file') as HTMLInputElement;
      const file = new File(['%PDF-1.7'], 'nuevo.pdf', { type: 'application/pdf' });
      Object.defineProperty(input, 'files', { value: [file], configurable: true });
      input.dispatchEvent(new Event('change'));
      await settle();

      (element.querySelector('.uploader__actions .btn--success') as HTMLButtonElement).click();
      http
        .expectOne('/api/manuscripts/m-1/draft-file/')
        .flush(
          { filename: 'nuevo.pdf', size_bytes: 8, uploaded_at: '2026-10-25T12:00:00Z' },
          { status: 201, statusText: 'Created' },
        );
      await settle();

      expect(text(element.querySelector('app-pdf-uploader') as HTMLElement)).toContain(
        'Borrador actual: nuevo.pdf',
      );
      expect(element.querySelector('app-pdf-uploader .uploader__success')?.textContent).toContain(
        'PDF adjuntado: nuevo.pdf.',
      );
    });

    it('enlaza siempre con el historial de versiones y el listado', async () => {
      const { element } = await open({ id: 'm-1' });

      expect(links(element)).toContainEqual([
        'Historial de versiones',
        '/app/author/manuscripts/m-1/history',
      ]);
      expect(links(element)).toContainEqual([
        '← Volver a mis manuscritos',
        '/app/author/manuscripts',
      ]);
    });
  });

  describe('acciones permitidas', () => {
    const hasEdit = (element: HTMLElement) =>
      links(element).some(([label]) => label === 'Editar manuscrito');

    it.each(MANUSCRIPT_STATUSES)(
      'Editar aparece solo si el estado %s lo permite',
      async (status) => {
        const { element } = await open({ status });

        expect(hasEdit(element)).toBe(status === 'DRAFT' || status === 'REQUIRES_CORRECTIONS');
      },
    );

    it.each(MANUSCRIPT_STATUSES)(
      'un manuscrito dado de baja (%s) nunca ofrece Editar',
      async (status) => {
        const { element } = await open({
          status,
          is_active: false,
          withdrawn_at: '2026-10-22T12:00:00Z',
        });

        expect(hasEdit(element)).toBe(false);
      },
    );

    it('el enlace de edición apunta al formulario del manuscrito', async () => {
      const { element } = await open({ id: 'm-1', status: 'REQUIRES_CORRECTIONS' });

      expect(links(element)).toContainEqual([
        'Editar manuscrito',
        '/app/author/manuscripts/m-1/edit',
      ]);
    });
  });

  describe('siguiente acción', () => {
    it.each(MANUSCRIPT_STATUSES)('explica qué hacer en %s', async (status) => {
      const { element } = await open({ status });

      const callout = text(
        element.querySelector('[aria-labelledby="next-action-title"]') as HTMLElement,
      );
      expect(callout).toContain('Siguiente acción');
      expect(callout).toContain(nextAction({ status, is_active: true }).detail);
    });

    it('un manuscrito dado de baja se explica como archivado', async () => {
      const { element } = await open({
        status: 'ACCEPTED',
        is_active: false,
        withdrawn_at: '2026-10-22T17:00:00Z',
        withdrawal_reason: 'Retiro por decisión del equipo.',
      });

      expect(
        text(element.querySelector('[aria-labelledby="next-action-title"]') as HTMLElement),
      ).toContain('solo lectura');
      expect(text(element)).toContain('Dado de baja');
      expect(text(element)).toContain('22/10/2026 12:00');
      expect(text(element)).toContain('Motivo: Retiro por decisión del equipo.');
    });

    it('un manuscrito activo no se presenta como dado de baja', async () => {
      const { element } = await open({ is_active: true });

      expect(text(element)).not.toContain('Dado de baja');
    });
  });

  describe('observaciones y veredicto', () => {
    it('muestra el veredicto, las observaciones y los comentarios para el autor', async () => {
      const { element } = await open({
        status: 'REQUIRES_CORRECTIONS',
        feedback: {
          decision: 'REQUIRES_CORRECTIONS',
          observations: 'Ampliar la muestra y revisar la metodología.',
          comments_for_author: 'El análisis estadístico es claro, pero faltan controles.',
        },
      });

      const section = element.querySelector('[aria-labelledby="feedback-title"]') as HTMLElement;
      expect(text(section)).toContain('Veredicto: Requiere correcciones');
      expect(text(section)).toContain('Ampliar la muestra y revisar la metodología.');
      expect(text(section)).toContain('El análisis estadístico es claro, pero faltan controles.');
    });

    it('un rechazo sin observaciones muestra solo el veredicto y los comentarios', async () => {
      const { element } = await open({
        status: 'REJECTED',
        feedback: {
          decision: 'REJECTED',
          observations: null,
          comments_for_author: 'No cumple el alcance.',
        },
      });

      const section = element.querySelector('[aria-labelledby="feedback-title"]') as HTMLElement;
      expect(text(section)).toContain('Veredicto: Rechazado');
      expect(text(section)).not.toContain('Observaciones del Editor');
      expect(text(section)).toContain('No cumple el alcance.');
    });

    it.each([[undefined], [null]])(
      'sin evaluación (%s) no hay sección de resultado',
      async (feedback) => {
        const { element } = await open({ feedback });

        expect(element.querySelector('[aria-labelledby="feedback-title"]')).toBeNull();
      },
    );

    it('nunca muestra la identidad del Revisor, comentarios confidenciales ni puntuaciones', async () => {
      // Aunque la respuesta los trajera por error, la vista solo lee los tres campos permitidos.
      const { element } = await open({
        feedback: {
          decision: 'REQUIRES_CORRECTIONS',
          observations: 'Ampliar la muestra.',
          comments_for_author: 'Buen trabajo.',
          reviewer: { full_name: 'Revisor Secreto', email: 'revisor.secreto@unl.edu.ec' },
          confidential_comments: 'Solo para el Editor: sospecho plagio.',
          originality_score: 2,
          methodology_score: 1,
          recommendation: 'REJECT',
        },
        reviewer: { full_name: 'Revisor Secreto' },
        confidential_comments: 'Solo para el Editor: sospecho plagio.',
      });

      const content = text(element);
      for (const leaked of [
        'Revisor Secreto',
        'revisor.secreto',
        'sospecho plagio',
        'Solo para el Editor',
        'originality',
        'methodology',
        'REJECT',
      ]) {
        expect(content).not.toContain(leaked);
      }
      expect(content).toContain('Ampliar la muestra.');
    });
  });

  describe('estados de carga y error', () => {
    it('muestra la carga hasta recibir la respuesta', async () => {
      const harness = await RouterTestingHarness.create();
      await harness.navigateByUrl('/app/author/manuscripts/m-1', ManuscriptDetailComponent);
      const element = harness.routeNativeElement as HTMLElement;

      expect(element.querySelector('app-loading-spinner')).not.toBeNull();

      http.expectOne('/api/manuscripts/m-1/').flush(buildManuscript());
      await harness.fixture.whenStable();
      harness.detectChanges();
      expect(element.querySelector('app-loading-spinner')).toBeNull();
    });

    it('un manuscrito ajeno responde 404 sin revelar nada y permite reintentar', async () => {
      const harness = await RouterTestingHarness.create();
      await harness.navigateByUrl('/app/author/manuscripts/m-1', ManuscriptDetailComponent);
      const element = harness.routeNativeElement as HTMLElement;
      const settle = async () => {
        await harness.fixture.whenStable();
        harness.detectChanges();
      };

      http.expectOne('/api/manuscripts/m-1/').flush(errorEnvelope('NOT_FOUND', 'No encontrado.'), {
        status: 404,
        statusText: 'Not Found',
      });
      await settle();

      expect(element.querySelector('app-error-state')?.textContent).toContain(
        'no existe o no está disponible',
      );
      expect(element.querySelector('h1')).toBeNull();

      (element.querySelector('app-error-state button') as HTMLButtonElement).click();
      await settle();
      http.expectOne('/api/manuscripts/m-1/').flush(buildManuscript({ title: 'Recuperado' }));
      await settle();

      expect(element.querySelector('h1')?.textContent).toBe('Recuperado');
      expect(element.querySelector('app-error-state')).toBeNull();
    });
  });

  describe('baja lógica', () => {
    const REASON_REQUIRED = ['UNDER_REVIEW', 'ACCEPTED'] as const;
    const REASON_OPTIONAL = MANUSCRIPT_STATUSES.filter(
      (status) => !(REASON_REQUIRED as readonly string[]).includes(status),
    );
    const WITHDRAW_URL = '/api/manuscripts/m-1/withdraw/';

    const withdrawButton = (element: HTMLElement) =>
      Array.from(element.querySelectorAll('.actions button')).find(
        (b) => b.textContent?.trim() === 'Dar de baja',
      ) as HTMLButtonElement | undefined;
    const dialog = (element: HTMLElement) => element.querySelector('dialog') as HTMLDialogElement;
    const dialogButton = (element: HTMLElement, label: string) =>
      Array.from(dialog(element).querySelectorAll('button')).find(
        (b) => b.textContent?.trim() === label,
      ) as HTMLButtonElement;
    const writeReason = async (
      element: HTMLElement,
      settle: () => Promise<void>,
      value: string,
    ) => {
      const textarea = dialog(element).querySelector('textarea') as HTMLTextAreaElement;
      textarea.value = value;
      textarea.dispatchEvent(new Event('input'));
      await settle();
    };

    it.each(MANUSCRIPT_STATUSES)(
      'un manuscrito activo en %s ofrece «Dar de baja»',
      async (status) => {
        const { element } = await open({ status });

        expect(withdrawButton(element)).toBeDefined();
        expect(withdrawButton(element)?.classList.contains('btn--danger')).toBe(true);
      },
    );

    it('un manuscrito ya dado de baja no la ofrece', async () => {
      const { element } = await open({ is_active: false, withdrawn_at: '2026-10-22T17:00:00Z' });

      expect(withdrawButton(element)).toBeUndefined();
    });

    it('el diálogo permanece cerrado hasta pulsar el botón', async () => {
      const { element, settle } = await open({ status: 'SUBMITTED' });
      expect(dialog(element).open).toBe(false);

      withdrawButton(element)?.click();
      await settle();

      expect(dialog(element).open).toBe(true);
      expect(text(dialog(element))).toContain('No se borra nada');
    });

    it('cancelar cierra el diálogo sin llamar al servidor', async () => {
      const { element, settle } = await open({ status: 'SUBMITTED' });
      withdrawButton(element)?.click();
      await settle();

      dialogButton(element, 'Cancelar').click();
      await settle();

      expect(dialog(element).open).toBe(false);
      http.expectNone(WITHDRAW_URL);
    });

    it.each(REASON_REQUIRED)('en %s exige el motivo antes de enviar la baja', async (status) => {
      const { element, settle } = await open({ status });
      withdrawButton(element)?.click();
      await settle();

      dialogButton(element, 'Confirmar baja').click();
      await settle();

      http.expectNone(WITHDRAW_URL);
      expect(text(dialog(element))).toContain('Indique el motivo de la baja');
      expect(dialog(element).open).toBe(true);
    });

    it.each(REASON_REQUIRED)(
      'en %s la baja con motivo envía el motivo recortado',
      async (status) => {
        const { element, settle } = await open({ status });
        withdrawButton(element)?.click();
        await settle();
        await writeReason(element, settle, '  Retiro por decisión del equipo.  ');

        dialogButton(element, 'Confirmar baja').click();
        await settle();

        const request = http.expectOne(WITHDRAW_URL);
        expect(request.request.method).toBe('POST');
        expect(request.request.body).toEqual({ reason: 'Retiro por decisión del equipo.' });
        request.flush(
          buildManuscript({ status, is_active: false, withdrawn_at: '2026-10-22T17:00:00Z' }),
        );
        await settle();
      },
    );

    it.each(REASON_OPTIONAL)('en %s la baja puede hacerse sin motivo', async (status) => {
      const { element, settle } = await open({ status });
      withdrawButton(element)?.click();
      await settle();

      dialogButton(element, 'Confirmar baja').click();
      await settle();

      const request = http.expectOne(WITHDRAW_URL);
      expect(request.request.body).toEqual({});
      request.flush(
        buildManuscript({ status, is_active: false, withdrawn_at: '2026-10-22T17:00:00Z' }),
      );
      await settle();
    });

    it('tras la baja el detalle pasa a archivado, de solo lectura, y lo explica', async () => {
      const { element, settle } = await open({ status: 'REQUIRES_CORRECTIONS' });
      expect(hasEditLink(element)).toBe(true);
      withdrawButton(element)?.click();
      await settle();
      await writeReason(element, settle, 'Cierro el proceso.');
      dialogButton(element, 'Confirmar baja').click();
      await settle();

      http.expectOne(WITHDRAW_URL).flush(
        buildManuscript({
          status: 'REQUIRES_CORRECTIONS',
          is_active: false,
          withdrawn_at: '2026-10-22T17:00:00Z',
          withdrawal_reason: 'Cierro el proceso.',
        }),
      );
      await settle();

      expect(dialog(element).open).toBe(false);
      expect(element.querySelector('.callout--success')?.textContent).toContain(
        'Su historial, sus versiones y su auditoría se conservan',
      );
      expect(text(element)).toContain('Dado de baja');
      expect(text(element)).toContain('Motivo: Cierro el proceso.');
      expect(withdrawButton(element)).toBeUndefined();
      expect(hasEditLink(element)).toBe(false);
      expect(element.querySelector('app-pdf-uploader')).toBeNull();
      // El historial sigue accesible.
      expect(links(element)).toContainEqual([
        'Historial de versiones',
        '/app/author/manuscripts/m-1/history',
      ]);
    });

    it('un error del servidor se muestra dentro del diálogo y permite reintentar', async () => {
      const { element, settle } = await open({ status: 'SUBMITTED' });
      withdrawButton(element)?.click();
      await settle();
      dialogButton(element, 'Confirmar baja').click();
      await settle();

      http.expectOne(WITHDRAW_URL).flush(errorEnvelope('AUDIT_UNAVAILABLE', 'Sin auditoría.'), {
        status: 503,
        statusText: 'Service Unavailable',
      });
      await settle();

      expect(dialog(element).open).toBe(true);
      expect(text(dialog(element))).toContain('Servicio no disponible');
      expect(dialogButton(element, 'Confirmar baja').disabled).toBe(false);

      dialogButton(element, 'Confirmar baja').click();
      await settle();
      http
        .expectOne(WITHDRAW_URL)
        .flush(buildManuscript({ is_active: false, withdrawn_at: '2026-10-22T17:00:00Z' }));
      await settle();
      expect(dialog(element).open).toBe(false);
    });

    it('si el servidor pide el motivo, lo muestra en el diálogo', async () => {
      const { element, settle } = await open({ status: 'SUBMITTED' });
      withdrawButton(element)?.click();
      await settle();
      dialogButton(element, 'Confirmar baja').click();
      await settle();

      http.expectOne(WITHDRAW_URL).flush(
        errorEnvelope('VALIDATION_ERROR', 'Indique el motivo.', {
          reason: ['Indique el motivo de la baja: el manuscrito está en revisión o aceptado.'],
        }),
        { status: 400, statusText: 'Bad Request' },
      );
      await settle();

      expect(text(dialog(element))).toContain(
        'Indique el motivo de la baja: el manuscrito está en revisión',
      );
    });

    it('si ya estaba dado de baja (409) cierra el diálogo y muestra el estado real', async () => {
      const { element, settle } = await open({ status: 'SUBMITTED' });
      withdrawButton(element)?.click();
      await settle();
      dialogButton(element, 'Confirmar baja').click();
      await settle();

      http.expectOne(WITHDRAW_URL).flush(errorEnvelope('STATE_CONFLICT', 'Ya dado de baja.'), {
        status: 409,
        statusText: 'Conflict',
      });
      await settle();
      http
        .expectOne('/api/manuscripts/m-1/')
        .flush(buildManuscript({ is_active: false, withdrawn_at: '2026-10-22T17:00:00Z' }));
      await settle();

      expect(dialog(element).open).toBe(false);
      expect(text(element)).toContain('Dado de baja');
      expect(withdrawButton(element)).toBeUndefined();
    });

    it('no envía dos bajas a la vez', async () => {
      const { element, settle } = await open({ status: 'SUBMITTED' });
      withdrawButton(element)?.click();
      await settle();

      dialogButton(element, 'Confirmar baja').click();
      await settle();
      expect(dialogButton(element, 'Dando de baja…').disabled).toBe(true);
      dialogButton(element, 'Dando de baja…').click();
      await settle();

      http
        .expectOne(WITHDRAW_URL)
        .flush(buildManuscript({ is_active: false, withdrawn_at: '2026-10-22T17:00:00Z' }));
    });
  });
});
