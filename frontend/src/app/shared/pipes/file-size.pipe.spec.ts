import { FileSizePipe } from './file-size.pipe';

describe('FileSizePipe', () => {
  const pipe = new FileSizePipe();

  it('devuelve una cadena vacía para valores ausentes o inválidos', () => {
    expect(pipe.transform(null)).toBe('');
    expect(pipe.transform(undefined)).toBe('');
    expect(pipe.transform(Number.NaN)).toBe('');
    expect(pipe.transform(-1)).toBe('');
  });

  it('formatea bytes sin unidad mayor', () => {
    expect(pipe.transform(500)).toBe('500 B');
  });

  it('formatea kilobytes con coma decimal en español', () => {
    expect(pipe.transform(1536)).toBe('1,5 KB');
  });

  it('formatea el límite de 50 MB de un PDF exacto', () => {
    expect(pipe.transform(50 * 1024 * 1024)).toBe('50 MB');
  });
});
