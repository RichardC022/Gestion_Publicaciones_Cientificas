import { Component, signal } from '@angular/core';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { API_BASE_URL } from '../../../core/http/api-base-url.token';
import { EligibilityDiagnosis, EligibleReviewer } from '../../../core/models/editor.model';
import { errorEnvelope } from '../../author/testing/manuscript.fixtures';
import { buildReviewer } from '../testing/editor.fixtures';
import { ReviewerPickerComponent, explainNoReviewers } from './reviewer-picker.component';

@Component({
  imports: [ReviewerPickerComponent],
  template: `<app-reviewer-picker
    [manuscriptId]="manuscriptId()"
    area="Agronomía"
    [disabled]="disabled()"
    (selected)="chosen.push($event)"
  />`,
})
class HostComponent {
  readonly manuscriptId = signal('s-1');
  readonly disabled = signal(false);
  readonly chosen: EligibleReviewer[] = [];
}

const page = (results: EligibleReviewer[], diagnosis?: EligibilityDiagnosis) => ({
  count: results.length,
  next: null,
  previous: null,
  results,
  ...(diagnosis ? { diagnosis } : {}),
});

describe('ReviewerPickerComponent', () => {
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: API_BASE_URL, useValue: '/api/' },
      ],
    });
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  const request = () => http.expectOne((r) => r.url === '/api/editor/reviewers/');
  const text = (node: Element | null) => (node?.textContent ?? '').replace(/\s+/g, ' ').trim();

  const open = async () => {
    const fixture = TestBed.createComponent(HostComponent);
    fixture.detectChanges();
    const element = fixture.nativeElement as HTMLElement;
    const settle = async () => {
      await fixture.whenStable();
      fixture.detectChanges();
    };
    return { fixture, host: fixture.componentInstance, element, settle };
  };

  const items = (element: HTMLElement) => Array.from(element.querySelectorAll('.picker__item'));

  describe('lista', () => {
    it('pide los candidatos del manuscrito y los muestra con sus áreas y su carga', async () => {
      const { element, settle } = await open();
      expect(element.querySelector('app-loading-spinner')).not.toBeNull();

      const call = request();
      expect(call.request.params.get('manuscript_id')).toBe('s-1');
      call.flush(
        page([
          buildReviewer({
            full_name: 'Marta Ruiz',
            email: 'marta@unl.edu.ec',
            expertise_areas: ['Agronomía', 'Edafología'],
            active_assignments: 1,
            max_active_assignments: 3,
          }),
        ]),
      );
      await settle();

      expect(element.querySelector('app-loading-spinner')).toBeNull();
      const row = text(items(element)[0]);
      expect(row).toContain('Marta Ruiz');
      expect(row).toContain('marta@unl.edu.ec');
      expect(row).toContain('Áreas: Agronomía, Edafología');
      expect(row).toContain('Carga: 1 de 3 asignaciones activas');
      expect(row).not.toContain('Carga completa');
    });

    it('seleccionar emite el Revisor elegido', async () => {
      const { element, host, settle } = await open();
      const marta = buildReviewer({ id: 'r-1', full_name: 'Marta Ruiz' });
      const luis = buildReviewer({ id: 'r-2', full_name: 'Luis Vega', email: 'luis@unl.edu.ec' });
      request().flush(page([marta, luis]));
      await settle();

      (items(element)[1].querySelector('button') as HTMLButtonElement).click();

      expect(host.chosen).toEqual([luis]);
    });

    it('con la carga completa lo advierte y no permite seleccionarlo', async () => {
      const { element, host, settle } = await open();
      request().flush(
        page([buildReviewer({ full_name: 'Marta Ruiz', active_assignments: 3, max_active_assignments: 3 })]),
      );
      await settle();

      const button = items(element)[0].querySelector('button') as HTMLButtonElement;
      expect(text(items(element)[0])).toContain('Carga completa');
      expect(button.disabled).toBe(true);
      button.click();
      expect(host.chosen).toEqual([]);
    });

    it('mientras hay una acción en curso bloquea la selección', async () => {
      const { element, host, fixture, settle } = await open();
      request().flush(page([buildReviewer()]));
      await settle();

      host.disabled.set(true);
      fixture.detectChanges();

      expect((items(element)[0].querySelector('button') as HTMLButtonElement).disabled).toBe(true);
    });
  });

  describe('búsqueda', () => {
    const search = async (element: HTMLElement, value: string, settle: () => Promise<void>) => {
      const input = element.querySelector('input[type="search"]') as HTMLInputElement;
      input.value = value;
      input.dispatchEvent(new Event('input'));
      await settle();
    };

    it('filtra por nombre, correo, código institucional o área sin volver a consultar', async () => {
      const { element, settle } = await open();
      request().flush(
        page([
          buildReviewer({ id: 'r-1', full_name: 'Marta Ruiz', institutional_id: 'INST-0001' }),
          buildReviewer({
            id: 'r-2',
            full_name: 'Luis Vega',
            email: 'lvega@unl.edu.ec',
            institutional_id: 'INST-0002',
            expertise_areas: ['Medicina'],
          }),
        ]),
      );
      await settle();

      await search(element, 'vega', settle);
      expect(items(element).map((i) => text(i.querySelector('strong')))).toEqual(['Luis Vega']);
      await search(element, 'INST-0001', settle);
      expect(items(element).map((i) => text(i.querySelector('strong')))).toEqual(['Marta Ruiz']);
      await search(element, 'medicina', settle);
      expect(items(element).map((i) => text(i.querySelector('strong')))).toEqual(['Luis Vega']);
      expect(text(element.querySelector('.picker__count'))).toBe('1 de 2 Revisores');
    });

    it('si nadie coincide lo dice', async () => {
      const { element, settle } = await open();
      request().flush(page([buildReviewer()]));
      await settle();

      await search(element, 'zzz', settle);

      expect(items(element).length).toBe(0);
      expect(text(element)).toContain('Ningún Revisor coincide con la búsqueda.');
    });
  });

  describe('sin Revisores elegibles', () => {
    it('explica la causa con las cifras del diagnóstico, no una lista vacía', async () => {
      const { element, settle } = await open();
      request().flush(
        page([], { reviewers: 6, conflict: 1, no_profile: 1, unavailable: 2, other_area: 2 }),
      );
      await settle();

      const empty = text(element.querySelector('.picker__empty'));
      expect(empty).toContain('No hay Revisores elegibles.');
      expect(empty).toContain('Hay 6 Revisores con cuenta activa, pero ninguno es elegible');
      expect(empty).toContain('2 no declaran el área «Agronomía».');
      expect(empty).toContain('2 marcaron que no están disponibles.');
      expect(empty).toContain('1 figura como autor del manuscrito (conflicto de interés).');
      expect(empty).toContain('1 no tiene perfil de revisor');
      expect(element.querySelector('.picker__item')).toBeNull();
      expect(element.querySelector('input[type="search"]')).toBeNull();
    });

    it('sin cuentas de Revisor lo dice', async () => {
      const { element, settle } = await open();
      request().flush(
        page([], { reviewers: 0, conflict: 0, no_profile: 0, unavailable: 0, other_area: 0 }),
      );
      await settle();

      expect(text(element.querySelector('.picker__empty'))).toContain(
        'No hay cuentas con el rol de Revisor activo en el sistema.',
      );
    });
  });

  describe('errores y cambios', () => {
    it('un error del servidor se explica y permite reintentar', async () => {
      const { element, settle } = await open();
      request().flush(errorEnvelope('SERVER_ERROR', 'Error interno.'), {
        status: 500,
        statusText: 'Server Error',
      });
      await settle();

      expect(element.querySelector('app-error-state')).not.toBeNull();
      expect(element.querySelector('.picker__item')).toBeNull();

      (element.querySelector('app-error-state button') as HTMLButtonElement).click();
      await settle();
      request().flush(page([buildReviewer()]));
      await settle();

      expect(element.querySelector('app-error-state')).toBeNull();
      expect(items(element).length).toBe(1);
    });

    it('al cambiar de manuscrito vuelve a consultar', async () => {
      const { host, fixture, element, settle } = await open();
      request().flush(page([buildReviewer()]));
      await settle();

      host.manuscriptId.set('s-2');
      fixture.detectChanges();

      expect(request().request.params.get('manuscript_id')).toBe('s-2');
      expect(element.querySelector('app-loading-spinner')).not.toBeNull();
    });
  });
});

describe('explainNoReviewers', () => {
  const base: EligibilityDiagnosis = {
    reviewers: 1,
    conflict: 0,
    no_profile: 0,
    unavailable: 0,
    other_area: 0,
  };

  it('usa singular y plural y omite las causas en cero', () => {
    expect(explainNoReviewers({ ...base, reviewers: 1, other_area: 1 }, 'Agronomía')).toEqual([
      'Hay 1 Revisor con cuenta activa, pero ninguno es elegible:',
      '1 no declara el área «Agronomía».',
    ]);
  });

  it('sin área conocida habla del área del manuscrito', () => {
    expect(explainNoReviewers({ ...base, other_area: 2, reviewers: 2 })[1]).toBe(
      '2 no declaran el área del manuscrito.',
    );
  });

  it('sin diagnóstico no inventa una causa', () => {
    expect(explainNoReviewers(undefined)).toEqual([
      'No se pudo determinar la causa; intente de nuevo.',
    ]);
  });
});
