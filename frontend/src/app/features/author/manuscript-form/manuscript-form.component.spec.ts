import { Component } from '@angular/core';
import { provideHttpClient } from '@angular/common/http';
import {
  HttpTestingController,
  TestRequest,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';

import { AuthStore } from '../../../core/auth/auth.store';
import { unsavedChangesGuard } from '../../../core/auth/unsaved-changes.guard';
import { API_BASE_URL } from '../../../core/http/api-base-url.token';
import { MANUSCRIPT_STATUSES, ManuscriptStatus } from '../../../core/models/manuscript.model';
import { SessionUser } from '../../../core/models/session-user.model';
import {
  AUTHOR_ANA,
  AUTHOR_LUIS,
  buildManuscript,
  errorEnvelope,
} from '../testing/manuscript.fixtures';
import { ManuscriptFormComponent } from './manuscript-form.component';

@Component({ template: '' })
class BlankComponent {}

const ANA: SessionUser = {
  id: 'u-1',
  institutional_id: 'INST-0001',
  username: 'a.lopez',
  email: 'a.lopez@unl.edu.ec',
  first_name: 'Ana',
  last_name: 'López',
  full_name: 'Ana López',
};

describe('ManuscriptFormComponent', () => {
  let http: HttpTestingController;
  let router: Router;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideRouter([
          { path: 'app/author/manuscripts/new', component: ManuscriptFormComponent },
          { path: 'app/author/manuscripts/:id/edit', component: ManuscriptFormComponent },
          { path: 'app/author/manuscripts/:id', component: BlankComponent },
          { path: 'app/author/manuscripts', component: BlankComponent },
        ]),
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: API_BASE_URL, useValue: '/api/' },
      ],
    });
    http = TestBed.inject(HttpTestingController);
    router = TestBed.inject(Router);
    TestBed.inject(AuthStore).setSession({ user: ANA, roles: ['AUTHOR'], access: 'token' });
  });

  afterEach(() => http.verify());

  const open = async (url: string) => {
    const harness = await RouterTestingHarness.create();
    const component = await harness.navigateByUrl(url, ManuscriptFormComponent);
    const element = harness.routeNativeElement as HTMLElement;
    const settle = async () => {
      await harness.fixture.whenStable();
      harness.detectChanges();
    };
    await settle();
    return { harness, component, element, settle };
  };

  const create = () => open('/app/author/manuscripts/new');

  /** Abre la edición y responde la carga del manuscrito. */
  const edit = async (overrides = {}, etag = '"4"') => {
    const view = await open('/app/author/manuscripts/m-1/edit');
    http
      .expectOne('/api/manuscripts/m-1/')
      .flush(buildManuscript(overrides), { headers: { ETag: etag } });
    await view.settle();
    return view;
  };

  const type = (element: HTMLElement, selector: string, value: string) => {
    const input = element.querySelector(selector) as HTMLInputElement | HTMLTextAreaElement;
    input.value = value;
    input.dispatchEvent(new Event('input'));
  };

  const fillAuthor = (element: HTMLElement, index: number, author: Partial<typeof AUTHOR_ANA>) => {
    if (author.full_name !== undefined) type(element, `#author-name-${index}`, author.full_name);
    if (author.email !== undefined) type(element, `#author-email-${index}`, author.email);
    if (author.affiliation !== undefined)
      type(element, `#author-affiliation-${index}`, author.affiliation);
  };

  const fillGeneral = (element: HTMLElement) => {
    type(element, '#title', '  Efecto del clima  ');
    type(element, '#abstract', 'Resumen del estudio.');
    type(element, '#keywords', 'clima, Cultivos ; clima');
    type(element, '#area', 'Agronomía');
    type(element, '#language', 'es');
  };

  const submit = async (element: HTMLElement, settle: () => Promise<void>) => {
    (element.querySelector('form button[type="submit"]') as HTMLButtonElement).click();
    await settle();
  };

  const noWrites = () => {
    http.expectNone((r) => r.method !== 'GET');
  };

  const authorCards = (element: HTMLElement) => element.querySelectorAll('fieldset.author');

  describe('alta de un borrador', () => {
    it('precarga al autor que registra como único autor y responsable', async () => {
      const { component, element } = await create();

      expect(authorCards(element).length).toBe(1);
      expect(component.authors.getRawValue()).toEqual([
        {
          full_name: 'Ana López',
          email: 'a.lopez@unl.edu.ec',
          affiliation: '',
          is_corresponding: true,
        },
      ]);
      expect((element.querySelector('h1') as HTMLElement).textContent).toBe('Nuevo manuscrito');
    });

    it('guarda el borrador con el payload normalizado y navega al detalle', async () => {
      const { element, settle } = await create();
      fillGeneral(element);
      fillAuthor(element, 0, { affiliation: ' Universidad Nacional de Loja ' });

      await submit(element, settle);

      const request = http.expectOne('/api/manuscripts/');
      expect(request.request.method).toBe('POST');
      expect(request.request.body).toEqual({
        title: 'Efecto del clima',
        abstract: 'Resumen del estudio.',
        keywords: ['clima', 'Cultivos'],
        area: 'Agronomía',
        language: 'es',
        authors: [
          {
            full_name: 'Ana López',
            email: 'a.lopez@unl.edu.ec',
            affiliation: 'Universidad Nacional de Loja',
            is_corresponding: true,
          },
        ],
      });
      request.flush(buildManuscript({ id: 'nuevo-1' }), {
        status: 201,
        statusText: 'Created',
        headers: { ETag: '"0"' },
      });
      await settle();

      expect(router.url).toBe('/app/author/manuscripts/nuevo-1');
    });

    it('permite guardar un borrador con metadatos incompletos y avisa qué falta para enviarlo', async () => {
      const { element, settle } = await create();
      fillAuthor(element, 0, { affiliation: 'UNL' });
      await settle();

      expect(element.querySelector('.notice--warning')?.textContent).toContain(
        'Título, Resumen, Palabras clave, Área de conocimiento, Idioma',
      );

      await submit(element, settle);

      const request = http.expectOne('/api/manuscripts/');
      expect(request.request.body).toMatchObject({
        title: '',
        abstract: '',
        keywords: [],
        area: '',
        language: '',
      });
      request.flush(buildManuscript(), { status: 201, statusText: 'Created' });
    });

    it('el aviso desaparece al completar los metadatos', async () => {
      const { element, settle } = await create();
      fillGeneral(element);
      await settle();

      expect(element.querySelector('.notice--warning')).toBeNull();
    });
  });

  describe('lista de autores: el guardado se bloquea', () => {
    it('sin autores no se envía nada', async () => {
      const { component, element, settle } = await create();
      fillAuthor(element, 0, { affiliation: 'UNL' });

      component.authors.clear();
      await submit(element, settle);

      noWrites();
      expect(element.querySelector('#form-errors')?.textContent).toContain(
        'Debe indicar al menos un autor.',
      );
    });

    it('con más de un responsable no se envía nada', async () => {
      const { component, element, settle } = await create();
      fillAuthor(element, 0, { affiliation: 'UNL' });
      (element.querySelector('button.btn--ghost[type="button"]') as HTMLButtonElement).click();
      await settle();
      fillAuthor(element, 1, { ...AUTHOR_LUIS });
      component.authors.at(1).controls.is_corresponding.setValue(true);

      await submit(element, settle);

      noWrites();
      expect(element.querySelector('#form-errors')?.textContent).toContain(
        'Solo puede haber un autor responsable.',
      );
    });

    it('sin ningún responsable no se envía nada', async () => {
      const { component, element, settle } = await create();
      fillAuthor(element, 0, { affiliation: 'UNL' });
      component.authors.at(0).controls.is_corresponding.setValue(false);

      await submit(element, settle);

      noWrites();
      expect(element.querySelector('#form-errors')?.textContent).toContain(
        'Debe designar exactamente un autor responsable.',
      );
    });

    it('un correo repetido entre autores bloquea el guardado', async () => {
      const { element, settle } = await create();
      fillAuthor(element, 0, { affiliation: 'UNL' });
      (element.querySelector('button.btn--ghost[type="button"]') as HTMLButtonElement).click();
      await settle();
      fillAuthor(element, 1, {
        full_name: 'Otra Persona',
        email: 'A.LOPEZ@unl.edu.ec',
        affiliation: 'UNL',
      });

      await submit(element, settle);

      noWrites();
      expect(element.querySelector('#form-errors')?.textContent).toContain('no puede repetirse');
    });

    it('si el autor que registra no figura en la lista no se envía nada', async () => {
      const { element, settle } = await create();
      fillAuthor(element, 0, { email: 'otra.persona@unl.edu.ec', affiliation: 'UNL' });

      await submit(element, settle);

      noWrites();
      expect(element.querySelector('#form-errors')?.textContent).toContain(
        'debe figurar en la lista',
      );
    });

    it.each([
      ['el nombre', { full_name: '' }, 'Escriba el nombre completo.'],
      ['el correo', { email: 'no-es-un-correo' }, 'Escriba un correo válido.'],
      ['la filiación', { affiliation: '' }, 'Escriba la filiación.'],
    ])('%s vacío o inválido de un autor bloquea el guardado', async (_name, change, message) => {
      const { element, settle } = await create();
      fillAuthor(element, 0, { affiliation: 'UNL', ...change });

      await submit(element, settle);

      noWrites();
      expect(element.textContent).toContain(message);
    });

    it('un idioma que no es un código de dos letras bloquea el guardado', async () => {
      const { element, settle } = await create();
      fillAuthor(element, 0, { affiliation: 'UNL' });
      type(element, '#language', 'E1');

      await submit(element, settle);

      noWrites();
      expect(element.textContent).toContain('código de idioma de dos letras');
    });

    it('una palabra clave de más de 100 caracteres bloquea el guardado', async () => {
      const { element, settle } = await create();
      fillAuthor(element, 0, { affiliation: 'UNL' });
      type(element, '#keywords', 'a'.repeat(101));

      await submit(element, settle);

      noWrites();
      expect(element.textContent).toContain('hasta 100 caracteres');
    });
  });

  describe('gestión de autores', () => {
    it('agrega y quita autores; con uno solo no se puede quitar', async () => {
      const { component, element, settle } = await create();
      const remove = () =>
        Array.from(element.querySelectorAll<HTMLButtonElement>('button.btn--danger'));
      expect(remove()[0].disabled).toBe(true);

      (element.querySelector('button.btn--ghost[type="button"]') as HTMLButtonElement).click();
      await settle();
      expect(authorCards(element).length).toBe(2);
      expect(remove().every((button) => !button.disabled)).toBe(true);

      remove()[1].click();
      await settle();
      expect(authorCards(element).length).toBe(1);
      expect(component.authors.length).toBe(1);
    });

    it('el segundo autor nace sin ser responsable', async () => {
      const { component, element, settle } = await create();
      (element.querySelector('button.btn--ghost[type="button"]') as HTMLButtonElement).click();
      await settle();

      expect(component.authors.getRawValue().map((a) => a.is_corresponding)).toEqual([true, false]);
    });

    it('elegir un responsable desmarca al anterior: siempre exactamente uno', async () => {
      const { component, element, settle } = await create();
      (element.querySelector('button.btn--ghost[type="button"]') as HTMLButtonElement).click();
      await settle();

      const radios = element.querySelectorAll<HTMLInputElement>('input[type="radio"]');
      radios[1].click();
      await settle();

      expect(component.authors.getRawValue().map((a) => a.is_corresponding)).toEqual([false, true]);
      expect(component.authors.errors).toBeNull();
    });
  });

  describe('cambios sin guardar', () => {
    it('no advierte si no se tocó nada', async () => {
      const { component } = await create();

      expect(component.hasUnsavedChanges()).toBe(false);
      expect(unsavedChangesGuard(component, null as never, null as never, null as never)).toBe(
        true,
      );
    });

    it('advierte tras editar y deja de advertir tras guardar', async () => {
      const { component, element, settle } = await create();
      type(element, '#title', 'Algo');
      expect(component.hasUnsavedChanges()).toBe(true);

      fillAuthor(element, 0, { affiliation: 'UNL' });
      await submit(element, settle);
      http
        .expectOne('/api/manuscripts/')
        .flush(buildManuscript({ id: 'x' }), { status: 201, statusText: 'Created' });
      await settle();

      expect(component.hasUnsavedChanges()).toBe(false);
    });

    it('agregar un autor también cuenta como cambio', async () => {
      const { component, element, settle } = await create();
      (element.querySelector('button.btn--ghost[type="button"]') as HTMLButtonElement).click();
      await settle();

      expect(component.hasUnsavedChanges()).toBe(true);
    });
  });

  describe('errores del servidor', () => {
    const fillValid = (element: HTMLElement) => {
      fillGeneral(element);
      fillAuthor(element, 0, { affiliation: 'UNL' });
    };

    it('muestra el error de validación junto a su campo', async () => {
      const { element, settle } = await create();
      fillValid(element);
      await submit(element, settle);

      http.expectOne('/api/manuscripts/').flush(
        errorEnvelope('VALIDATION_ERROR', 'Los datos enviados no son válidos.', {
          title: ['Asegúrese de que este campo no tenga más de 300 caracteres.'],
        }),
        { status: 400, statusText: 'Bad Request' },
      );
      await settle();

      expect(element.querySelector('#title + .field__error')?.textContent).toContain(
        '300 caracteres',
      );
    });

    it('muestra el error de la lista de autores del servidor', async () => {
      const { element, settle } = await create();
      fillValid(element);
      await submit(element, settle);

      http.expectOne('/api/manuscripts/').flush(
        errorEnvelope('VALIDATION_ERROR', 'Los datos enviados no son válidos.', {
          authors: ['El autor que registra el manuscrito debe figurar en la lista de autores.'],
        }),
        { status: 400, statusText: 'Bad Request' },
      );
      await settle();

      expect(element.textContent).toContain('debe figurar en la lista de autores');
    });

    it('un error genérico muestra el mensaje accionable y permite reintentar', async () => {
      const { element, settle } = await create();
      fillValid(element);
      await submit(element, settle);

      http
        .expectOne('/api/manuscripts/')
        .flush(errorEnvelope('AUDIT_UNAVAILABLE', 'Sin auditoría.'), {
          status: 503,
          statusText: 'Unavailable',
        });
      await settle();

      expect(element.querySelector('.notice--danger')?.textContent).toContain(
        'Servicio no disponible',
      );
      const button = element.querySelector('form button[type="submit"]') as HTMLButtonElement;
      expect(button.disabled).toBe(false);
      expect(button.textContent?.trim()).toBe('Guardar borrador');
    });

    it('no envía dos veces mientras guarda', async () => {
      const { element, settle } = await create();
      fillValid(element);

      await submit(element, settle);
      await submit(element, settle);

      http
        .expectOne('/api/manuscripts/')
        .flush(buildManuscript(), { status: 201, statusText: 'Created' });
    });
  });

  describe('edición', () => {
    it('carga el manuscrito: datos, palabras clave y autores en orden', async () => {
      const { component, element } = await edit({
        title: 'Título vigente',
        keywords: ['clima', 'suelo'],
        authors: [
          { ...AUTHOR_LUIS, author_order: 2 },
          { ...AUTHOR_ANA, author_order: 1 },
        ],
      });

      expect((element.querySelector('h1') as HTMLElement).textContent).toBe('Editar manuscrito');
      expect((element.querySelector('#title') as HTMLInputElement).value).toBe('Título vigente');
      expect((element.querySelector('#keywords') as HTMLInputElement).value).toBe('clima, suelo');
      expect(component.authors.getRawValue().map((a) => a.full_name)).toEqual([
        'Ana López',
        'Luis Pérez',
      ]);
      expect(component.hasUnsavedChanges()).toBe(false);
    });

    it('guarda con PATCH reenviando el ETag en If-Match y navega al detalle', async () => {
      const { element, settle } = await edit({}, '"7"');
      type(element, '#title', 'Título corregido');

      await submit(element, settle);

      const request = http.expectOne('/api/manuscripts/m-1/');
      expect(request.request.method).toBe('PATCH');
      expect(request.request.headers.get('If-Match')).toBe('"7"');
      expect(request.request.body.title).toBe('Título corregido');
      request.flush(buildManuscript({ title: 'Título corregido' }), { headers: { ETag: '"8"' } });
      await settle();

      expect(router.url).toBe('/app/author/manuscripts/m-1');
    });

    it('sin ETag no intenta guardar y pide recargar', async () => {
      const view = await open('/app/author/manuscripts/m-1/edit');
      http.expectOne('/api/manuscripts/m-1/').flush(buildManuscript());
      await view.settle();

      await submit(view.element, view.settle);

      noWrites();
      expect(view.element.textContent).toContain('Recargue el manuscrito');
    });

    it('un borrador puede dejar metadatos vacíos', async () => {
      const { element, settle } = await edit({ status: 'DRAFT' });
      type(element, '#title', '');

      await submit(element, settle);

      const request = http.expectOne('/api/manuscripts/m-1/');
      expect(request.request.body.title).toBe('');
      request.flush(buildManuscript());
    });

    it('en Requiere correcciones los metadatos obligatorios no pueden quedar vacíos', async () => {
      const { element, settle } = await edit({ status: 'REQUIRES_CORRECTIONS' });
      expect(element.querySelector('.notice--warning')).toBeNull();
      type(element, '#title', '');
      type(element, '#keywords', '');

      await submit(element, settle);

      noWrites();
      expect(element.textContent).toContain('Este campo es obligatorio.');
      expect(
        (element.querySelector('#title') as HTMLInputElement).getAttribute('aria-required'),
      ).toBe('true');
    });

    it.each(MANUSCRIPT_STATUSES.filter((s) => s !== 'DRAFT' && s !== 'REQUIRES_CORRECTIONS'))(
      'en %s el formulario queda bloqueado y explica por qué',
      async (status: ManuscriptStatus) => {
        const { element, settle } = await edit({ status });

        expect(element.querySelector('.notice--warning')?.textContent).toContain(
          'no admite edición',
        );
        expect((element.querySelector('#title') as HTMLInputElement).disabled).toBe(true);
        expect(
          (element.querySelector('form button[type="submit"]') as HTMLButtonElement).disabled,
        ).toBe(true);

        await submit(element, settle);
        noWrites();
      },
    );

    it('un manuscrito dado de baja no se edita aunque su estado lo permitiría', async () => {
      const { element } = await edit({ status: 'DRAFT', is_active: false });

      expect(element.querySelector('.notice--warning')?.textContent).toContain('fue dado de baja');
      expect((element.querySelector('#title') as HTMLInputElement).disabled).toBe(true);
    });

    it('un conflicto de versión se explica y recargar trae los datos vigentes', async () => {
      const { component, element, settle } = await edit({ title: 'Mi versión' }, '"1"');
      type(element, '#title', 'Mis cambios');
      await submit(element, settle);

      http
        .expectOne('/api/manuscripts/m-1/')
        .flush(errorEnvelope('VERSION_CONFLICT', 'Cambió.', { lock_version: 2 }), {
          status: 409,
          statusText: 'Conflict',
        });
      await settle();

      expect(element.querySelector('.notice--warning[role="alert"]')?.textContent).toContain(
        'cambiaron',
      );

      (
        Array.from(element.querySelectorAll('button')).find(
          (b) => b.textContent?.trim() === 'Recargar datos',
        ) as HTMLButtonElement
      ).click();
      await settle();
      http.expectOne('/api/manuscripts/m-1/').flush(buildManuscript({ title: 'Título del otro' }), {
        headers: { ETag: '"2"' },
      });
      await settle();

      expect(element.querySelector('.notice--warning[role="alert"]')).toBeNull();
      expect((element.querySelector('#title') as HTMLInputElement).value).toBe('Título del otro');
      expect(component.hasUnsavedChanges()).toBe(false);
    });

    it('un manuscrito ajeno o inexistente muestra el error sin revelar nada y permite reintentar', async () => {
      const { element, settle } = await open('/app/author/manuscripts/ajeno/edit');
      http
        .expectOne('/api/manuscripts/ajeno/')
        .flush(errorEnvelope('NOT_FOUND', 'No encontrado.'), {
          status: 404,
          statusText: 'Not Found',
        });
      await settle();

      expect(element.querySelector('app-error-state')?.textContent).toContain(
        'no existe o no está disponible',
      );
      expect(element.querySelector('form')).toBeNull();

      (element.querySelector('app-error-state button') as HTMLButtonElement).click();
      await settle();
      http
        .expectOne('/api/manuscripts/ajeno/')
        .flush(buildManuscript(), { headers: { ETag: '"0"' } });
      await settle();
      expect(element.querySelector('form')).not.toBeNull();
    });

    it('«Cancelar» vuelve al detalle del manuscrito', async () => {
      const { element } = await edit();

      const cancel = Array.from(element.querySelectorAll('a.btn')).find(
        (a) => a.textContent?.trim() === 'Cancelar',
      ) as HTMLAnchorElement;
      expect(cancel.getAttribute('href')).toBe('/app/author/manuscripts/m-1');
    });
  });
});
