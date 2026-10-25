import { TestBed } from '@angular/core/testing';

import { STATUS_LABELS, StatusBadgeComponent } from './status-badge.component';

describe('StatusBadgeComponent', () => {
  const render = async (status: string) => {
    const fixture = TestBed.createComponent(StatusBadgeComponent);
    fixture.componentRef.setInput('status', status);
    await fixture.whenStable();
    return fixture;
  };

  const badgeOf = async (status: string) => {
    const fixture = await render(status);
    return (fixture.nativeElement as HTMLElement).querySelector<HTMLElement>('.badge');
  };

  it('mapea los estados editoriales a etiquetas en español', () => {
    expect(STATUS_LABELS['DRAFT']).toBe('Borrador');
    expect(STATUS_LABELS['UNDER_REVIEW']).toBe('En revisión');
    expect(STATUS_LABELS['REQUIRES_CORRECTIONS']).toBe('Requiere correcciones');
    expect(STATUS_LABELS['ACCEPTED']).toBe('Aceptado');
    expect(STATUS_LABELS['REJECTED']).toBe('Rechazado');
  });

  it('usa el tono semántico verde solo para estados de éxito', async () => {
    const badge = await badgeOf('ACCEPTED');
    expect(badge?.className).toContain('badge--success');
    expect(badge?.textContent?.trim()).toBe('Aceptado');
  });

  it('usa el tono rojo para estados destructivos y fallidos', async () => {
    const badge = await badgeOf('REJECTED');
    expect(badge?.className).toContain('badge--danger');
  });

  it('usa el tono amarillo para advertencias', async () => {
    const badge = await badgeOf('REQUIRES_CORRECTIONS');
    expect(badge?.className).toContain('badge--warning');
  });

  it('deja caer al código original en estados desconocidos', async () => {
    const badge = await badgeOf('SOMETHING_ELSE');
    expect(badge?.textContent?.trim()).toBe('SOMETHING_ELSE');
  });
});
