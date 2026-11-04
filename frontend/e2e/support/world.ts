import { Api, evaluate, judge, Scenario, startReview, submitManuscript } from './api';
import { RUN, Who } from './env';

/** Datos con los que las pruebas de accesibilidad, teclado y responsive recorren cada pantalla. */
export interface World {
  submitted: Scenario; // recién enviado
  pending: Scenario; // en revisión, con asignación activa
  accepted: Scenario; // aceptado y publicado
  draftId: string; // borrador editable
  assignmentId: string; // asignación activa del Revisor sobre `pending`
  auditEventId: string; // un evento de auditoría cualquiera
}

export async function buildWorld(tag: string): Promise<World> {
  const [author, editor, reviewer] = await Promise.all([
    Api.login('author'),
    Api.login('editor'),
    Api.login('reviewer'),
  ]);
  const submitted = await submitManuscript(author, `${tag} enviado ${RUN}`);
  const pending = await submitManuscript(author, `${tag} en revisión ${RUN}`);
  await startReview(editor, pending.id, reviewer.userId);
  const accepted = await submitManuscript(author, `${tag} aceptado ${RUN}`);
  await startReview(editor, accepted.id, reviewer.userId);
  await evaluate(reviewer, accepted.id);
  await judge(editor, accepted.id, { decision: 'ACCEPTED' });
  const assignments = await (await reviewer.get('reviewer/assignments/')).json();
  const assignmentId = assignments.results.find(
    (r: { manuscript_code: string }) => r.manuscript_code === pending.code,
  ).id;
  const draft = await author.post('manuscripts/', {
    title: `${tag} borrador ${RUN}`,
    abstract: 'Resumen del borrador.',
    keywords: ['accesibilidad'],
    area: 'Agronomía',
    language: 'es',
    authors: [
      {
        full_name: 'Marcela Quizhpe Ordóñez',
        email: 'e2e-autor@e2e.unl.edu.ec',
        affiliation: 'UNL',
        is_corresponding: true,
      },
    ],
  });
  const draftId = (await draft.json()).id;
  const admin = await Api.login('admin');
  const audit = await (await admin.get('admin/audit/?page_size=1')).json();
  const auditEventId = audit.results[0].id;
  await Promise.all([author.dispose(), editor.dispose(), reviewer.dispose(), admin.dispose()]);
  return { submitted, pending, accepted, draftId, assignmentId, auditEventId };
}

export type Screen = { role: Who | null; name: string; path: string };

/** Todas las pantallas navegables por ruta directa, por rol (`null` = público). */
export function screens(w: World): Screen[] {
  return [
    { role: null, name: 'inicio de sesión', path: '/login' },
    { role: null, name: 'catálogo', path: '/catalog' },
    { role: null, name: 'ficha del catálogo', path: `/catalog/${w.accepted.code}` },
    { role: 'author', name: 'panel', path: '/app/dashboard' },
    { role: 'author', name: 'mis manuscritos', path: '/app/author/manuscripts' },
    { role: 'author', name: 'nuevo manuscrito', path: '/app/author/manuscripts/new' },
    { role: 'author', name: 'detalle enviado', path: `/app/author/manuscripts/${w.submitted.id}` },
    { role: 'author', name: 'detalle borrador', path: `/app/author/manuscripts/${w.draftId}` },
    { role: 'author', name: 'editar borrador', path: `/app/author/manuscripts/${w.draftId}/edit` },
    {
      role: 'author',
      name: 'historial de versiones',
      path: `/app/author/manuscripts/${w.submitted.id}/history`,
    },
    { role: 'author', name: 'avisos', path: '/app/notifications' },
    { role: 'editor', name: 'panel', path: '/app/dashboard' },
    { role: 'editor', name: 'bandeja de envíos', path: '/app/editor/submissions' },
    { role: 'editor', name: 'detalle enviado', path: `/app/editor/submissions/${w.submitted.id}` },
    {
      role: 'editor',
      name: 'detalle en revisión',
      path: `/app/editor/submissions/${w.pending.id}`,
    },
    { role: 'editor', name: 'detalle aceptado', path: `/app/editor/submissions/${w.accepted.id}` },
    { role: 'editor', name: 'asignaciones vencidas', path: '/app/editor/assignments/expired' },
    { role: 'editor', name: 'incidentes', path: '/app/editor/incidents' },
    { role: 'reviewer', name: 'panel', path: '/app/dashboard' },
    { role: 'reviewer', name: 'mis asignaciones', path: '/app/reviewer/assignments' },
    {
      role: 'reviewer',
      name: 'detalle de asignación',
      path: `/app/reviewer/assignments/${w.assignmentId}`,
    },
    {
      role: 'reviewer',
      name: 'formulario de evaluación',
      path: `/app/reviewer/assignments/${w.assignmentId}/evaluate`,
    },
    { role: 'reviewer', name: 'historial de evaluaciones', path: '/app/reviewer/history' },
    { role: 'admin', name: 'panel', path: '/app/dashboard' },
    { role: 'admin', name: 'auditoría', path: '/app/admin/audit' },
    { role: 'admin', name: 'detalle del evento', path: `/app/admin/audit/${w.auditEventId}` },
  ];
}
