import { DatePipe } from '@angular/common';
import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { BehaviorSubject, catchError, map, of, switchMap, tap } from 'rxjs';

import { ApiError, toApiError } from '../../../core/models/api-error.model';
import { CatalogArticle, languageLabel } from '../../../core/models/catalog.model';
import { CatalogService } from '../../../core/services/catalog.service';
import { ErrorStateComponent } from '../../../shared/components/error-state.component';
import { LoadingSpinnerComponent } from '../../../shared/components/loading-spinner.component';
import { PdfViewerComponent } from '../../../shared/components/pdf-viewer.component';
import { PublicHeaderComponent } from '../../../shared/components/public-header.component';

/** Fechas se muestran en la zona institucional (UTC-5, sin horario de verano). */
const INSTITUTIONAL_OFFSET = '-0500';

const ARTICLE_UNAVAILABLE =
  'Este artículo no está disponible en el catálogo: no existe, no fue aceptado o fue dado de baja.';
const DOCUMENT_UNAVAILABLE = 'Documento no disponible.';

/**
 * Ficha pública de un artículo aceptado (plan sección 3.5, HU-19).
 *
 * * Muestra autores con su filiación, resumen, palabras clave, área, idioma,
 *   fecha y versión: la lista blanca pública. No hay evaluaciones,
 *   revisores, historial ni auditoría, ni se pide nada de eso.
 * * No envía credenciales. Un artículo que no es público responde `404` (o
 *   `410` si fue retirado) y se muestra un estado controlado, no un error
 *   de red.
 * * El PDF se pide solo al solicitarlo y se muestra en el visor; si ya no
 *   está disponible (`404`/`410`) se dice «Documento no disponible».
 */
@Component({
  selector: 'app-catalog-detail',
  imports: [
    DatePipe,
    RouterLink,
    PublicHeaderComponent,
    LoadingSpinnerComponent,
    ErrorStateComponent,
    PdfViewerComponent,
  ],
  template: `
    <app-public-header />
    <main class="detail">
      <p class="detail__back"><a routerLink="/catalog">← Volver al catálogo</a></p>

      @switch (viewState()) {
        @case ('loading') {
          <app-loading-spinner label="Cargando el artículo…" />
        }
        @case ('unavailable') {
          <div class="unavailable" role="status">
            <h1>Artículo no disponible</h1>
            <p>{{ unavailableMessage }}</p>
            <a class="btn btn--primary" routerLink="/catalog">Ver el catálogo</a>
          </div>
        }
        @case ('error') {
          <app-error-state [message]="error()?.userMessage ?? ''" (retry)="reload()" />
        }
        @default {
          @if (article(); as item) {
            <article aria-labelledby="article-title">
              <header>
                <h1 id="article-title">{{ item.title }}</h1>
                <p class="detail__meta">
                  {{ item.code }} · {{ item.area }} · {{ language(item) }} · Versión
                  {{ item.version_number }} · Publicado el
                  {{ item.published_at | date: 'dd/MM/yyyy' : offset }}
                </p>
              </header>

              <section aria-labelledby="authors-title">
                <h2 id="authors-title">Autores</h2>
                <ul class="authors">
                  @for (author of item.authors; track $index) {
                    <li>
                      <strong>{{ author.full_name }}</strong>&ngsp;<span class="authors__affiliation">{{ author.affiliation }}</span>
                    </li>
                  }
                </ul>
              </section>

              <section aria-labelledby="abstract-title">
                <h2 id="abstract-title">Resumen</h2>
                <p class="detail__abstract">{{ item.abstract }}</p>
              </section>

              @if (item.keywords.length > 0) {
                <section aria-labelledby="keywords-title">
                  <h2 id="keywords-title">Palabras clave</h2>
                  <ul class="keywords">
                    @for (keyword of item.keywords; track keyword) {
                      <li>
                        <a [routerLink]="['/catalog']" [queryParams]="{ keyword: keyword }">{{
                          keyword
                        }}</a>
                      </li>
                    }
                  </ul>
                </section>
              }

              <section aria-labelledby="document-title">
                <h2 id="document-title">Documento</h2>
                @switch (documentState()) {
                  @case ('ready') {
                    <app-pdf-viewer
                      [blob]="document()"
                      [filename]="item.code + '.pdf'"
                      [frameTitle]="'Documento ' + item.code"
                    />
                  }
                  @case ('unavailable') {
                    <p class="callout callout--error" role="alert">{{ documentUnavailable }}</p>
                  }
                  @case ('error') {
                    <p class="callout callout--error" role="alert">{{ documentError() }}</p>
                    <button type="button" class="btn btn--primary" (click)="loadDocument(item.code)">
                      Reintentar
                    </button>
                  }
                  @default {
                    <button
                      type="button"
                      class="btn btn--primary"
                      [disabled]="documentState() === 'loading'"
                      (click)="loadDocument(item.code)"
                    >
                      {{ documentState() === 'loading' ? 'Cargando documento…' : 'Ver el documento (PDF)' }}
                    </button>
                  }
                }
              </section>
            </article>
          }
        }
      }
    </main>
  `,
  styles: `
    .detail {
      max-width: 52rem;
      margin: 0 auto;
      padding: 1rem 1.5rem 2rem;
    }
    .detail__meta {
      margin: 0;
      color: var(--gpc-text-muted);
    }
    .detail h1 {
      overflow-wrap: anywhere;
    }
    .detail__abstract {
      white-space: pre-line;
      overflow-wrap: anywhere;
    }
    .authors {
      margin: 0;
      padding: 0;
      list-style: none;
      display: grid;
      gap: 0.375rem;
    }
    .authors__affiliation {
      display: block;
      color: var(--gpc-text-muted);
      font-size: 0.9375rem;
    }
    .keywords {
      display: flex;
      flex-wrap: wrap;
      gap: 0.375rem;
      margin: 0;
      padding: 0;
      list-style: none;
    }
    .keywords li {
      padding: 0.125rem 0.625rem;
      background: var(--gpc-primary-50);
      border: 1px solid var(--gpc-primary-100);
      border-radius: 999px;
    }
    .unavailable {
      padding: 2rem 1rem;
      text-align: center;
      background: var(--gpc-surface-alt);
      border: 1px dashed var(--gpc-border);
      border-radius: var(--gpc-radius);
    }
    .callout {
      margin: 0 0 0.75rem;
      padding: 0.75rem 1rem;
      border: 1px solid;
      border-radius: var(--gpc-radius);
    }
    .callout--error {
      background: var(--gpc-danger-100);
      border-color: var(--gpc-danger-700);
      color: var(--gpc-danger-700);
    }
  `,
})
export class CatalogDetailComponent {
  private readonly service = inject(CatalogService);
  private readonly route = inject(ActivatedRoute);
  private readonly destroyRef = inject(DestroyRef);

  protected readonly offset = INSTITUTIONAL_OFFSET;
  protected readonly unavailableMessage = ARTICLE_UNAVAILABLE;
  protected readonly documentUnavailable = DOCUMENT_UNAVAILABLE;

  protected readonly viewState = signal<'loading' | 'ready' | 'unavailable' | 'error'>('loading');
  protected readonly article = signal<CatalogArticle | null>(null);
  protected readonly error = signal<ApiError | null>(null);

  protected readonly documentState = signal<'idle' | 'loading' | 'ready' | 'unavailable' | 'error'>(
    'idle',
  );
  protected readonly document = signal<Blob | null>(null);
  protected readonly documentError = signal('');

  private readonly retry$ = new BehaviorSubject<void>(undefined);

  constructor() {
    this.route.paramMap
      .pipe(
        map((params) => params.get('code') ?? ''),
        switchMap((code) =>
          this.retry$.pipe(
            tap(() => {
              this.viewState.set('loading');
              this.documentState.set('idle');
              this.document.set(null);
            }),
            switchMap(() =>
              this.service.get(code).pipe(
                map((article) => ({ article, error: null as ApiError | null })),
                catchError((error: unknown) => of({ article: null, error: toApiError(error) })),
              ),
            ),
          ),
        ),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe(({ article, error }) => {
        this.article.set(article);
        this.error.set(error);
        if (article) {
          this.viewState.set('ready');
        } else if (error?.status === 404 || error?.status === 410) {
          this.viewState.set('unavailable');
        } else {
          this.viewState.set('error');
        }
      });
  }

  protected language(article: CatalogArticle): string {
    return languageLabel(article.language);
  }

  protected reload(): void {
    this.retry$.next();
  }

  /** Pide el PDF público (sin credenciales) y lo muestra en el visor. */
  protected loadDocument(code: string): void {
    if (this.documentState() === 'loading') {
      return;
    }
    this.documentState.set('loading');
    this.service.document(code).subscribe({
      next: (blob) => {
        this.document.set(blob);
        this.documentState.set('ready');
      },
      error: (error: ApiError) => {
        if (error.status === 404 || error.status === 410) {
          this.documentState.set('unavailable');
          return;
        }
        this.documentError.set(error.userMessage);
        this.documentState.set('error');
      },
    });
  }
}
