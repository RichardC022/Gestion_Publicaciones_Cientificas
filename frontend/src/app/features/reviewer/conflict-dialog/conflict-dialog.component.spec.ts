import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';

import { API_BASE_URL } from '../../../core/http/api-base-url.token';
import { EvaluationSnapshot } from '../../../core/models/reviewer.model';
import { errorEnvelope } from '../../author/testing/manuscript.fixtures';
import { buildReviewerEvaluation } from '../testing/reviewer.fixtures';
import { ConflictDialogComponent } from './conflict-dialog.component';

const CONFLICT = '/api/reviewer/assignments/a-1/conflict/';

describe('ConflictDialogComponent', () => {
  let http: HttpTestingController;
  let fixture: ComponentFixture<ConflictDialogComponent>;
  let declared: EvaluationSnapshot[];
  let cancelled: number;

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
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: API_BASE_URL, useValue: '/api/' },
      ],
    });
    http = TestBed.inject(HttpTestingController);
    declared = [];
    cancelled = 0;
  });

  afterEach(() => http.verify());

  const text = (node: Element | null) => (node?.textContent ?? '').replace(/\s+/g, ' ').trim();
  const root = () => fixture.nativeElement as HTMLElement;
  const dialog = () => root().querySelector('dialog') as HTMLDialogElement;
  const button = (label: string) =>
    Array.from(root().querySelectorAll<HTMLButtonElement>('button')).find(
      (b) => text(b) === label,
    )!;

  const render = async (open = true, unsavedChanges = false) => {
    fixture = TestBed.createComponent(ConflictDialogComponent);
    fixture.componentRef.setInput('assignmentId', 'a-1');
    fixture.componentRef.setInput('open', open);
    fixture.componentRef.setInput('unsavedChanges', unsavedChanges);
    fixture.componentInstance.declared.subscribe((value) => declared.push(value));
    fixture.componentInstance.cancelled.subscribe(() => cancelled++);
    await fixture.whenStable();
  };

  const type = async (value: string) => {
    const area = root().querySelector<HTMLTextAreaElement>('textarea')!;
    area.value = value;
    area.dispatchEvent(new Event('input', { bubbles: true }));
    await fixture.whenStable();
  };

  it('se abre y explica que bloquea la evaluación, avisa al Editor y no se deshace', async () => {
    await render();

    expect(dialog().hasAttribute('open')).toBe(true);
    const body = text(dialog());
    expect(body).toContain('bloqueada');
    expect(body).toContain('El Editor será avisado');
    expect(body).toContain('No se puede deshacer');
  });

  it('cerrado no muestra el diálogo', async () => {
    await render(false);

    expect(dialog().hasAttribute('open')).toBe(false);
  });

  it('avisa de que los cambios sin guardar se perderán solo si los hay', async () => {
    await render(true, true);
    expect(text(dialog())).toContain('cambios sin guardar');
    fixture.destroy();

    await render(true, false);
    expect(text(dialog())).not.toContain('cambios sin guardar');
  });

  it('el motivo es opcional: sin motivo envía un cuerpo vacío', async () => {
    await render();

    button('Declarar conflicto').click();
    const request = http.expectOne(CONFLICT);
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual({});
    request.flush(buildReviewerEvaluation({ id: 'ev-1', conflict_declared: true }), {
      headers: { ETag: '"2"' },
    });
    await fixture.whenStable();
  });

  it('con motivo lo envía recortado y entrega la evaluación bloqueada', async () => {
    await render();
    await type('  Fui director de tesis de un autor.  ');

    button('Declarar conflicto').click();
    const request = http.expectOne(CONFLICT);
    expect(request.request.body).toEqual({ reason: 'Fui director de tesis de un autor.' });
    request.flush(buildReviewerEvaluation({ id: 'ev-1', conflict_declared: true }), {
      headers: { ETag: '"2"' },
    });
    await fixture.whenStable();

    expect(declared).toHaveLength(1);
    expect(declared[0].evaluation.conflict_declared).toBe(true);
    expect(declared[0].etag).toBe('"2"');
  });

  it('mientras se envía bloquea los controles y no admite un segundo envío', async () => {
    await render();

    button('Declarar conflicto').click();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(button('Declarando…').disabled).toBe(true);
    expect(button('Cancelar').disabled).toBe(true);
    button('Declarando…').click();
    http.expectOne(CONFLICT).flush(buildReviewerEvaluation({ conflict_declared: true }), {
      headers: { ETag: '"2"' },
    });
  });

  it('un error de red no da el conflicto por declarado y conserva el motivo', async () => {
    await render();
    await type('Motivo importante');

    button('Declarar conflicto').click();
    http.expectOne(CONFLICT).error(new ProgressEvent('error'));
    await fixture.whenStable();
    fixture.detectChanges();

    expect(declared).toHaveLength(0);
    expect(text(root().querySelector('[role="alert"]'))).toContain('No fue posible conectar');
    expect(root().querySelector('textarea')!.value).toBe('Motivo importante');
    expect(button('Declarar conflicto').disabled).toBe(false);
  });

  it('un 409 muestra el mensaje del servidor y no declara nada', async () => {
    await render();

    button('Declarar conflicto').click();
    http
      .expectOne(CONFLICT)
      .flush(errorEnvelope('STATE_CONFLICT', 'El conflicto de interés ya fue declarado.'), {
        status: 409,
        statusText: 'Conflict',
      });
    await fixture.whenStable();
    fixture.detectChanges();

    expect(declared).toHaveLength(0);
    expect(text(root().querySelector('[role="alert"]'))).toBe(
      'El conflicto de interés ya fue declarado.',
    );
  });

  it('un 503 de auditoría pide reintentar más tarde', async () => {
    await render();

    button('Declarar conflicto').click();
    http.expectOne(CONFLICT).flush(errorEnvelope('AUDIT_UNAVAILABLE', 'Sin auditoría.'), {
      status: 503,
      statusText: 'Service Unavailable',
    });
    await fixture.whenStable();
    fixture.detectChanges();

    expect(declared).toHaveLength(0);
    expect(text(root().querySelector('[role="alert"]'))).toContain('no disponible temporalmente');
  });

  it('cancelar no envía nada y avisa al contenedor', async () => {
    await render();

    button('Cancelar').click();

    http.expectNone(CONFLICT);
    expect(cancelled).toBe(1);
  });

  it('cada apertura empieza limpia', async () => {
    await render();
    await type('Texto viejo');
    fixture.componentRef.setInput('open', false);
    await fixture.whenStable();

    fixture.componentRef.setInput('open', true);
    await fixture.whenStable();
    fixture.detectChanges();

    expect(root().querySelector('textarea')!.value).toBe('');
  });
});
