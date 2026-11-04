import { convertToParamMap } from '@angular/router';

import {
  actionLabel,
  detailLabel,
  detailValue,
  hasAuditFilters,
  resultLabel,
  shortHash,
  toAuditFilters,
} from './audit.model';

const UUID = '3f2b1c9e-8a4d-4c1e-9b7a-1d2e3f4a5b6c';

describe('audit.model', () => {
  describe('toAuditFilters', () => {
    it('lee los cinco filtros válidos de la URL', () => {
      const filters = toAuditFilters(
        convertToParamMap({
          date_from: '2026-10-01',
          date_to: '2026-10-31',
          actor: UUID,
          action: 'VERDICT_REGISTERED',
          manuscript: UUID,
          result: 'DENIED',
        }),
      );

      expect(filters).toEqual({
        date_from: '2026-10-01',
        date_to: '2026-10-31',
        actor: UUID,
        action: 'VERDICT_REGISTERED',
        manuscript: UUID,
        result: 'DENIED',
      });
    });

    it('descarta lo que el backend rechazaría con 400', () => {
      const filters = toAuditFilters(
        convertToParamMap({
          date_from: '01/10/2026',
          date_to: 'mañana',
          actor: 'no-es-un-uuid',
          action: 'minusculas',
          manuscript: '123',
          result: 'MAYBE',
        }),
      );

      expect(filters).toEqual({});
      expect(hasAuditFilters(filters)).toBe(false);
    });

    it('descarta «hasta» si es anterior a «desde»', () => {
      const filters = toAuditFilters(
        convertToParamMap({ date_from: '2026-10-31', date_to: '2026-10-01' }),
      );

      expect(filters).toEqual({ date_from: '2026-10-31' });
    });

    it('normaliza ids a minúsculas y recorta espacios', () => {
      const filters = toAuditFilters(convertToParamMap({ actor: ` ${UUID.toUpperCase()} ` }));

      expect(filters.actor).toBe(UUID);
    });

    it('un campo vacío no es un filtro', () => {
      expect(toAuditFilters(convertToParamMap({ actor: '', action: '  ', result: '' }))).toEqual(
        {},
      );
    });
  });

  describe('etiquetas', () => {
    it('traduce acciones y resultados conocidos y conserva los desconocidos', () => {
      expect(actionLabel('VERDICT_CORRECTION_AUTHORIZED')).toBe(
        'Corrección de veredicto autorizada',
      );
      expect(actionLabel('FUTURE_ACTION')).toBe('FUTURE_ACTION');
      expect(resultLabel('DENIED')).toBe('Denegado');
      expect(detailLabel('round_number')).toBe('Ronda');
      expect(detailLabel('otro')).toBe('otro');
    });

    it('formatea los valores de details', () => {
      expect(detailValue(true)).toBe('Sí');
      expect(detailValue(false)).toBe('No');
      expect(detailValue(null)).toBe('—');
      expect(detailValue(3)).toBe('3');
    });

    it('acorta un hash para la tabla', () => {
      expect(shortHash('a'.repeat(64))).toBe('aaaaaaaaaaaa');
      expect(shortHash(null)).toBe('—');
    });
  });
});
