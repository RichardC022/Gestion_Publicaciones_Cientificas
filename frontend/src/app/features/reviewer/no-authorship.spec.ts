/**
 * Doble ciego en el código fuente (TSK-69): ningún archivo del módulo
 * Revisor —componentes, modelo ni servicio— referencia campos de autoría,
 * contacto, archivo original ni ruta de almacenamiento. Lo que un tipo no
 * declara, la interfaz no puede pintarlo; esta prueba impide que alguien lo
 * declare sin que falle la suite.
 *
 * Los comentarios en español hablan de «autores» con libertad; solo se
 * examina el código y las plantillas, sin comentarios.
 */
const FORBIDDEN = [
  'authors',
  'author',
  'author_order',
  'is_corresponding',
  'corresponding_author',
  'affiliation',
  'created_by',
  'submitted_by',
  'metadata_snapshot',
  'metadata_sha256',
  'original_filename',
  'original_file_path',
  'original_sha256',
  'original_size_bytes',
  'sanitized_file_path',
  'sanitized_sha256',
  'file_url',
  'assigned_by',
  'confidential_comments_for_editor',
];

/** Campos que solo el módulo Editor puede declarar. */
const EDITOR_ONLY = ['justification', 'observations', 'reviewer_id', 'reviewer_name'];

async function sourceFiles(): Promise<{ name: string; code: string }[]> {
  const moduleName: string = 'node:fs';
  const fs = await import(/* @vite-ignore */ moduleName);
  const root: string = (globalThis as unknown as { process: { cwd(): string } }).process.cwd();
  const app = `${root}/src/app`;
  const reviewer = `${app}/features/reviewer`;
  const files: string[] = [
    ...(fs.readdirSync(reviewer, { recursive: true }) as string[])
      .filter((f) => f.endsWith('.ts') && !f.endsWith('.spec.ts') && !f.includes('testing/'))
      .map((f) => `${reviewer}/${f}`),
    `${app}/core/models/reviewer.model.ts`,
    `${app}/core/services/reviewer.service.ts`,
  ];
  return files.map((file) => ({
    name: file.slice(app.length + 1),
    code: stripComments(fs.readFileSync(file, 'utf8') as string),
  }));
}

/** Quita comentarios de bloque y de línea (sin tocar las URL de las plantillas). */
function stripComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:'"`])\/\/.*$/gm, '$1');
}

const word = (field: string) => new RegExp(`\\b${field}\\b`);

describe('Módulo Revisor: sin campos de autoría en el código', () => {
  it('revisa los archivos esperados', async () => {
    const names = (await sourceFiles()).map((f) => f.name);

    for (const expected of [
      'features/reviewer/assignment-list/assignment-list.component.ts',
      'features/reviewer/assignment-detail/assignment-detail.component.ts',
      'features/reviewer/evaluation-form/evaluation-form.component.ts',
      'features/reviewer/evaluation-history/evaluation-history.component.ts',
      'features/reviewer/deadline-countdown/deadline-countdown.component.ts',
      'features/reviewer/conflict-dialog/conflict-dialog.component.ts',
      'features/reviewer/identity-leak-dialog/identity-leak-dialog.component.ts',
      'core/models/reviewer.model.ts',
      'core/services/reviewer.service.ts',
    ]) {
      expect(names).toContain(expected);
    }
  });

  it.each(FORBIDDEN)('ningún archivo del Revisor referencia «%s»', async (field) => {
    const offenders = (await sourceFiles()).filter((f) => word(field).test(f.code));

    expect(offenders.map((f) => f.name)).toEqual([]);
  });

  it.each(EDITOR_ONLY)(
    'ningún archivo del Revisor referencia «%s» (campo del Editor)',
    async (field) => {
      const offenders = (await sourceFiles()).filter((f) => word(field).test(f.code));

      expect(offenders.map((f) => f.name)).toEqual([]);
    },
  );

  it('el comprobador sí detecta una referencia a un campo prohibido', () => {
    const dirty = stripComments(`
      // authors en un comentario no cuenta
      interface Row { id: string; authors: string[] }
    `);

    expect(word('authors').test(dirty)).toBe(true);
    expect(word('authors').test(stripComments('// authors\\n/* authors */'))).toBe(false);
  });
});
