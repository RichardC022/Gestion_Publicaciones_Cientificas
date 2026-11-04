import { defineConfig } from '@playwright/test';

/**
 * E2E de los flujos críticos (TSK-91). Corren contra el stack REAL de Docker Compose
 * (Nginx + Django + PostgreSQL), nunca contra `ng serve`: lo levanta
 * `scripts/e2e.sh`, que fija E2E_BASE_URL y las cuentas.
 *
 * Los archivos son `*.e2e.ts` (no `*.spec.ts`) para que `ng test` no los recoja.
 * Un solo trabajador y en orden: los flujos comparten el stack, y cada uno crea sus
 * propios manuscritos con un sufijo único, así que no dependen de datos previos.
 */
export default defineConfig({
  testDir: './e2e',
  testMatch: '**/*.e2e.ts',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 90_000,
  expect: { timeout: 15_000 },
  reporter: [['list']],
  outputDir: './test-results',
  use: {
    baseURL: process.env['E2E_BASE_URL'] ?? 'https://localhost:20443',
    // El stack usa un certificado autofirmado (scripts/make_dev_cert.sh).
    ignoreHTTPSErrors: true,
    locale: 'es-EC',
    timezoneId: 'America/Guayaquil',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
});
