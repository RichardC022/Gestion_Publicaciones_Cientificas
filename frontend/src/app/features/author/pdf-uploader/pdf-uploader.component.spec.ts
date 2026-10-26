import { HttpEventType, provideHttpClient } from '@angular/common/http';
import {
  HttpTestingController,
  TestRequest,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';

import { API_BASE_URL } from '../../../core/http/api-base-url.token';
import { DraftFileSummary } from '../../../core/models/manuscript.model';
import { errorEnvelope } from '../testing/manuscript.fixtures';
import { MAX_PDF_BYTES } from './pdf-file.validation';
import { PdfUploaderComponent } from './pdf-uploader.component';

const URL = '/api/manuscripts/m-1/draft-file/';

const CURRENT: DraftFileSummary = {
  filename: 'borrador-anterior.pdf',
  size_bytes: 2_621_440,
  uploaded_at: '2026-10-20T15:30:00Z',
};

const SAVED: DraftFileSummary = {
  filename: 'articulo.pdf',
  size_bytes: 1_048_576,
  uploaded_at: '2026-10-25T12:00:00Z',
};

/** Archivo de prueba; `size` permite simular pesos enormes sin reservar memoria. */
function pdf(name = 'articulo.pdf', options: { type?: string; size?: number } = {}): File {
  const file = new File(['%PDF-1.7 contenido'], name, { type: options.type ?? 'application/pdf' });
  if (options.size !== undefined) {
    Object.defineProperty(file, 'size', { value: options.size });
  }
  return file;
}

describe('PdfUploaderComponent', () => {
  let http: HttpTestingController;
  let fixture: ComponentFixture<PdfUploaderComponent>;
  let element: HTMLElement;
  const emitted: DraftFileSummary[] = [];

  beforeEach(async () => {
    emitted.length = 0;
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

  const render = async (current: DraftFileSummary | null = null) => {
    fixture = TestBed.createComponent(PdfUploaderComponent);
    fixture.componentRef.setInput('manuscriptId', 'm-1');
    fixture.componentRef.setInput('current', current);
    fixture.componentInstance.uploaded.subscribe((draft) => emitted.push(draft));
    element = fixture.nativeElement as HTMLElement;
    await fixture.whenStable();
  };

  const settle = () => fixture.whenStable();
  const text = () => (element.textContent ?? '').replace(/\s+/g, ' ');
  const input = () => element.querySelector('#pdf-file') as HTMLInputElement;
  const button = (label: string) =>
    Array.from(element.querySelectorAll('button')).find((b) => b.textContent?.trim() === label) as
      HTMLButtonElement | undefined;
  const alerts = () =>
    Array.from(element.querySelectorAll('[role="alert"]')).map((e) => e.textContent?.trim());

  const choose = async (file: File) => {
    Object.defineProperty(input(), 'files', { value: [file], configurable: true });
    input().dispatchEvent(new Event('change'));
    await settle();
  };

  /** Elige un archivo válido y pulsa el botón de subir; devuelve la solicitud pendiente. */
  const startUpload = async (file = pdf(), label = 'Subir PDF'): Promise<TestRequest> => {
    await choose(file);
    button(label)?.click();
    await settle();
    return http.expectOne(URL);
  };

  describe('validación previa al envío (solo UX)', () => {
    beforeEach(() => render());

    it.each([
      ['una extensión distinta de .pdf', pdf('articulo.docx'), 'Solo se admiten archivos PDF'],
      [
        'un tipo MIME que no es PDF',
        pdf('articulo.pdf', { type: 'image/png' }),
        'El tipo de archivo no es PDF.',
      ],
      ['un archivo vacío', pdf('articulo.pdf', { size: 0 }), 'El archivo está vacío.'],
      [
        'más de 50 MB',
        pdf('articulo.pdf', { size: MAX_PDF_BYTES + 1 }),
        'supera el límite de 50 MB',
      ],
    ])('rechaza %s sin enviar nada', async (_case, file, message) => {
      await choose(file);

      expect(alerts().join(' ')).toContain(message);
      expect(element.querySelector('.uploader__selected')).toBeNull();
      expect(button('Subir PDF')).toBeUndefined();
      http.expectNone(URL);
    });

    it('acepta exactamente 50 MB', async () => {
      await choose(pdf('limite.pdf', { size: MAX_PDF_BYTES }));

      expect(alerts()).toEqual([]);
      expect(text()).toContain('Archivo elegido: limite.pdf');
      expect(button('Subir PDF')).toBeDefined();
    });

    it('vacía el selector para poder elegir de nuevo el mismo archivo', async () => {
      await choose(pdf('articulo.docx'));

      expect(input().value).toBe('');
      expect(input().getAttribute('aria-invalid')).toBe('true');
    });

    it('un archivo inválido no deja la pantalla bloqueada: se puede elegir otro válido', async () => {
      await choose(pdf('malo.txt'));
      expect(alerts().length).toBe(1);
      expect(input().disabled).toBe(false);

      await choose(pdf('bueno.pdf'));

      expect(alerts()).toEqual([]);
      expect(input().getAttribute('aria-invalid')).toBeNull();
      expect(text()).toContain('Archivo elegido: bueno.pdf');
      expect(button('Subir PDF')?.disabled).toBe(false);
    });

    it('muestra el tamaño legible del archivo elegido', async () => {
      await choose(pdf('articulo.pdf', { size: 3_145_728 }));

      expect(text()).toContain('3 MB');
    });

    it('«Quitar selección» descarta el archivo elegido', async () => {
      await choose(pdf());

      button('Quitar selección')?.click();
      await settle();

      expect(element.querySelector('.uploader__selected')).toBeNull();
    });

    it('cancelar el diálogo del navegador (sin archivo) limpia la selección', async () => {
      await choose(pdf());
      Object.defineProperty(input(), 'files', { value: [], configurable: true });
      input().dispatchEvent(new Event('change'));
      await settle();

      expect(element.querySelector('.uploader__selected')).toBeNull();
    });
  });

  describe('primera carga', () => {
    beforeEach(() => render(null));

    it('invita a adjuntar el PDF cuando todavía no hay ninguno', () => {
      expect(text()).toContain('Aún no hay un PDF adjunto.');
      expect(element.querySelector('label[for="pdf-file"]')?.textContent).toBe('Adjuntar el PDF');
      expect(input().getAttribute('accept')).toBe('.pdf,application/pdf');
    });

    it('envía el archivo a draft-file, informa el resultado y lo notifica al contenedor', async () => {
      const request = await startUpload(pdf('articulo.pdf'));

      expect(request.request.method).toBe('POST');
      expect(((request.request.body as FormData).get('file') as File).name).toBe('articulo.pdf');
      request.flush(SAVED, { status: 201, statusText: 'Created' });
      await settle();

      expect(element.querySelector('.uploader__success')?.textContent).toContain(
        'PDF adjuntado: articulo.pdf.',
      );
      expect(emitted).toEqual([SAVED]);
      expect(element.querySelector('.uploader__selected')).toBeNull();
      expect(input().disabled).toBe(false);
    });

    it('subir el PDF solo llama al endpoint del borrador: no envía ni crea versión', async () => {
      const request = await startUpload();
      request.flush(SAVED, { status: 201, statusText: 'Created' });
      await settle();

      // `verify()` falla si hubiera quedado otra solicitud (submit, versions…) sin atender.
      expect(request.request.url).toBe(URL);
      http.expectNone((r) => /\/(submit|versions)\//.test(r.url));
    });

    it('muestra el progreso de la carga mientras sube', async () => {
      const request = await startUpload();
      const bar = () => element.querySelector('progress') as HTMLProgressElement;
      expect(bar()).not.toBeNull();

      request.event({ type: HttpEventType.UploadProgress, loaded: 40, total: 100 });
      await settle();
      expect(bar().value).toBe(40);
      expect(text()).toContain('40 %');
      expect(bar().getAttribute('aria-label')).toBe('Progreso de la carga del PDF');

      request.event({ type: HttpEventType.UploadProgress, loaded: 100, total: 100 });
      await settle();
      expect(bar().value).toBe(100);

      request.flush(SAVED, { status: 201, statusText: 'Created' });
      await settle();
      expect(element.querySelector('progress')).toBeNull();
    });

    it('sin total conocido muestra «Subiendo…» en lugar de un porcentaje', async () => {
      const request = await startUpload();

      request.event({ type: HttpEventType.UploadProgress, loaded: 40 });
      await settle();

      expect(element.querySelector('.uploader__progress span')?.textContent).toBe('Subiendo…');
      request.flush(SAVED, { status: 201, statusText: 'Created' });
    });

    it('mientras sube deshabilita el selector y no permite una segunda carga', async () => {
      const request = await startUpload();

      expect(input().disabled).toBe(true);
      expect(button('Subiendo…')?.disabled).toBe(true);
      button('Subiendo…')?.click();
      await settle();

      http.expectNone(URL);
      request.flush(SAVED, { status: 201, statusText: 'Created' });
    });
  });

  describe('reemplazo del borrador', () => {
    beforeEach(() => render(CURRENT));

    it('muestra el borrador actual y ofrece reemplazarlo', () => {
      expect(text()).toContain('Borrador actual: borrador-anterior.pdf');
      expect(text()).toContain('2,5 MB');
      expect(text()).toContain('20/10/2026 10:30');
      expect(element.querySelector('label[for="pdf-file"]')?.textContent).toBe('Reemplazar el PDF');
    });

    it('advierte que reemplaza el borrador y que no crea una versión', async () => {
      await choose(pdf('nuevo.pdf'));

      const warning = element.querySelector('.uploader__warning')?.textContent ?? '';
      expect(warning).toContain('Reemplazará el borrador actual (borrador-anterior.pdf)');
      expect(warning).toContain('no envía el manuscrito ni crea una versión');
      expect(button('Reemplazar PDF')).toBeDefined();
    });

    it('al reemplazar informa «PDF reemplazado» y notifica el nuevo borrador', async () => {
      const request = await startUpload(pdf('nuevo.pdf'), 'Reemplazar PDF');

      request.flush({ ...SAVED, filename: 'nuevo.pdf' }, { status: 200, statusText: 'OK' });
      await settle();

      expect(element.querySelector('.uploader__success')?.textContent).toContain(
        'PDF reemplazado: nuevo.pdf.',
      );
      expect(emitted).toEqual([{ ...SAVED, filename: 'nuevo.pdf' }]);
    });

    it('sin archivo elegido no aparece la advertencia de reemplazo', () => {
      expect(element.querySelector('.uploader__warning')).toBeNull();
    });
  });

  describe('rechazos del backend (la barrera real de seguridad)', () => {
    beforeEach(() => render(null));

    it('413: explica el límite de 50 MB y descarta el archivo para elegir otro', async () => {
      const request = await startUpload();

      request.flush(errorEnvelope('PDF_TOO_LARGE', 'El archivo supera el límite de 50 MB.'), {
        status: 413,
        statusText: 'Payload Too Large',
      });
      await settle();

      expect(alerts()).toEqual(['El archivo supera el límite de 50 MB.']);
      expect(element.querySelector('.uploader__selected')).toBeNull();
      expect(input().disabled).toBe(false);
      expect(emitted).toEqual([]);
    });

    it('415: explica que el tipo de contenido no está soportado', async () => {
      const request = await startUpload();

      request.flush(errorEnvelope('PDF_UNSUPPORTED', 'Tipo de contenido no soportado.'), {
        status: 415,
        statusText: 'Unsupported Media Type',
      });
      await settle();

      expect(alerts()).toEqual(['El tipo de contenido enviado no está soportado.']);
      expect(element.querySelector('.uploader__selected')).toBeNull();
    });

    it.each([
      'El PDF está protegido o cifrado.',
      'El archivo está vacío.',
      'El PDF no contiene páginas.',
      'El PDF está dañado o no puede abrirse correctamente.',
      'El PDF contiene contenido activo no permitido.',
    ])('400: muestra el motivo exacto del servidor («%s»)', async (message) => {
      const request = await startUpload();

      request.flush(errorEnvelope('PDF_INVALID', message), {
        status: 400,
        statusText: 'Bad Request',
      });
      await settle();

      expect(alerts()).toEqual([message]);
      expect(element.querySelector('.uploader__selected')).toBeNull();
      expect(emitted).toEqual([]);
    });

    it('un PDF que el cliente dejó pasar pero el servidor rechaza se explica y se puede reintentar con otro', async () => {
      const first = await startUpload(pdf('texto-con-extension-pdf.pdf'));
      first.flush(errorEnvelope('PDF_INVALID', 'El contenido del archivo no es un PDF.'), {
        status: 400,
        statusText: 'Bad Request',
      });
      await settle();

      const second = await startUpload(pdf('bueno.pdf'));
      second.flush(SAVED, { status: 201, statusText: 'Created' });
      await settle();

      expect(alerts()).toEqual([]);
      expect(emitted).toEqual([SAVED]);
    });

    it('409: avisa que el estado cambió y conserva el archivo para reintentar', async () => {
      const request = await startUpload();

      request.flush(errorEnvelope('STATE_CONFLICT', 'No es un borrador.'), {
        status: 409,
        statusText: 'Conflict',
      });
      await settle();

      expect(alerts().join(' ')).toContain('no es válida en el estado actual');
      expect(element.querySelector('.uploader__selected')).not.toBeNull();
      expect(button('Subir PDF')?.disabled).toBe(false);
    });

    it('un error del servidor conserva el archivo y permite reintentar la misma carga', async () => {
      const first = await startUpload(pdf('articulo.pdf'));
      first.flush(errorEnvelope('STORAGE_UNAVAILABLE', 'Sin almacenamiento.'), {
        status: 503,
        statusText: 'Service Unavailable',
      });
      await settle();

      expect(alerts().join(' ')).toContain('Servicio no disponible');
      expect(text()).toContain('Archivo elegido: articulo.pdf');
      expect(element.querySelector('progress')).toBeNull();

      button('Subir PDF')?.click();
      await settle();
      http.expectOne(URL).flush(SAVED, { status: 201, statusText: 'Created' });
      await settle();

      expect(alerts()).toEqual([]);
      expect(emitted).toEqual([SAVED]);
    });

    it('un fallo de red se explica y conserva el archivo', async () => {
      const request = await startUpload();

      request.error(new ProgressEvent('error'));
      await settle();

      expect(alerts().join(' ')).toContain('No fue posible conectar con el servidor');
      expect(text()).toContain('Archivo elegido: articulo.pdf');
    });

    it('tras un error la pantalla vuelve a estar lista', async () => {
      const request = await startUpload();
      request.flush(errorEnvelope('PDF_TOO_LARGE', 'Grande.'), {
        status: 413,
        statusText: 'Payload Too Large',
      });
      await settle();

      expect(input().disabled).toBe(false);
      expect(element.querySelector('progress')).toBeNull();
      await choose(pdf('otro.pdf'));
      expect(alerts()).toEqual([]);
      expect(button('Subir PDF')?.disabled).toBe(false);
    });
  });

  describe('cancelar una carga en curso', () => {
    beforeEach(() => render(null));

    it('aborta la solicitud, avisa y deja elegir de nuevo', async () => {
      const request = await startUpload();

      button('Cancelar carga')?.click();
      await settle();

      expect(request.cancelled).toBe(true);
      expect(alerts().join(' ')).toContain('Carga cancelada');
      expect(emitted).toEqual([]);
      expect(input().disabled).toBe(false);
      expect(element.querySelector('progress')).toBeNull();
      // El archivo sigue elegido: se puede volver a intentar.
      expect(button('Subir PDF')?.disabled).toBe(false);
    });
  });

  describe('privacidad del navegador', () => {
    it('el PDF nunca se guarda en el almacenamiento del navegador', async () => {
      const local = vi.spyOn(Storage.prototype, 'setItem');
      await render(null);

      const request = await startUpload();
      request.event({ type: HttpEventType.UploadProgress, loaded: 10, total: 20 });
      request.flush(SAVED, { status: 201, statusText: 'Created' });
      await settle();

      expect(local).not.toHaveBeenCalled();
      local.mockRestore();
    });
  });

  describe('accesibilidad', () => {
    beforeEach(() => render(null));

    it('el selector tiene etiqueta, pista asociada y los errores se anuncian', async () => {
      expect(element.querySelector('label[for="pdf-file"]')).not.toBeNull();
      expect(input().getAttribute('aria-describedby')).toBe('pdf-file-hint');
      expect(element.querySelector('#pdf-file-hint')?.textContent).toContain('hasta 50 MB');

      await choose(pdf('malo.txt'));
      expect(element.querySelector('p[role="alert"]')).not.toBeNull();
    });

    it('el resultado exitoso se anuncia como estado', async () => {
      const request = await startUpload();
      request.flush(SAVED, { status: 201, statusText: 'Created' });
      await settle();

      expect(element.querySelector('.uploader__success')?.getAttribute('role')).toBe('status');
    });
  });
});
