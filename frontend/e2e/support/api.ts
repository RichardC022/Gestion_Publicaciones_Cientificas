import { APIRequestContext, expect, request } from '@playwright/test';

import { ACCOUNTS, AREA, PASSWORD, Who } from './env';
import { makePdf } from './pdf';

/**
 * Cliente de la API para PREPARAR el escenario de un flujo (llegar al punto en que
 * empieza la parte que se prueba por la pantalla). Lo que se prueba va por la UI.
 */
export class Api {
  constructor(
    private readonly ctx: APIRequestContext,
    private readonly bearer: string,
    readonly userId: string,
  ) {}

  static async login(who: Who): Promise<Api> {
    const ctx = await request.newContext({ ignoreHTTPSErrors: true });
    const base = process.env['E2E_BASE_URL'] ?? 'https://localhost:20443';
    const res = await ctx.post(`${base}/api/auth/login/`, {
      data: { identifier: ACCOUNTS[who].id, password: PASSWORD },
    });
    expect(res.status(), `login de ${who}`).toBe(200);
    const body = await res.json();
    const me = await ctx.get(`${base}/api/auth/me/`, {
      headers: { Authorization: `Bearer ${body.access}` },
    });
    return new Api(ctx, body.access, (await me.json()).user.id);
  }

  private url(path: string): string {
    return `${process.env['E2E_BASE_URL'] ?? 'https://localhost:20443'}/api/${path}`;
  }

  private headers(extra: Record<string, string> = {}): Record<string, string> {
    return { Authorization: `Bearer ${this.bearer}`, ...extra };
  }

  async get(path: string) {
    return this.ctx.get(this.url(path), { headers: this.headers() });
  }

  async post(path: string, data: unknown = {}, headers: Record<string, string> = {}) {
    return this.ctx.post(this.url(path), { data, headers: this.headers(headers) });
  }

  async put(path: string, data: unknown, headers: Record<string, string> = {}) {
    return this.ctx.put(this.url(path), { data, headers: this.headers(headers) });
  }

  async upload(path: string, filename: string, pdf: Buffer) {
    return this.ctx.post(this.url(path), {
      headers: this.headers(),
      multipart: { file: { name: filename, mimeType: 'application/pdf', buffer: pdf } },
    });
  }

  async dispose(): Promise<void> {
    await this.ctx.dispose();
  }
}

export interface Scenario {
  id: string;
  code: string;
  title: string;
}

const key = (): string => `e2e-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;

/** Un manuscrito del Autor, enviado (v1, ronda 0): borrador + PDF + envío. */
export async function submitManuscript(author: Api, title: string): Promise<Scenario> {
  const me = (await (await author.get('auth/me/')).json()).user;
  const created = await author.post('manuscripts/', {
    title,
    abstract: 'Resumen del estudio de campo sobre cultivos de altura.',
    keywords: ['clima', 'cultivos'],
    area: AREA,
    language: 'es',
    authors: [
      {
        full_name: me.full_name ?? ACCOUNTS.author.name,
        email: me.email,
        affiliation: 'Universidad Nacional de Loja',
        is_corresponding: true,
      },
    ],
  });
  expect(created.status(), await created.text()).toBe(201);
  const manuscript = await created.json();
  const uploaded = await author.upload(
    `manuscripts/${manuscript.id}/draft-file/`,
    'articulo.pdf',
    makePdf(`${title}-${key()}`),
  );
  expect(uploaded.status(), await uploaded.text()).toBe(201);
  const sent = await author.post(
    `manuscripts/${manuscript.id}/submit/`,
    {},
    { 'Idempotency-Key': key() },
  );
  expect(sent.status(), await sent.text()).toBe(201);
  const detail = await (await author.get(`manuscripts/${manuscript.id}/`)).json();
  return { id: manuscript.id, code: detail.code, title };
}

/** El Editor pasa el manuscrito a revisión y asigna al Revisor. */
export async function startReview(editor: Api, manuscriptId: string, reviewerId: string) {
  const res = await editor.post(`editor/submissions/${manuscriptId}/start-review/`, {
    reviewer_id: reviewerId,
  });
  expect(res.status(), await res.text()).toBe(200);
}

export const EVALUATION = {
  originality_score: 4,
  methodology_score: 4,
  clarity_score: 5,
  relevance_score: 4,
  ethics_score: 5,
  recommendation: 'ACCEPT',
  comments_for_author: 'Trabajo sólido, con matices menores por resolver.',
  confidential_comments: 'Sin observaciones adicionales para el Editor.',
};

/** El Revisor guarda y envía su evaluación final. */
export async function evaluate(reviewer: Api, manuscriptId: string, overrides = {}) {
  const list = await (await reviewer.get('reviewer/assignments/')).json();
  const row = list.results.find(
    (r: { manuscript_id?: string; manuscript_code: string; id: string }) =>
      r.manuscript_id ? r.manuscript_id === manuscriptId : true,
  );
  const base = `reviewer/assignments/${row.id}/evaluation/`;
  const saved = await reviewer.put(base, { ...EVALUATION, ...overrides }, { 'If-Match': '"0"' });
  expect(saved.status(), await saved.text()).toBe(200);
  const sent = await reviewer.post(`${base}submit/`, {}, { 'If-Match': saved.headers()['etag'] });
  expect(sent.status(), await sent.text()).toBe(200);
}

/** El Editor registra un veredicto sobre la versión evaluada. */
export async function judge(editor: Api, manuscriptId: string, body: Record<string, string>) {
  const detail = await editor.get(`editor/submissions/${manuscriptId}/`);
  const res = await editor.post(`editor/manuscripts/${manuscriptId}/verdicts/`, body, {
    'Idempotency-Key': key(),
    'If-Match': detail.headers()['etag'] ?? '',
  });
  expect(res.status(), await res.text()).toBe(201);
  return res.json();
}
