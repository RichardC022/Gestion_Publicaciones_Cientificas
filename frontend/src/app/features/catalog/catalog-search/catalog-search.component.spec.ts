import { Component, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';

import { CatalogFilters } from '../../../core/models/catalog.model';
import { CatalogSearchComponent } from './catalog-search.component';

@Component({
  imports: [CatalogSearchComponent],
  template: `
    <app-catalog-search
      [filters]="filters()"
      (searched)="searched.push($event)"
      (cleared)="cleared = cleared + 1"
    />
  `,
})
class HostComponent {
  readonly filters = signal<CatalogFilters>({});
  readonly searched: CatalogFilters[] = [];
  cleared = 0;
}

describe('CatalogSearchComponent', () => {
  const setup = async (filters: CatalogFilters = {}) => {
    const fixture = TestBed.createComponent(HostComponent);
    fixture.componentInstance.filters.set(filters);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    const element = fixture.nativeElement as HTMLElement;
    const input = (id: string) => element.querySelector<HTMLInputElement>(`#${id}`)!;
    const select = (id: string) => element.querySelector<HTMLSelectElement>(`#${id}`)!;
    const type = (id: string, value: string) => {
      const field = input(id);
      field.value = value;
      field.dispatchEvent(new Event('input'));
    };
    const choose = (id: string, value: string) => {
      const field = select(id);
      field.value = value;
      field.dispatchEvent(new Event('change'));
    };
    const submit = () => {
      element.querySelector('form')!.dispatchEvent(new Event('submit'));
      fixture.detectChanges();
    };
    return { fixture, host: fixture.componentInstance, element, input, select, type, choose, submit };
  };

  it('es un formulario de búsqueda accesible con todos los filtros', async () => {
    const { element } = await setup();

    expect(element.querySelector('form')!.getAttribute('role')).toBe('search');
    for (const id of [
      'catalog-search',
      'catalog-area',
      'catalog-keyword',
      'catalog-language',
      'catalog-from',
      'catalog-to',
      'catalog-ordering',
    ]) {
      expect(element.querySelector(`#${id}`), id).not.toBeNull();
      expect(element.querySelector(`label[for="${id}"]`), `label ${id}`).not.toBeNull();
    }
  });

  it('refleja los filtros vigentes de la URL', async () => {
    const { input, select } = await setup({
      search: 'glaciares',
      area: 'Agronomía',
      language: 'es',
      date_from: '2026-01-01',
      ordering: 'title',
    });

    expect(input('catalog-search').value).toBe('glaciares');
    expect(input('catalog-area').value).toBe('Agronomía');
    expect(select('catalog-language').value).toBe('es');
    expect(input('catalog-from').value).toBe('2026-01-01');
    expect(select('catalog-ordering').value).toBe('title');
  });

  it('actualiza el formulario cuando cambian los filtros vigentes', async () => {
    const { fixture, host, input } = await setup({ search: 'uno' });

    host.filters.set({ search: 'dos' });
    fixture.detectChanges();
    await fixture.whenStable();

    expect(input('catalog-search').value).toBe('dos');
  });

  it('emite solo los filtros con valor, recortados', async () => {
    const { host, type, choose, submit } = await setup();

    type('catalog-search', '  glaciares  ');
    type('catalog-keyword', 'clima');
    choose('catalog-language', 'en');
    submit();

    expect(host.searched).toEqual([{ search: 'glaciares', keyword: 'clima', language: 'en' }]);
  });

  it('sin nada escrito emite un filtro vacío', async () => {
    const { host, submit } = await setup();

    submit();

    expect(host.searched).toEqual([{}]);
  });

  it('el orden por defecto no se emite y otro sí', async () => {
    const { host, choose, submit } = await setup();

    choose('catalog-ordering', 'title');
    submit();

    expect(host.searched).toEqual([{ ordering: 'title' }]);
  });

  it('no emite si «Desde» es posterior a «Hasta» y lo explica', async () => {
    const { host, element, type, submit } = await setup();

    type('catalog-from', '2026-05-02');
    type('catalog-to', '2026-05-01');
    submit();

    expect(host.searched).toEqual([]);
    expect(element.querySelector('.search__error')!.textContent).toContain('no puede ser posterior');
  });

  it('Limpiar avisa al contenedor', async () => {
    const { fixture, host, element } = await setup({ search: 'x' });

    element
      .querySelectorAll<HTMLButtonElement>('.search__actions button')[1]
      .click();
    fixture.detectChanges();

    expect(host.cleared).toBe(1);
  });
});
