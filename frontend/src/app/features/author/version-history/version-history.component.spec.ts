import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';

import { API_BASE_URL } from '../../../core/http/api-base-url.token';
import { HistoryEntry, Manuscript } from '../../../core/models/manuscript.model';
import { Paginated } from '../../../core/models/paginated.model';
import { buildManuscript, errorEnvelope } from '../testing/manuscript.fixtures';
import { VersionHistoryComponent } from './version-history.component';

const SEAL_1 = 'a'.repeat(64);
const SEAL_2 = 'c'.repeat(64);
const META = 'b'.repeat(64);

const HISTORY: HistoryEntry[] = [
  {
    type: 'CREATED',
    occurred_at: '2026-10-20T14:00:00Z',
    from_status: null,
    to_status: 'DRAFT',
    reason: null,
    version_number: null,
    round_number: null,
  },
  {
    type: 'VERSION_SUBMITTED',
    occurred_at: '2026-10-20T15:30:00Z',
    version_id: 'v-1',
    version_number: 1,
    round_number: 0,
    original_filename: 'primera.pdf',
    original_size_bytes: 2_621_440,
    integrity_seal: `sha256:${SEAL_1}`,
    metadata_sha256: META,
  },
  {
    type: 'ROUND_OPENED',
    occurred_at: '2026-10-20T15:30:00Z',
    round_number: 0,
    closed_at: '2026-10-20T15:30:00Z',
    closed_by_version_number: 1,
  },
  {
    type: 'STATUS_CHANGED',
    occurred_at: '2026-10-20T15:30:01Z',
    from_status: 'DRAFT',
    to_status: 'SUBMITTED',
    reason: null,
    version_number: 1,
    round_number: 0,
  },
  {
    type: 'ROUND_OPENED',
    occurred_at: '2026-10-22T10:00:00Z',
    round_number: 1,
    closed_at: null,
    closed_by_version_number: null,
  },
  {
    type: 'VERSION_SUBMITTED',
    occurred_at: '2026-10-23T16:00:00Z',
    version_id: 'v-2',
    version_number: 2,
    round_number: 1,
    original_filename: 'segunda.pdf',
    original_size_bytes: 1_048_576,
    integrity_seal: `sha256:${SEAL_2}`,
    metadata_sha256: META,
  },
];

const page = (results: HistoryEntry[], next: string | null = null): Paginated<HistoryEntry> => ({
  count: results.length,
  next,
  previous: null,
  results,
});

describe('VersionHistoryComponent', () => {
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideRouter([
          { path: 'app/author/manuscripts/:id/history', component: VersionHistoryComponent },
        ]),
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: API_BASE_URL, useValue: '/api/' },
      ],
    });
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  const historyRequest = () => http.expectOne((r) => r.url === '/api/manuscripts/m-1/history/');

  /** Abre la pantalla y responde el manuscrito y su historial. */
  const open = async (
    entries: HistoryEntry[] = HISTORY,
    manuscript: Partial<Manuscript> = { status: 'SUBMITTED', current_version: 2, current_round: 1 },
    next: string | null = null,
  ) => {
    const harness = await RouterTestingHarness.create();
    await harness.navigateByUrl('/app/author/manuscripts/m-1/history', VersionHistoryComponent);
    const element = harness.routeNativeElement as HTMLElement;
    const settle = async () => {
      await harness.fixture.whenStable();
      harness.detectChanges();
    };
    http
      .expectOne('/api/manuscripts/m-1/')
      .flush(buildManuscript(manuscript), { headers: { ETag: '"1"' } });
    historyRequest().flush(page(entries, next));
    await settle();
    return { element, settle };
  };

  const text = (element: Element) => (element.textContent ?? '').replace(/\s+/g, ' ').trim();
  const items = (element: HTMLElement) => Array.from(element.querySelectorAll('ol.timeline > li'));
  const versionCards = (element: HTMLElement) =>
    Array.from(element.querySelectorAll<HTMLElement>('article.timeline__card--version'));

  describe('línea de tiempo', () => {
    it('muestra los eventos en orden cronológico', async () => {
      const { element } = await open();

      // Une los nodos del encabezado: en un contenedor flex no llevan espacio entre sí.
      const titles = items(element).map((item) =>
        Array.from(item.querySelector('h2')?.childNodes ?? [])
          .filter((node) => node.nodeType === Node.ELEMENT_NODE || node.nodeType === Node.TEXT_NODE)
          .map((node) => node.textContent?.trim())
          .filter(Boolean)
          .join(' '),
      );
      expect(titles).toEqual([
        'Borrador creado',
        'Versión v1 Ronda 0',
        'Ronda 0',
        'Cambio de estado',
        'Ronda 1',
        'Versión v2 Ronda 1 Vigente',
      ]);
    });

    it('encabeza con el código, el título y el estado del manuscrito', async () => {
      const { element } = await open();

      const subject = text(element.querySelector('.history-subject') as HTMLElement);
      expect(subject).toContain('GPC-2026-000001');
      expect(subject).toContain('Efecto del clima en cultivos andinos');
      expect(subject).toContain('Enviado');
    });

    it('explica que el historial es inmutable', async () => {
      const { element } = await open();

      expect(text(element.querySelector('.history-note') as HTMLElement)).toContain('inmutable');
    });

    it('muestra las fechas en la zona institucional (UTC-5)', async () => {
      const { element } = await open();

      // 15:30 UTC son las 10:30 en Guayaquil.
      expect(text(items(element)[1])).toContain('20/10/2026 10:30');
      expect(text(items(element)[5])).toContain('23/10/2026 11:00');
    });

    it('cada fecha es un elemento time con su instante exacto', async () => {
      const { element } = await open();

      const time = items(element)[1].querySelector('time') as HTMLTimeElement;
      expect(time.getAttribute('datetime')).toBe('2026-10-20T15:30:00Z');
    });
  });

  describe('versiones: hash, ronda y solo lectura', () => {
    it('cada versión muestra versión, ronda, archivo, tamaño y ambos sellos', async () => {
      const { element } = await open();

      const [first, second] = versionCards(element);
      expect(text(first)).toContain('Versión v1');
      expect(text(first)).toContain('Ronda 0');
      expect(text(first)).toContain('primera.pdf');
      expect(text(first)).toContain('2,5 MB');
      expect(text(first)).toContain(`sha256:${SEAL_1}`);
      expect(text(first)).toContain(`sha256:${META}`);
      expect(text(second)).toContain('Versión v2');
      expect(text(second)).toContain('Ronda 1');
      expect(text(second)).toContain(`sha256:${SEAL_2}`);
    });

    it('las versiones anteriores también conservan su sello completo', async () => {
      const { element } = await open();

      const previous = versionCards(element)[0];
      expect(previous.querySelector('code')?.textContent).toBe(`sha256:${SEAL_1}`);
      expect((previous.querySelector('code')?.textContent ?? '').length).toBe(
        'sha256:'.length + 64,
      );
    });

    it('solo la versión vigente se marca como «Vigente»', async () => {
      const { element } = await open();

      const [first, second] = versionCards(element);
      expect(text(first)).not.toContain('Vigente');
      expect(text(second)).toContain('Vigente');
    });

    it('es de solo lectura: ningún campo, edición ni reemplazo', async () => {
      const { element } = await open();

      expect(element.querySelector('input, textarea, select')).toBeNull();
      const actions = Array.from(element.querySelectorAll('button, a')).map((e) => text(e));
      for (const forbidden of ['Editar', 'Reemplazar', 'Eliminar', 'Borrar', 'Subir']) {
        expect(actions.some((label) => label.includes(forbidden))).toBe(false);
      }
    });

    it('la única acción de cada versión es descargar su PDF exacto', async () => {
      const { element } = await open();

      for (const card of versionCards(element)) {
        const buttons = Array.from(card.querySelectorAll('button'));
        expect(buttons.map((b) => text(b))).toEqual(['Descargar PDF exacto']);
      }
    });

    it('no muestra rutas internas, copia sanitizada ni actores', async () => {
      const { element } = await open();

      const content = text(element).toLowerCase();
      for (const leaked of ['private/', 'sanitized', 'manuscripts/', 'actor']) {
        expect(content).not.toContain(leaked);
      }
    });
  });

  describe('rondas y estados', () => {
    it('una ronda cerrada indica la versión que la cerró', async () => {
      const { element } = await open();

      expect(text(items(element)[2])).toContain('Cerrada con la versión v1');
    });

    it('una ronda abierta indica que espera la nueva versión', async () => {
      const { element } = await open();

      expect(text(items(element)[4])).toContain('Abierta: a la espera de la nueva versión.');
    });

    it('un cambio de estado muestra el estado anterior y el nuevo', async () => {
      const { element } = await open();

      const change = text(items(element)[3]);
      expect(change).toContain('Borrador');
      expect(change).toContain('Enviado');
      expect(change).toContain('Versión v1');
    });

    it('la baja lógica aparece con su motivo y aclara que el historial se conserva', async () => {
      const withdrawn: HistoryEntry = {
        type: 'WITHDRAWN',
        occurred_at: '2026-10-24T12:00:00Z',
        from_status: 'SUBMITTED',
        to_status: 'SUBMITTED',
        reason: 'Ya no deseo continuar.',
        version_number: null,
        round_number: null,
      };
      const { element } = await open([...HISTORY, withdrawn], {
        status: 'SUBMITTED',
        current_version: 2,
        is_active: false,
        withdrawn_at: '2026-10-24T12:00:00Z',
      });

      const last = text(items(element).at(-1) as Element);
      expect(last).toContain('Dado de baja');
      expect(last).toContain('Motivo: Ya no deseo continuar.');
      expect(last).toContain('todo su historial se conserva');
      expect(text(element.querySelector('.history-subject') as HTMLElement)).toContain(
        'Dado de baja',
      );
      // Las versiones siguen disponibles tras la baja.
      expect(versionCards(element).length).toBe(2);
    });
  });

  describe('descarga del PDF exacto', () => {
    let create: ReturnType<typeof vi.fn>;
    let clicked: HTMLAnchorElement[];
    let click: ReturnType<typeof vi.spyOn>;

    beforeEach(() => {
      clicked = [];
      create = vi.fn(() => 'blob:gpc-test');
      Object.assign(URL, { createObjectURL: create, revokeObjectURL: vi.fn() });
      click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (
        this: HTMLAnchorElement,
      ) {
        clicked.push(this);
      });
    });

    afterEach(() => click.mockRestore());

    const downloadButton = (element: HTMLElement, index: number) =>
      versionCards(element)[index].querySelector('button') as HTMLButtonElement;

    it('pide el archivo como Blob y lo entrega con el nombre del servidor', async () => {
      const { element, settle } = await open();

      downloadButton(element, 0).click();
      await settle();
      const request = http.expectOne('/api/manuscripts/m-1/versions/v-1/file/');
      expect(request.request.responseType).toBe('blob');
      request.flush(new Blob(['%PDF-1.7'], { type: 'application/pdf' }), {
        headers: { 'Content-Disposition': 'attachment; filename="GPC-2026-000001-v1.pdf"' },
      });
      await settle();

      expect(create).toHaveBeenCalledTimes(1);
      expect(clicked[0].download).toBe('GPC-2026-000001-v1.pdf');
    });

    it('si el servidor no indica nombre usa código y número de versión', async () => {
      const { element, settle } = await open();

      downloadButton(element, 1).click();
      await settle();
      http.expectOne('/api/manuscripts/m-1/versions/v-2/file/').flush(new Blob(['%PDF-1.7']));
      await settle();

      expect(clicked[0].download).toBe('GPC-2026-000001-v2.pdf');
    });

    it('mientras descarga bloquea el botón y no permite otra descarga simultánea', async () => {
      const { element, settle } = await open();

      downloadButton(element, 0).click();
      await settle();

      expect(text(downloadButton(element, 0))).toBe('Descargando…');
      expect(downloadButton(element, 0).disabled).toBe(true);
      downloadButton(element, 1).click();
      await settle();
      http.expectNone('/api/manuscripts/m-1/versions/v-2/file/');

      http.expectOne('/api/manuscripts/m-1/versions/v-1/file/').flush(new Blob(['x']));
      await settle();
      expect(downloadButton(element, 0).disabled).toBe(false);
    });

    it('un fallo de la descarga se explica y deja volver a intentar', async () => {
      const { element, settle } = await open();

      downloadButton(element, 0).click();
      await settle();
      http
        .expectOne('/api/manuscripts/m-1/versions/v-1/file/')
        .flush(new Blob([JSON.stringify(errorEnvelope('AUDIT_UNAVAILABLE', 'Sin auditoría.'))]), {
          status: 503,
          statusText: 'Service Unavailable',
        });
      await vi.waitFor(async () => {
        await settle();
        expect(element.querySelector('.history-error')).not.toBeNull();
      });

      expect(element.querySelector('.history-error')?.textContent).toContain(
        'Servicio no disponible',
      );
      expect(clicked).toEqual([]);
      expect(downloadButton(element, 0).disabled).toBe(false);
    });
  });

  describe('estados de carga y error', () => {
    it('muestra la carga hasta recibir las respuestas', async () => {
      const harness = await RouterTestingHarness.create();
      await harness.navigateByUrl('/app/author/manuscripts/m-1/history', VersionHistoryComponent);
      const element = harness.routeNativeElement as HTMLElement;

      expect(element.querySelector('app-loading-spinner')).not.toBeNull();

      http.expectOne('/api/manuscripts/m-1/').flush(buildManuscript());
      historyRequest().flush(page([]));
      await harness.fixture.whenStable();
      harness.detectChanges();
      expect(element.querySelector('app-loading-spinner')).toBeNull();
    });

    it('sin eventos lo indica', async () => {
      const { element } = await open([]);

      expect(text(element)).toContain('Aún no hay eventos registrados.');
      expect(element.querySelector('ol')).toBeNull();
    });

    it('un manuscrito ajeno responde 404 sin revelar nada y permite reintentar', async () => {
      const harness = await RouterTestingHarness.create();
      await harness.navigateByUrl('/app/author/manuscripts/m-1/history', VersionHistoryComponent);
      const element = harness.routeNativeElement as HTMLElement;
      const settle = async () => {
        await harness.fixture.whenStable();
        harness.detectChanges();
      };

      http.expectOne('/api/manuscripts/m-1/').flush(errorEnvelope('NOT_FOUND', 'No encontrado.'), {
        status: 404,
        statusText: 'Not Found',
      });
      http.match((r) => r.url === '/api/manuscripts/m-1/history/'); // cancelada por el error
      await settle();

      expect(element.querySelector('app-error-state')?.textContent).toContain(
        'no existe o no está disponible',
      );
      expect(element.querySelector('ol')).toBeNull();

      (element.querySelector('app-error-state button') as HTMLButtonElement).click();
      await settle();
      http.expectOne('/api/manuscripts/m-1/').flush(buildManuscript());
      historyRequest().flush(page(HISTORY));
      await settle();

      expect(element.querySelector('app-error-state')).toBeNull();
      expect(items(element).length).toBe(6);
    });
  });

  describe('historiales largos', () => {
    it('ofrece «Mostrar más eventos» y agrega la página siguiente', async () => {
      const { element, settle } = await open(
        HISTORY.slice(0, 2),
        undefined,
        '/api/manuscripts/m-1/history/?page=2',
      );
      expect(items(element).length).toBe(2);

      const more = Array.from(element.querySelectorAll('button')).find(
        (b) => b.textContent?.trim() === 'Mostrar más eventos',
      ) as HTMLButtonElement;
      more.click();
      await settle();
      const request = http.expectOne((r) => r.url === '/api/manuscripts/m-1/history/');
      expect(request.request.params.get('page')).toBe('2');
      request.flush(page(HISTORY.slice(2, 4)));
      await settle();

      expect(items(element).length).toBe(4);
      expect(
        Array.from(element.querySelectorAll('button')).some((b) =>
          b.textContent?.includes('Mostrar más'),
        ),
      ).toBe(false);
    });

    it('con todo el historial cargado no ofrece más eventos', async () => {
      const { element } = await open();

      expect(
        Array.from(element.querySelectorAll('button')).some((b) =>
          b.textContent?.includes('Mostrar más'),
        ),
      ).toBe(false);
    });
  });

  it('enlaza de vuelta con el manuscrito', async () => {
    const { element } = await open();

    const back = element.querySelector('nav a') as HTMLAnchorElement;
    expect(back.getAttribute('href')).toBe('/app/author/manuscripts/m-1');
  });
});
