import { FormControl } from '@angular/forms';

import {
  AUTHOR_ROSTER_ERRORS,
  authorRosterValidator,
  rosterMessages,
} from './author-roster.validator';
import { KEYWORD_MAX_LENGTH, parseKeywords } from './keywords';

const row = (email: string, is_corresponding = false) => ({ email, is_corresponding });

describe('authorRosterValidator', () => {
  const validate = (rows: unknown[], registrant: string | null = null) =>
    authorRosterValidator(() => registrant)(new FormControl(rows));

  it('acepta un autor responsable único', () => {
    expect(validate([row('a@x.edu', true)])).toBeNull();
    expect(validate([row('a@x.edu', true), row('b@x.edu')])).toBeNull();
  });

  it('exige al menos un autor', () => {
    expect(validate([])).toEqual({ noAuthors: true });
  });

  it('exige exactamente un responsable: ninguno', () => {
    expect(validate([row('a@x.edu'), row('b@x.edu')])?.['responsible']).toBe('none');
  });

  it('exige exactamente un responsable: más de uno', () => {
    expect(validate([row('a@x.edu', true), row('b@x.edu', true)])?.['responsible']).toBe('many');
  });

  it('rechaza correos repetidos sin distinguir mayúsculas ni espacios', () => {
    const errors = validate([row('A@x.edu', true), row(' a@X.edu ')]);
    expect(errors?.['duplicateEmails']).toBe(true);
  });

  it('exige que el autor que registra figure en la lista', () => {
    expect(validate([row('otro@x.edu', true)], 'yo@x.edu')?.['registrantMissing']).toBe(true);
    expect(validate([row('YO@x.edu', true)], 'yo@x.edu')).toBeNull();
  });

  it('sin sesión (registrante nulo) no aplica la regla del registrante', () => {
    expect(validate([row('otro@x.edu', true)], null)).toBeNull();
  });

  it('acumula varios errores a la vez', () => {
    const errors = validate([row('a@x.edu'), row('a@x.edu')], 'yo@x.edu');
    expect(Object.keys(errors ?? {}).sort()).toEqual([
      'duplicateEmails',
      'registrantMissing',
      'responsible',
    ]);
  });

  describe('rosterMessages', () => {
    it('traduce cada error a su mensaje', () => {
      expect(rosterMessages({ noAuthors: true })).toEqual([AUTHOR_ROSTER_ERRORS.noAuthors]);
      expect(rosterMessages({ responsible: 'none' })).toEqual([
        AUTHOR_ROSTER_ERRORS.responsibleNone,
      ]);
      expect(rosterMessages({ responsible: 'many' })).toEqual([
        AUTHOR_ROSTER_ERRORS.responsibleMany,
      ]);
      expect(rosterMessages({ duplicateEmails: true })).toEqual([
        AUTHOR_ROSTER_ERRORS.duplicateEmails,
      ]);
      expect(rosterMessages({ registrantMissing: true })).toEqual([
        AUTHOR_ROSTER_ERRORS.registrantMissing,
      ]);
    });

    it('sin errores no hay mensajes', () => {
      expect(rosterMessages(null)).toEqual([]);
    });
  });
});

describe('parseKeywords', () => {
  it('separa por coma, punto y coma y salto de línea', () => {
    expect(parseKeywords('clima, cultivos; suelo\nagua')).toEqual([
      'clima',
      'cultivos',
      'suelo',
      'agua',
    ]);
  });

  it('recorta espacios y descarta vacías', () => {
    expect(parseKeywords('  clima ,, ,  suelo  ,')).toEqual(['clima', 'suelo']);
  });

  it('elimina repetidas sin distinguir mayúsculas y conserva la primera escritura', () => {
    expect(parseKeywords('Clima, clima, CLIMA, suelo')).toEqual(['Clima', 'suelo']);
  });

  it('el texto vacío no produce palabras clave', () => {
    expect(parseKeywords('')).toEqual([]);
    expect(parseKeywords(' , ; ')).toEqual([]);
  });

  it('expone el máximo de la API', () => {
    expect(KEYWORD_MAX_LENGTH).toBe(100);
  });
});
