import { TestBed } from '@angular/core/testing';

import { EmptyStateComponent } from './empty-state.component';

describe('EmptyStateComponent', () => {
  const render = async (actionLabel: string | null) => {
    const fixture = TestBed.createComponent(EmptyStateComponent);
    fixture.componentRef.setInput('message', 'No hay manuscritos todavía.');
    fixture.componentRef.setInput('actionLabel', actionLabel);
    await fixture.whenStable();
    return fixture;
  };

  it('se anuncia como estado y muestra el mensaje', async () => {
    const fixture = await render(null);
    const element = fixture.nativeElement as HTMLElement;
    expect(element.querySelector('[role="status"]')).not.toBeNull();
    expect(element.textContent).toContain('No hay manuscritos todavía.');
  });

  it('muestra la acción sugerida solo cuando se indica', async () => {
    const withoutAction = await render(null);
    expect((withoutAction.nativeElement as HTMLElement).querySelector('button')).toBeNull();

    const withAction = await render('Crear manuscrito');
    const button = (withAction.nativeElement as HTMLElement).querySelector<
      HTMLButtonElement
    >('button');
    expect(button?.textContent?.trim()).toBe('Crear manuscrito');

    let activated = false;
    withAction.componentInstance.action.subscribe(() => {
      activated = true;
    });
    button?.click();
    await withAction.whenStable();
    expect(activated).toBe(true);
  });
});
