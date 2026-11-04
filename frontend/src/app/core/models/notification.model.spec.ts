import { convertToParamMap } from '@angular/router';

import { internalLink, toNoticeFilter } from './notification.model';

describe('toNoticeFilter', () => {
  it('sin parámetro muestra todos', () => {
    expect(toNoticeFilter(convertToParamMap({}))).toBe('ALL');
  });

  it('?filter=unread muestra los no leídos', () => {
    expect(toNoticeFilter(convertToParamMap({ filter: 'unread' }))).toBe('UNREAD');
  });

  it.each(['UNREAD', 'read', '', 'all', '<script>'])(
    'un valor manipulado (%j) vuelve a todos',
    (value) => {
      expect(toNoticeFilter(convertToParamMap({ filter: value }))).toBe('ALL');
    },
  );
});

describe('internalLink', () => {
  it.each(['/app/editor/submissions/s-1', '/app/reviewer/assignments', '/app/editor/incidents'])(
    '%s es una ruta interna',
    (link) => {
      expect(internalLink(link)).toBe(link);
    },
  );

  it.each([
    'https://sitio-ajeno.example/app/x',
    '//sitio-ajeno.example/app/x',
    'javascript:alert(1)',
    '/app//sitio-ajeno.example',
    '/otra-ruta',
    'app/editor',
    '/app/ con espacio',
    '',
    null,
    undefined,
  ])('%j no se convierte en enlace', (link) => {
    expect(internalLink(link)).toBeNull();
  });
});
