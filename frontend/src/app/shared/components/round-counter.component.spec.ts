import { TestBed } from '@angular/core/testing';

import { RoundCounterComponent } from './round-counter.component';

describe('RoundCounterComponent', () => {
  it('muestra la ronda vigente', async () => {
    const fixture = TestBed.createComponent(RoundCounterComponent);
    fixture.componentRef.setInput('round', 2);
    await fixture.whenStable();
    expect(((fixture.nativeElement as HTMLElement).textContent ?? '').trim()).toBe(
      'Ronda 2',
    );
  });
});
