import { Type } from '@angular/core';
import { TestBed } from '@angular/core/testing';

import { AdminSummaryComponent } from './admin-summary/admin-summary.component';
import { AuthorSummaryComponent } from './author-summary/author-summary.component';
import { EditorSummaryComponent } from './editor-summary/editor-summary.component';
import { ReviewerSummaryComponent } from './reviewer-summary/reviewer-summary.component';

/** Suite directa de los cuatro resúmenes del panel (TSK-28). */

const renderSummary = async (
  component: Type<unknown>,
  data: Record<string, unknown> | null,
) => {
  const fixture = TestBed.createComponent(component);
  fixture.componentRef.setInput('data', data);
  await fixture.whenStable();
  return fixture;
};

const cases = [
  { title: 'AuthorSummaryComponent', component: AuthorSummaryComponent, heading: 'Autor' },
  { title: 'ReviewerSummaryComponent', component: ReviewerSummaryComponent, heading: 'Revisor' },
  { title: 'EditorSummaryComponent', component: EditorSummaryComponent, heading: 'Editor' },
  { title: 'AdminSummaryComponent', component: AdminSummaryComponent, heading: 'Administrador' },
] as const;

describe('Resúmenes del panel unificado (TSK-28)', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({});
  });

  for (const { title, component, heading } of cases) {
    describe(title, () => {
      it(`muestra el encabezado ${heading} y los datos de su sección`, async () => {
        const fixture = await renderSummary(component, { manuscripts: 3, pending: 1 });
        const element = fixture.nativeElement as HTMLElement;

        expect(element.textContent).toContain(heading);
        expect(element.textContent).toContain('manuscripts');
        expect(element.textContent).toContain('3');
        expect(element.textContent).toContain('pending');
        expect(element.textContent).toContain('1');
      });

      it('con sección sin datos muestra el estado vacío', async () => {
        const fixture = await renderSummary(component, null);
        const element = fixture.nativeElement as HTMLElement;

        expect(element.textContent).toContain(heading);
        expect(element.textContent).toContain('Sin datos por ahora.');
      });
    });
  }
});
