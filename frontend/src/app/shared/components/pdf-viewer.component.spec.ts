import { TestBed } from '@angular/core/testing';
import { vi } from 'vitest';

import { PdfViewerComponent } from './pdf-viewer.component';

describe('PdfViewerComponent', () => {
  beforeEach(() => {
    Object.defineProperty(URL, 'createObjectURL', {
      configurable: true,
      writable: true,
      value: vi.fn(() => `blob:mock-${crypto.randomUUID()}`),
    });
    Object.defineProperty(URL, 'revokeObjectURL', {
      configurable: true,
      writable: true,
      value: vi.fn(),
    });
  });

  const render = async (blob: Blob | null) => {
    const fixture = TestBed.createComponent(PdfViewerComponent);
    fixture.componentRef.setInput('blob', blob);
    fixture.componentRef.setInput('filename', 'documento.pdf');
    await fixture.whenStable();
    return fixture;
  };

  it('renderiza el iframe sandbox cuando hay documento', async () => {
    const fixture = await render(new Blob(['%PDF-1.7'], { type: 'application/pdf' }));
    const iframe = (fixture.nativeElement as HTMLElement).querySelector('iframe');
    expect(iframe).not.toBeNull();
    expect(iframe?.getAttribute('src')).toContain('blob:mock');
    expect(iframe?.getAttribute('sandbox')).toBe('allow-same-origin');
  });

  it('muestra el mensaje de vacío cuando no hay documento', async () => {
    const fixture = await render(null);
    const element = fixture.nativeElement as HTMLElement;
    expect(element.querySelector('iframe')).toBeNull();
    expect(element.textContent).toContain('No hay documento disponible.');
  });

  it('revoca la URL anterior al cambiar de documento', async () => {
    const fixture = await render(new Blob(['%PDF-1.7'], { type: 'application/pdf' }));
    const firstUrl = (fixture.nativeElement as HTMLElement)
      .querySelector('iframe')
      ?.getAttribute('src') as string;

    fixture.componentRef.setInput(
      'blob',
      new Blob(['%PDF-1.7'], { type: 'application/pdf' }),
    );
    await fixture.whenStable();

    expect(URL.revokeObjectURL).toHaveBeenCalledWith(firstUrl);
  });

  it('abre el documento en pestaña nueva con noopener', async () => {
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null);
    const fixture = await render(new Blob(['%PDF-1.7'], { type: 'application/pdf' }));
    const url = (fixture.nativeElement as HTMLElement)
      .querySelector('iframe')
      ?.getAttribute('src') as string;

    const buttons = Array.from(
      (fixture.nativeElement as HTMLElement).querySelectorAll<HTMLButtonElement>('button'),
    );
    const openButton = buttons.find((button) =>
      button.textContent?.includes('Abrir en pestaña nueva'),
    );
    openButton?.click();

    expect(openSpy).toHaveBeenCalledWith(url, '_blank', 'noopener');
  });
});
