import { TestBed } from '@angular/core/testing';

import { ErrorStateComponent } from './error-state.component';

describe('ErrorStateComponent', () => {
  const render = async (retryLabel: string | null) => {
    const fixture = TestBed.createComponent(ErrorStateComponent);
    fixture.componentRef.setInput('message', 'No se pudo cargar la sección.');
    fixture.componentRef.setInput('retryLabel', retryLabel);
    await fixture.whenStable();
    return fixture;
  };

  it('se anuncia como alerta accesible', async () => {
    const fixture = await render('Reintentar');
    const element = fixture.nativeElement as HTMLElement;
    expect(element.querySelector('[role="alert"]')).not.toBeNull();
    expect(element.textContent).toContain('No se pudo cargar la sección.');
  });

  it('ofrece Reintentar por defecto y emite el evento', async () => {
    const fixture = await render('Reintentar');
    let retried = false;
    fixture.componentInstance.retry.subscribe(() => {
      retried = true;
    });

    const button = (fixture.nativeElement as HTMLElement).querySelector<
      HTMLButtonElement
    >('button');
    expect(button?.textContent?.trim()).toBe('Reintentar');
    button?.click();
    await fixture.whenStable();

    expect(retried).toBe(true);
  });

  it('omite el botón cuando la etiqueta de reintento es nula', async () => {
    const fixture = await render(null);
    expect((fixture.nativeElement as HTMLElement).querySelector('button')).toBeNull();
  });
});
