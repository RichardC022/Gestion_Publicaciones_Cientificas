import { TestBed } from '@angular/core/testing';

import { PaginationComponent } from './pagination.component';

describe('PaginationComponent', () => {
  const render = async (page: number, pageSize: number, totalItems: number) => {
    const fixture = TestBed.createComponent(PaginationComponent);
    fixture.componentRef.setInput('page', page);
    fixture.componentRef.setInput('pageSize', pageSize);
    fixture.componentRef.setInput('totalItems', totalItems);
    await fixture.whenStable();
    return fixture;
  };

  it('se oculta cuando solo hay una página', async () => {
    const fixture = await render(1, 20, 15);
    expect((fixture.nativeElement as HTMLElement).querySelector('nav')).toBeNull();
  });

  it('muestra la página actual y el total de elementos', async () => {
    const fixture = await render(1, 20, 250);
    const element = fixture.nativeElement as HTMLElement;
    expect(element.textContent).toContain('Página 1 de 13');
    expect(element.textContent).toContain('250 elementos');
  });

  it('deshabilita Anterior en la primera página y Siguiente en la última', async () => {
    const first = await render(1, 20, 250);
    const firstButtons = Array.from(
      (first.nativeElement as HTMLElement).querySelectorAll<HTMLButtonElement>('button'),
    );
    expect(firstButtons[0].disabled).toBe(true);
    expect(firstButtons[1].disabled).toBe(false);

    const last = await render(13, 20, 250);
    const lastButtons = Array.from(
      (last.nativeElement as HTMLElement).querySelectorAll<HTMLButtonElement>('button'),
    );
    expect(lastButtons[0].disabled).toBe(false);
    expect(lastButtons[1].disabled).toBe(true);
  });

  it('emite pageChange al pulsar Siguiente', async () => {
    const fixture = await render(2, 20, 250);
    const emitted: number[] = [];
    fixture.componentInstance.pageChange.subscribe((page) => emitted.push(page));

    const buttons = Array.from(
      (fixture.nativeElement as HTMLElement).querySelectorAll<HTMLButtonElement>('button'),
    );
    buttons[1].click();
    await fixture.whenStable();

    expect(emitted).toEqual([3]);
  });
});
