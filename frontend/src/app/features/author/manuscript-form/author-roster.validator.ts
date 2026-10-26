import { AbstractControl, ValidationErrors, ValidatorFn } from '@angular/forms';

/**
 * Reglas de la lista de autores del manuscrito (CA-HU-04-02/03, HU-07):
 *
 * * al menos un autor (`noAuthors`);
 * * exactamente un autor responsable (`responsible`: `none` | `many`);
 * * ningún correo repetido (`duplicateEmails`);
 * * el autor que registra debe figurar en la lista (`registrantMissing`).
 *
 * Son las mismas que aplica el backend; aquí solo evitan un viaje
 * inútil y explican el problema antes de enviar.
 */
export const AUTHOR_ROSTER_ERRORS = {
  noAuthors: 'Debe indicar al menos un autor.',
  responsibleNone: 'Debe designar exactamente un autor responsable.',
  responsibleMany: 'Solo puede haber un autor responsable.',
  duplicateEmails: 'Un mismo correo no puede repetirse entre los autores.',
  registrantMissing: 'El autor que registra el manuscrito debe figurar en la lista de autores.',
} as const;

interface RosterRow {
  email?: string;
  is_corresponding?: boolean;
}

/**
 * `registrantEmail` se evalúa en cada validación (puede cambiar si la
 * sesión se refresca); `null` desactiva la regla del registrante.
 */
export function authorRosterValidator(registrantEmail: () => string | null): ValidatorFn {
  return (control: AbstractControl): ValidationErrors | null => {
    const rows = (control.value ?? []) as RosterRow[];
    const errors: ValidationErrors = {};

    if (rows.length === 0) {
      errors['noAuthors'] = true;
      return errors;
    }

    const responsible = rows.filter((row) => row.is_corresponding).length;
    if (responsible === 0) {
      errors['responsible'] = 'none';
    } else if (responsible > 1) {
      errors['responsible'] = 'many';
    }

    const emails = rows.map((row) => (row.email ?? '').trim().toLowerCase()).filter(Boolean);
    if (new Set(emails).size !== emails.length) {
      errors['duplicateEmails'] = true;
    }

    const registrant = registrantEmail()?.trim().toLowerCase();
    if (registrant && !emails.includes(registrant)) {
      errors['registrantMissing'] = true;
    }

    return Object.keys(errors).length > 0 ? errors : null;
  };
}

/** Mensajes legibles de los errores de la lista de autores. */
export function rosterMessages(errors: ValidationErrors | null): string[] {
  if (!errors) {
    return [];
  }
  const messages: string[] = [];
  if (errors['noAuthors']) {
    messages.push(AUTHOR_ROSTER_ERRORS.noAuthors);
  }
  if (errors['responsible'] === 'none') {
    messages.push(AUTHOR_ROSTER_ERRORS.responsibleNone);
  }
  if (errors['responsible'] === 'many') {
    messages.push(AUTHOR_ROSTER_ERRORS.responsibleMany);
  }
  if (errors['duplicateEmails']) {
    messages.push(AUTHOR_ROSTER_ERRORS.duplicateEmails);
  }
  if (errors['registrantMissing']) {
    messages.push(AUTHOR_ROSTER_ERRORS.registrantMissing);
  }
  return messages;
}
