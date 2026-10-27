import { TestBed } from '@angular/core/testing';

import { LoadingSpinnerComponent } from './loading-spinner.component';

describe('LoadingSpinnerComponent', () => {
  it('expone el estado accesible con el texto indicado', async () => {
    const fixture = TestBed.createComponent(LoadingSpinnerComponent);
    fixture.componentRef.setInput('label', 'Cargando catálogo…');
    await fixture.whenStable();

    const element = fixture.nativeElement as HTMLElement;
    expect(element.querySelector('[role="status"]')).not.toBeNull();
    expect(element.textContent).toContain('Cargando catálogo…');
  });
});
