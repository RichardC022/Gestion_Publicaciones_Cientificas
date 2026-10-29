import { convertToParamMap } from '@angular/router';

import { hasCatalogFilters, languageLabel, toCatalogFilters } from './catalog.model';

const params = (values: Record<string, string>) => convertToParamMap(values);

describe('toCatalogFilters', () => {
  it('sin parámetros no hay filtros', () => {
    expect(toCatalogFilters(params({}))).toEqual({});
  });

  it('toma los filtros válidos de la URL', () => {
    expect(
      toCatalogFilters(
        params({
          search: '  glaciares ',
          area: 'Agronomía',
          keyword: 'clima',
          language: 'es',
          date_from: '2026-01-01',
          date_to: '2026-12-31',
          ordering: 'title',
        }),
      ),
    ).toEqual({
      search: 'glaciares',
      area: 'Agronomía',
      keyword: 'clima',
      language: 'es',
      date_from: '2026-01-01',
      date_to: '2026-12-31',
      ordering: 'title',
    });
  });

  it('descarta los valores que el backend rechazaría con 400', () => {
    expect(
      toCatalogFilters(
        params({
          language: 'espanol',
          date_from: 'ayer',
          date_to: '2026-13-45x',
          ordering: 'code',
          search: 'x'.repeat(201),
        }),
      ),
    ).toEqual({});
  });

  it('descarta «Hasta» cuando es anterior a «Desde»', () => {
    expect(toCatalogFilters(params({ date_from: '2026-05-02', date_to: '2026-05-01' }))).toEqual({
      date_from: '2026-05-02',
    });
  });

  it('el orden por defecto no viaja', () => {
    expect(toCatalogFilters(params({ ordering: '-published_at' }))).toEqual({});
  });

  it('ignora los espacios en blanco', () => {
    expect(toCatalogFilters(params({ search: '   ' }))).toEqual({});
  });
});

describe('hasCatalogFilters', () => {
  it('el orden no cuenta como filtro', () => {
    expect(hasCatalogFilters({ ordering: 'title' })).toBe(false);
    expect(hasCatalogFilters({})).toBe(false);
  });

  it('cualquier otro campo sí', () => {
    expect(hasCatalogFilters({ search: 'x' })).toBe(true);
    expect(hasCatalogFilters({ date_to: '2026-01-01' })).toBe(true);
  });
});

describe('languageLabel', () => {
  it('traduce los códigos conocidos y muestra el resto en mayúsculas', () => {
    expect(languageLabel('es')).toBe('Español');
    expect(languageLabel('de')).toBe('DE');
  });
});
