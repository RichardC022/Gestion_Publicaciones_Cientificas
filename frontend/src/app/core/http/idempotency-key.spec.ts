import { newIdempotencyKey } from './idempotency-key';

/** Formato que acepta el backend: letras, números y `. _ : -`, hasta 100 caracteres. */
const BACKEND_FORMAT = /^[A-Za-z0-9._:-]{1,100}$/;

describe('newIdempotencyKey', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('genera una clave con el formato que acepta el backend', () => {
    expect(newIdempotencyKey()).toMatch(BACKEND_FORMAT);
  });

  it('cada llamada devuelve una clave distinta', () => {
    const keys = new Set(Array.from({ length: 200 }, () => newIdempotencyKey()));

    expect(keys.size).toBe(200);
  });

  it('usa un UUID cuando el navegador lo ofrece', () => {
    vi.stubGlobal('crypto', { randomUUID: () => '0b8f2c1e-6d0a-4b8e-9a52-1f7c3d2e4a10' });

    expect(newIdempotencyKey()).toBe('0b8f2c1e-6d0a-4b8e-9a52-1f7c3d2e4a10');
  });

  it('sin crypto.randomUUID genera una clave alternativa igualmente válida y única', () => {
    vi.stubGlobal('crypto', {});

    const first = newIdempotencyKey();
    const second = newIdempotencyKey();

    expect(first).toMatch(BACKEND_FORMAT);
    expect(first.length).toBeLessThanOrEqual(100);
    expect(first).not.toBe(second);
  });

  it('sin objeto crypto tampoco falla', () => {
    vi.stubGlobal('crypto', undefined);

    expect(newIdempotencyKey()).toMatch(BACKEND_FORMAT);
  });
});
