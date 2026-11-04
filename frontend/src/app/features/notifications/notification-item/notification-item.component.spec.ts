import { Component, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { Notice } from '../../../core/models/notification.model';
import { buildNotice, buildNoticePayload } from '../testing/notification.fixtures';
import { NotificationItemComponent } from './notification-item.component';

@Component({
  imports: [NotificationItemComponent],
  template: `<app-notification-item
    [notice]="notice()"
    [busy]="busy()"
    (opened)="opened.push($event)"
    (markRead)="marked.push($event)"
  />`,
})
class HostComponent {
  readonly notice = signal<Notice>(buildNotice());
  readonly busy = signal(false);
  readonly opened: Notice[] = [];
  readonly marked: Notice[] = [];
}

describe('NotificationItemComponent', () => {
  beforeEach(() => {
    // El enlace de los avisos de prueba lleva a un detalle de envío.
    TestBed.configureTestingModule({
      providers: [provideRouter([{ path: 'app/editor/submissions/:id', children: [] }])],
    });
  });

  const text = (node: Element | null) => (node?.textContent ?? '').replace(/\s+/g, ' ').trim();

  const setup = (notice: Notice = buildNotice()) => {
    const fixture = TestBed.createComponent(HostComponent);
    fixture.componentInstance.notice.set(notice);
    fixture.detectChanges();
    const element = fixture.nativeElement as HTMLElement;
    const markButton = () =>
      Array.from(element.querySelectorAll('button')).find((b) =>
        text(b).includes('Marcar como leído'),
      );
    const link = () => element.querySelector<HTMLAnchorElement>('a');
    return { fixture, host: fixture.componentInstance, element, markButton, link };
  };

  it('muestra el título, el mensaje, la fecha en la zona institucional y los datos del manuscrito', () => {
    const { element } = setup(
      buildNotice({
        payload: buildNoticePayload({ due_at: '2026-11-26T15:00:00Z' }),
      }),
    );

    const content = text(element);
    expect(content).toContain('Nueva evaluación recibida');
    expect(content).toContain('El Revisor envió su evaluación del manuscrito.');
    // 15:00 UTC en la zona institucional (UTC-5) son las 10:00.
    expect(content).toContain('06/11/2026 10:00');
    expect(content).toContain('GPC-2026-000001');
    expect(content).toContain('Efecto del clima en cultivos andinos');
    expect(content).toContain('Acción: Registrar el veredicto');
    expect(content).toContain('Plazo: 26/11/2026 10:00');
  });

  it('un aviso sin manuscrito, acción ni plazo no muestra la línea de datos', () => {
    const { element } = setup(
      buildNotice({
        payload: buildNoticePayload({
          manuscript_code: null,
          manuscript_title: null,
          action: null,
          due_at: null,
        }),
      }),
    );

    expect(element.querySelector('.notice__meta')).toBeNull();
  });

  it('un no leído se distingue por texto («Nuevo») y por estilo', () => {
    const { element } = setup();

    expect(text(element.querySelector('.badge'))).toBe('Nuevo');
    expect(element.querySelector('.notice--unread')).not.toBeNull();
  });

  it('un leído no muestra «Nuevo» ni ofrece marcarlo', () => {
    const { element, markButton } = setup(
      buildNotice({ is_read: true, read_at: '2026-11-07T15:00:00Z' }),
    );

    expect(element.querySelector('.badge')).toBeNull();
    expect(element.querySelector('.notice--unread')).toBeNull();
    expect(markButton()).toBeUndefined();
  });

  it('«Marcar como leído» emite el aviso', () => {
    const { host, markButton } = setup();

    markButton()!.click();

    expect(host.marked).toEqual([host.notice()]);
    expect(host.opened).toEqual([]);
  });

  it('mientras marca, el botón queda bloqueado', () => {
    const { host, fixture, markButton } = setup();

    host.busy.set(true);
    fixture.detectChanges();

    expect(markButton()!.disabled).toBe(true);
  });

  it('el enlace interno lleva a la ruta del aviso y emite que se abrió', () => {
    const { host, link } = setup();

    expect(link()!.getAttribute('href')).toBe('/app/editor/submissions/s-1');
    link()!.click();

    expect(host.opened).toEqual([host.notice()]);
  });

  it.each([
    'https://sitio-ajeno.example/',
    '//sitio-ajeno.example/app/x',
    'javascript:alert(1)',
    '/otra',
  ])('un enlace no interno (%s) no se convierte en enlace', (target) => {
    const { element, link } = setup(buildNotice({ payload: buildNoticePayload({ link: target }) }));

    expect(link()).toBeNull();
    expect(element.querySelector('[href]')).toBeNull();
  });

  it('muestra el texto como texto: no interpreta marcas HTML', () => {
    const { element } = setup(
      buildNotice({
        payload: buildNoticePayload({ message: '<img src=x onerror=alert(1)> hola' }),
      }),
    );

    expect(element.querySelector('img')).toBeNull();
    expect(text(element)).toContain('<img src=x onerror=alert(1)> hola');
  });
});
