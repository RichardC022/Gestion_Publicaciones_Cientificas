import { saveBlob } from './save-blob';

describe('saveBlob', () => {
  let create: ReturnType<typeof vi.fn>;
  let revoke: ReturnType<typeof vi.fn>;
  let click: ReturnType<typeof vi.spyOn>;
  let clicked: HTMLAnchorElement[];

  beforeEach(() => {
    clicked = [];
    create = vi.fn(() => 'blob:gpc-test');
    revoke = vi.fn();
    Object.assign(URL, { createObjectURL: create, revokeObjectURL: revoke });
    click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (
      this: HTMLAnchorElement,
    ) {
      clicked.push(this);
    });
  });

  afterEach(() => click.mockRestore());

  it('descarga el contenido con el nombre indicado', () => {
    const blob = new Blob(['%PDF-1.7'], { type: 'application/pdf' });

    saveBlob(blob, 'GPC-2026-000001-v1.pdf');

    expect(create).toHaveBeenCalledWith(blob);
    expect(clicked.length).toBe(1);
    expect(clicked[0].href).toBe('blob:gpc-test');
    expect(clicked[0].download).toBe('GPC-2026-000001-v1.pdf');
  });

  it('revoca la URL de objeto y no deja el enlace en la página', () => {
    saveBlob(new Blob(['x']), 'a.pdf');

    expect(revoke).toHaveBeenCalledWith('blob:gpc-test');
    expect(document.querySelector('a[download]')).toBeNull();
  });

  it('revoca la URL aunque el navegador falle al activar el enlace', () => {
    click.mockImplementation(() => {
      throw new Error('bloqueado');
    });

    expect(() => saveBlob(new Blob(['x']), 'a.pdf')).toThrow('bloqueado');
    expect(revoke).toHaveBeenCalledWith('blob:gpc-test');
  });

  it('no guarda el archivo en el almacenamiento del navegador', () => {
    const setItem = vi.spyOn(Storage.prototype, 'setItem');

    saveBlob(new Blob(['x']), 'a.pdf');

    expect(setItem).not.toHaveBeenCalled();
    setItem.mockRestore();
  });
});
