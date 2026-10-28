import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';
import { vi } from 'vitest';

import { routes } from '../../app.routes';
import { AuthStore } from '../../core/auth/auth.store';
import { API_BASE_URL } from '../../core/http/api-base-url.token';
import { Role } from '../../core/models/role.model';
import { SessionUser } from '../../core/models/session-user.model';
import { errorEnvelope } from '../author/testing/manuscript.fixtures';
import {
  buildAssignmentDetail,
  buildAssignmentPage,
  buildAssignmentRow,
  buildCompleteEvaluation,
  buildHistoryPage,
  buildHistoryRow,
  buildReviewerEvaluation,
} from './testing/reviewer.fixtures';

/**
 * Integración del módulo Revisor con las rutas REALES de la aplicación
 * (TSK-69): carga diferida, guards de rol, títulos, navegación por enlaces,
 * acceso por URL a una asignación ajena, bloqueo por vencimiento, manejo de
 * `409`/`410` y aviso de cambios sin guardar. Solo se simula la API.
 */
const USER: SessionUser = {
  id: 'u-5',
  institutional_id: 'INST-0005',
  username: 'r.vega',
  email: 'r.vega@unl.edu.ec',
  first_name: 'Rosa',
  last_name: 'Vega',
  full_name: 'Rosa Vega',
};

const REVIEWER_ROUTES = [
  ['bandeja', '/app/reviewer/assignments', 'app-assignment-list', 'Mis asignaciones'],
  ['detalle', '/app/reviewer/assignments/a-1', 'app-assignment-detail', 'Detalle de la asignación'],
  ['evaluación', '/app/reviewer/assignments/a-1/evaluate', 'app-evaluation-form', 'Evaluación'],
  ['historial', '/app/reviewer/history', 'app-evaluation-history', 'Historial de evaluaciones'],
] as const;

const REVIEWER_SCREENS =
  'app-assignment-list, app-assignment-detail, app-evaluation-form, app-evaluation-history';

const emptyPage = { count: 0, next: null, previous: null, results: [] };

const NOT_FOUND = [
  errorEnvelope('NOT_FOUND', 'No encontrado.'),
  { status: 404, statusText: 'Not Found' },
] as const;

describe('Módulo Revisor: integración con las rutas reales', () => {
  let http: HttpTestingController;
  let router: Router;
  let store: AuthStore;

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
        provideRouter(routes),
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: API_BASE_URL, useValue: '/api/' },
      ],
    });
    http = TestBed.inject(HttpTestingController);
    router = TestBed.inject(Router);
    store = TestBed.inject(AuthStore);
  });

  afterEach(() => {
    http.verify();
    vi.restoreAllMocks();
  });

  const signIn = (...roles: Role[]) => store.setSession({ user: USER, roles, access: 'token' });

  const inbox = () => http.expectOne((r) => r.url === '/api/reviewer/assignments/');
  const detail = () => http.expectOne('/api/reviewer/assignments/a-1/');
  const evaluation = () => http.expectOne('/api/reviewer/assignments/a-1/evaluation/');
  const history = () => http.expectOne((r) => r.url === '/api/reviewer/evaluations/');

  const open = async (url: string) => {
    const harness = await RouterTestingHarness.create();
    await harness.navigateByUrl(url);
    const element = harness.routeNativeElement as HTMLElement;
    const settle = async () => {
      await harness.fixture.whenStable();
      harness.detectChanges();
    };
    return { harness, element, settle };
  };

  const click = async (element: HTMLElement, label: string, settle: () => Promise<void>) => {
    const link = Array.from(element.querySelectorAll<HTMLElement>('a, button')).find(
      (e) => e.textContent?.trim() === label,
    );
    expect(link, `enlace «${label}»`).toBeDefined();
    link?.click();
    await settle();
  };

  /** Responde lo que cada pantalla pide al cargar. */
  const answer = (selector: string, overdue = false) => {
    if (selector === 'app-assignment-list') inbox().flush(emptyPage);
    else if (selector === 'app-assignment-detail')
      detail().flush(buildAssignmentDetail({ is_overdue: overdue }));
    else if (selector === 'app-evaluation-form') {
      detail().flush(buildAssignmentDetail({ is_overdue: overdue }));
      evaluation().flush(buildReviewerEvaluation(), { headers: { ETag: '"0"' } });
    } else history().flush(emptyPage);
  };

  describe('rutas y roles', () => {
    it.each(REVIEWER_ROUTES)(
      '%s: el Revisor llega a su pantalla, con el título correcto',
      async (_name, url, selector, title) => {
        signIn('REVIEWER');
        const { element, settle } = await open(url);
        answer(selector);
        await settle();

        expect(element.querySelector(selector)).not.toBeNull();
        expect(document.title).toBe(title);
        expect(router.url).toBe(url);
      },
    );

    const OTHER_ROLES = ['EDITOR', 'AUTHOR', 'ADMIN'] as const;
    it.each(
      OTHER_ROLES.flatMap((role) =>
        REVIEWER_ROUTES.map(([name, url]) => [role, name, url] as const),
      ),
    )('el rol %s no entra a «%s» ni se pide nada', async (role, _name, url) => {
      signIn(role);
      await open(url);

      expect(router.url).toBe('/forbidden');
      expect(document.querySelector(REVIEWER_SCREENS)).toBeNull();
      http.expectNone(() => true);
    });

    it('una persona con Autor y Revisor entra sin conmutar de rol', async () => {
      signIn('AUTHOR', 'REVIEWER');
      const { element, settle } = await open('/app/reviewer/assignments');
      inbox().flush(buildAssignmentPage([buildAssignmentRow()]));
      await settle();

      expect(element.querySelector('app-assignment-list')).not.toBeNull();
      expect(element.querySelector('[role="tablist"], select[name="role"]')).toBeNull();
    });
  });

  describe('acceso por URL a una asignación ajena', () => {
    it('el detalle ajeno (404) no muestra ningún dato y no pide el documento', async () => {
      signIn('REVIEWER');
      const { element, settle } = await open('/app/reviewer/assignments/a-1');
      detail().flush(...NOT_FOUND);
      await settle();

      expect(element.querySelector('app-error-state')).not.toBeNull();
      expect(element.querySelector('h1')).toBeNull();
      expect(element.querySelector('table, dl, app-pdf-viewer')).toBeNull();
      http.expectNone((r) => r.url.includes('/document/'));
    });

    it('el formulario de una asignación ajena (404) no se muestra', async () => {
      signIn('REVIEWER');
      const { element, settle } = await open('/app/reviewer/assignments/a-1/evaluate');
      const pending = evaluation();
      detail().flush(...NOT_FOUND);
      await settle();

      // El primer 404 basta: la lectura de la evaluación se cancela.
      expect(pending.cancelled).toBe(true);
      expect(element.querySelector('app-error-state')).not.toBeNull();
      expect(element.querySelector('form')).toBeNull();
    });

    it('un Revisor con conflicto de interés (autor o coautor) tampoco ve la asignación por URL', async () => {
      signIn('AUTHOR', 'REVIEWER');
      const { element, settle } = await open('/app/reviewer/assignments/a-1');
      detail().flush(...NOT_FOUND);
      await settle();

      expect(element.querySelector('app-assignment-detail h1')).toBeNull();
      expect(element.querySelector('app-error-state')).not.toBeNull();
    });
  });

  describe('navegación por enlaces', () => {
    it('bandeja → detalle, con el enlace del código', async () => {
      signIn('REVIEWER');
      const { element, settle } = await open('/app/reviewer/assignments');
      inbox().flush(
        buildAssignmentPage([
          buildAssignmentRow({ id: 'a-1', manuscript_code: 'GPC-2026-000001' }),
        ]),
      );
      await settle();

      await click(element, 'GPC-2026-000001', settle);

      expect(router.url).toBe('/app/reviewer/assignments/a-1');
      detail().flush(buildAssignmentDetail());
      await settle();
      expect(element.querySelector('app-assignment-detail')).not.toBeNull();
      expect(element.querySelector('h1')?.textContent).toContain('Efecto del clima');
    });

    it('detalle → formulario con «Evaluar manuscrito» y vuelta con el enlace de regreso', async () => {
      signIn('REVIEWER');
      const { element, settle } = await open('/app/reviewer/assignments/a-1');
      detail().flush(buildAssignmentDetail());
      await settle();

      await click(element, 'Evaluar manuscrito', settle);

      expect(router.url).toBe('/app/reviewer/assignments/a-1/evaluate');
      detail().flush(buildAssignmentDetail());
      evaluation().flush(buildReviewerEvaluation(), { headers: { ETag: '"0"' } });
      await settle();
      expect(element.querySelector('app-evaluation-form')).not.toBeNull();

      await click(element, '← Volver al detalle de la asignación', settle);
      expect(router.url).toBe('/app/reviewer/assignments/a-1');
      detail().flush(buildAssignmentDetail());
      await settle();
      expect(element.querySelector('app-assignment-detail')).not.toBeNull();
    });

    it('una asignación completada lleva al historial y el historial vuelve a la bandeja', async () => {
      signIn('REVIEWER');
      const { element, settle } = await open('/app/reviewer/assignments/a-1');
      detail().flush(
        buildAssignmentDetail({
          status: 'COMPLETED',
          state: 'EVALUATED',
          completed_at: '2026-10-25T20:00:00Z',
          document_url: null,
        }),
      );
      await settle();

      await click(element, 'Ver mi historial', settle);
      expect(router.url).toBe('/app/reviewer/history');
      history().flush(buildHistoryPage([buildHistoryRow()]));
      await settle();
      expect(element.querySelector('app-evaluation-history')).not.toBeNull();

      await click(element, '← Volver a mis asignaciones', settle);
      expect(router.url).toBe('/app/reviewer/assignments');
      inbox().flush(emptyPage);
      await settle();
      expect(element.querySelector('app-assignment-list')).not.toBeNull();
    });
  });

  describe('estado en la URL', () => {
    it('la página de la bandeja vive en la URL y recargarla reproduce la misma vista', async () => {
      signIn('REVIEWER');
      const view = await open('/app/reviewer/assignments?page=2');

      const request = inbox();
      expect(request.request.params.get('page')).toBe('2');
      request.flush(buildAssignmentPage([buildAssignmentRow()], 25));
      await view.settle();

      expect(router.url).toBe('/app/reviewer/assignments?page=2');
    });
  });

  describe('bloqueo por vencimiento', () => {
    it('con el plazo vencido el detalle no deja entrar a evaluar', async () => {
      signIn('REVIEWER');
      const { element, settle } = await open('/app/reviewer/assignments/a-1');
      detail().flush(buildAssignmentDetail({ is_overdue: true, state: 'OVERDUE' }));
      await settle();

      expect(
        Array.from(element.querySelectorAll('a')).some(
          (a) => a.textContent?.trim() === 'Evaluar manuscrito',
        ),
      ).toBe(false);
      expect(element.textContent).toContain('El plazo venció');
    });

    it('entrar al formulario por URL con el plazo vencido lo deja en solo lectura', async () => {
      signIn('REVIEWER');
      const { element, settle } = await open('/app/reviewer/assignments/a-1/evaluate');
      detail().flush(buildAssignmentDetail({ is_overdue: true, state: 'OVERDUE' }));
      evaluation().flush(buildCompleteEvaluation(), { headers: { ETag: '"2"' } });
      await settle();

      expect(element.querySelector('textarea')!.readOnly).toBe(true);
      expect(element.querySelector('textarea')!.value).toBe('Aclarar la metodología.');
      const submit = Array.from(element.querySelectorAll<HTMLButtonElement>('button')).find(
        (b) => b.textContent?.trim() === 'Enviar evaluación',
      );
      expect(submit?.disabled).toBe(true);
    });
  });

  describe('409 y 410 en el formulario', () => {
    const typeAndSave = async (
      element: HTMLElement,
      settle: () => Promise<void>,
      value: string,
    ) => {
      const area = element.querySelector<HTMLTextAreaElement>('textarea')!;
      area.value = value;
      area.dispatchEvent(new Event('input', { bubbles: true }));
      await settle();
      await click(element, 'Guardar borrador', settle);
    };

    it('410 al guardar deja el texto en pantalla y bloquea', async () => {
      signIn('REVIEWER');
      const { element, settle } = await open('/app/reviewer/assignments/a-1/evaluate');
      detail().flush(buildAssignmentDetail());
      evaluation().flush(buildCompleteEvaluation(), { headers: { ETag: '"2"' } });
      await settle();

      await typeAndSave(element, settle, 'Texto que debe sobrevivir');
      http
        .expectOne((r) => r.method === 'PUT')
        .flush(errorEnvelope('STATE_CONFLICT', 'Plazo vencido.'), {
          status: 410,
          statusText: 'Gone',
        });
      await settle();

      expect(element.querySelector('textarea')!.value).toBe('Texto que debe sobrevivir');
      expect(element.querySelector('textarea')!.readOnly).toBe(true);
      expect(element.textContent).toContain('El plazo de evaluación venció');
    });

    it('409 por versión conserva el texto y ofrece elegir', async () => {
      signIn('REVIEWER');
      const { element, settle } = await open('/app/reviewer/assignments/a-1/evaluate');
      detail().flush(buildAssignmentDetail());
      evaluation().flush(buildCompleteEvaluation(), { headers: { ETag: '"2"' } });
      await settle();

      await typeAndSave(element, settle, 'Mi texto');
      http
        .expectOne((r) => r.method === 'PUT')
        .flush(errorEnvelope('VERSION_CONFLICT', 'Desfasado.'), {
          status: 409,
          statusText: 'Conflict',
        });
      await settle();

      expect(element.querySelector('textarea')!.value).toBe('Mi texto');
      expect(element.textContent).toContain('El borrador cambió desde que lo abrió');
    });
  });

  describe('cambios sin guardar', () => {
    const dirtyForm = async () => {
      signIn('REVIEWER');
      const view = await open('/app/reviewer/assignments/a-1/evaluate');
      detail().flush(buildAssignmentDetail());
      evaluation().flush(buildReviewerEvaluation(), { headers: { ETag: '"0"' } });
      await view.settle();
      const area = view.element.querySelector<HTMLTextAreaElement>('textarea')!;
      area.value = 'Sin guardar';
      area.dispatchEvent(new Event('input', { bubbles: true }));
      await view.settle();
      return view;
    };

    it('advierte antes de abandonar y, si la persona se queda, no navega', async () => {
      const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
      const { element, settle } = await dirtyForm();

      await click(element, '← Volver al detalle de la asignación', settle);

      expect(confirm).toHaveBeenCalledTimes(1);
      expect(router.url).toBe('/app/reviewer/assignments/a-1/evaluate');
      expect(element.querySelector('textarea')!.value).toBe('Sin guardar');
    });

    it('si la persona acepta, abandona el formulario', async () => {
      vi.spyOn(window, 'confirm').mockReturnValue(true);
      const { element, settle } = await dirtyForm();

      await click(element, '← Volver al detalle de la asignación', settle);

      expect(router.url).toBe('/app/reviewer/assignments/a-1');
      detail().flush(buildAssignmentDetail());
      await settle();
    });

    it('sin cambios no advierte', async () => {
      const confirm = vi.spyOn(window, 'confirm');
      signIn('REVIEWER');
      const { element, settle } = await open('/app/reviewer/assignments/a-1/evaluate');
      detail().flush(buildAssignmentDetail());
      evaluation().flush(buildReviewerEvaluation(), { headers: { ETag: '"0"' } });
      await settle();

      await click(element, '← Volver al detalle de la asignación', settle);

      expect(confirm).not.toHaveBeenCalled();
      expect(router.url).toBe('/app/reviewer/assignments/a-1');
      detail().flush(buildAssignmentDetail());
      await settle();
    });
  });
});
