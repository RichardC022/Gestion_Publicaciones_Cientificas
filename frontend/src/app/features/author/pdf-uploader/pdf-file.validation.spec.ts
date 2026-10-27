import { ACCEPTED_PDF_TYPES, MAX_PDF_BYTES, validatePdfFile } from './pdf-file.validation';

const file = (name: string, type = 'application/pdf', size = 1024) => ({ name, type, size });

describe('validatePdfFile', () => {
  it('el límite es de 50 MB', () => {
    expect(MAX_PDF_BYTES).toBe(52_428_800);
  });

  it('acepta un PDF normal', () => {
    expect(validatePdfFile(file('articulo.pdf'))).toBeNull();
  });

  it.each(['ARTICULO.PDF', 'Articulo.Pdf', 'mi artículo (final).pdf', 'a.b.c.pdf'])(
    'acepta la extensión sin distinguir mayúsculas: %s',
    (name) => {
      expect(validatePdfFile(file(name))).toBeNull();
    },
  );

  it.each([
    'articulo.txt',
    'articulo.docx',
    'articulo',
    'pdf',
    'articulo.pdf.exe',
    'articulo.pdf ',
  ])('rechaza la extensión de «%s»', (name) => {
    const result = validatePdfFile(file(name));
    expect(result?.problem).toBe('extension');
    expect(result?.message).toBe('Solo se admiten archivos PDF (extensión .pdf).');
  });

  it.each(ACCEPTED_PDF_TYPES)('acepta el tipo declarado «%s»', (type) => {
    expect(validatePdfFile(file('a.pdf', type))).toBeNull();
  });

  it('acepta el tipo en mayúsculas', () => {
    expect(validatePdfFile(file('a.pdf', 'Application/PDF'))).toBeNull();
  });

  it.each(['image/png', 'text/plain', 'application/zip', 'application/msword'])(
    'rechaza el tipo «%s» aunque la extensión sea .pdf',
    (type) => {
      const result = validatePdfFile(file('a.pdf', type));
      expect(result?.problem).toBe('type');
      expect(result?.message).toBe('El tipo de archivo no es PDF.');
    },
  );

  it('rechaza un archivo vacío', () => {
    const result = validatePdfFile(file('a.pdf', 'application/pdf', 0));
    expect(result?.problem).toBe('empty');
    expect(result?.message).toBe('El archivo está vacío.');
  });

  it('acepta exactamente 50 MB y rechaza 50 MB + 1 byte', () => {
    expect(validatePdfFile(file('a.pdf', 'application/pdf', MAX_PDF_BYTES))).toBeNull();

    const result = validatePdfFile(file('a.pdf', 'application/pdf', MAX_PDF_BYTES + 1));
    expect(result?.problem).toBe('too-large');
    expect(result?.message).toContain('supera el límite de 50 MB');
    expect(result?.message).toContain('50 MB');
  });

  it('indica el peso real del archivo rechazado por tamaño', () => {
    const result = validatePdfFile(file('a.pdf', 'application/pdf', 120 * 1024 * 1024));
    expect(result?.message).toBe('El archivo pesa 120 MB y supera el límite de 50 MB.');
  });

  it('informa primero la extensión, luego el tipo, luego el vacío y por último el tamaño', () => {
    expect(validatePdfFile(file('a.txt', 'image/png', 0))?.problem).toBe('extension');
    expect(validatePdfFile(file('a.pdf', 'image/png', 0))?.problem).toBe('type');
    expect(validatePdfFile(file('a.pdf', 'application/pdf', 0))?.problem).toBe('empty');
  });
});
