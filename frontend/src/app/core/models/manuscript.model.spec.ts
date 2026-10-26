import {
  EDITABLE_STATUSES,
  MANUSCRIPT_STATUSES,
  ManuscriptStatus,
  isEditable,
  nextAction,
} from './manuscript.model';

describe('manuscript.model', () => {
  describe('isEditable', () => {
    it.each(MANUSCRIPT_STATUSES.map((status) => [status, EDITABLE_STATUSES.includes(status)]))(
      'estado %s activo -> editable: %s',
      (status, expected) => {
        expect(isEditable({ status: status as ManuscriptStatus, is_active: true })).toBe(
          expected as boolean,
        );
      },
    );

    it('solo Borrador y Requiere correcciones son editables', () => {
      expect([...EDITABLE_STATUSES].sort()).toEqual(['DRAFT', 'REQUIRES_CORRECTIONS']);
    });

    it.each(MANUSCRIPT_STATUSES)('un manuscrito dado de baja nunca es editable (%s)', (status) => {
      expect(isEditable({ status, is_active: false })).toBe(false);
    });
  });

  describe('nextAction', () => {
    it.each(MANUSCRIPT_STATUSES)('define una acción breve y una detallada para %s', (status) => {
      const action = nextAction({ status, is_active: true });
      expect(action.short.length).toBeGreaterThan(0);
      expect(action.detail.length).toBeGreaterThan(action.short.length);
    });

    it('pide enviar nueva versión cuando requiere correcciones', () => {
      expect(nextAction({ status: 'REQUIRES_CORRECTIONS', is_active: true }).short).toBe(
        'Enviar nueva versión',
      );
    });

    it('un manuscrito dado de baja está archivado sin importar su estado', () => {
      for (const status of MANUSCRIPT_STATUSES) {
        expect(nextAction({ status, is_active: false }).short).toBe('Archivado');
      }
    });

    it('un aceptado indica que está publicado', () => {
      expect(nextAction({ status: 'ACCEPTED', is_active: true }).short).toBe('Publicado');
    });
  });
});
