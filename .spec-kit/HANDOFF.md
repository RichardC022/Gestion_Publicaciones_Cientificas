# HANDOFF — 29/10/2026

**Estado:** Fases 0–4 completas · Fase 5: **TSK-71 a TSK-83 hechas** (TSK-83 sin commit todavía) · **siguiente: TSK-84** (pruebas de frontend de la Fase 5) y después la Fase 6 (TSK-85 en adelante) · rama `dev/jostin-setup`.
**Detalle solo si hace falta:** `.spec-kit/compliance.md` (matriz de 57 filas, §2.6 Fase 5, §3 deuda, §4 siguiente paso). Código: `graphify query "<pregunta>"` antes de leer archivos.

## Últimos commits (Fase 5)
```
f3d47ca TSK 82 diálogo de corrección y veredicto corregido   9a3db07 TSK 81 auditoría global del Administrador
f1c206e TSK 80 catálogo público (búsqueda, listado, ficha)    d665766 TSK 79 pruebas de ciclo completo
d2d5f3d TSK 78 el veredicto del Editor consume la corrección  aa05996 TSK 77 autorización administrativa de corrección
639cabe TSK 75 notificaciones de panel y correo               fd65399 TSK 74 catálogo público (rotulado «TSK 73» por error)
a7c261e TSK 73 consulta administrativa de auditoría           af289de TSK 72 rol de aplicación sin UPDATE/DELETE en auditoría
fd87eaf TSK 71 cron de avisos, limpieza e integridad          e686f7b TSK 76 comandos de avisos, limpieza e integridad
```
**Sin commit:** TSK-83 (avisos en el frontend) y esta actualización de `HANDOFF.md`/`compliance.md`.

## Pruebas (último resultado)
| Suite | Resultado | Comando |
|---|---|---|
| Backend | 1580 ✅ · 11 omitidas · 0 `xfail` (antes 1312 · 8 · 1; el `xfail` de D-10 se cerró) — corrida completa del 29/10 | `docker compose run --rm --no-deps -v "$PWD/backend:/app" backend sh -c "python -m pip install --quiet --user -r requirements/development.txt; python -m pytest -q -p no:cacheprovider"` (≈ 42 min; añade una carpeta de `tests/` para acotar) |
| Frontend | 1282 ✅ (74 archivos) · `ng build --configuration production` OK (solo el aviso NG8113, D-13) | `cd frontend && npx ng test --watch=false` · `npx ng build --configuration production` |
| Volumen | ✅ (TSK-58, no repetido) | `./scripts/smoke_media_isolation.sh` |
| Migraciones | sin pendientes (`publications/0009_verdict_correction` y `notifications/0001_initial` son las nuevas de la Fase 5) | `docker compose run --rm --no-deps -v "$PWD/backend:/app" backend python manage.py makemigrations --check --dry-run` |

Docker (tras cambios): `docker compose up -d --build backend web` · apagar: `docker compose stop`. El `backend` aplica solo `apply_db_privileges` tras cada `migrate` (TSK-72).

## 🔴 D-01 — credencial publicada (único crítico)
`credentials.txt` ya no se versiona, pero **sigue en el historial**: `ad22b2c` está en `origin/dev/jostin-setup`, `origin/develop`, `personal/develop`, `personal/main`. **Rotar esa credencial** (no depende de código). Reescribir el historial exige `push --force` y tu aprobación explícita. No se ha leído su contenido.

## Qué entregó la Fase 5
**DevOps** — **71** `scripts/cron/gpc.cron` programa, además de respaldo y expiración, `send_pending_notifications` (cada minuto), `cleanup_idempotency_keys` (03:00) y `verify_integrity` (día 1, 03:30), cada uno con su `flock` y su log. **72** `apply_db_privileges` (`apps/audit/privileges.py`): el rol de la aplicación no tiene `UPDATE`/`DELETE` sobre la auditoría; se aplica tras cada `migrate`; el rol administrador se usa solo con `DB_USE_ADMIN=1` (README §3.6.1).

**Backend**
- **73** `GET /api/admin/audit/` y `{id}/` (`apps/audit/`): solo `ADMIN`, filtros por fecha, actor, acción, manuscrito y resultado; cada consulta se audita (`AUDIT_QUERIED`, `AUDIT_DETAIL_VIEWED`); el detalle de un evento de veredicto lleva `can_authorize_correction`.
- **74** `GET /api/catalog/`, `{code}/`, `{code}/document/` (`catalog_*.py`): públicos, solo `ACCEPTED` y activos; `404` si no es público, `410` si el PDF se retiró; entrega por `X-Accel-Redirect` a `/_catalog/` y descarga auditada. **La baja lógica ahora retira el artículo del catálogo** (cierra el `xfail` de D-10).
- **75** `apps/notifications/`: receptores de las **doce** señales (once anteriores + `verdict_correction_authorized`); un aviso por destinatario y evento (`uq_notification_recipient_event`); `payloads.py` es una lista blanca de siete campos de texto (la no fuga es estructural); `GET /api/notifications/` (`?read=true|false`, `unread_count`), `PATCH …/{id}/read/`, `POST …/read-all/`; el aviso ajeno responde `404`. El correo es un gemelo `EMAIL` que entrega `send_pending_notifications` con reintentos; el panel no depende del SMTP.
- **76** los tres comandos de gestión; `verify_integrity` solo lee y sale distinto de cero si hay discrepancias.
- **77** `VerdictCorrection` + `POST /api/admin/verdicts/{id}/authorize-correction/` (motivo 10–1000, `Idempotency-Key`, `409` si el veredicto no es el último, hay versión posterior o ya hay una autorización activa). **78** el veredicto del Editor consume la autorización (deriva `previous_verdict`, ignora cualquier valor del cliente), registra `VERDICT_CORRECTED` y actualiza estado, catálogo y ronda en una transacción. **79** pruebas de ciclo completo (`tests/phase5.py`, `test_phase5_*`); corrigió que la auditoría normalice la IP antes de encadenar el hash.

**Frontend**
- **80** `/catalog` y `/catalog/:code` sin guard ni JWT, filtros combinados, paginación en la URL, ficha con visor de PDF; sin evaluaciones, revisores ni historial.
- **81** `/app/admin/audit` (tabla paginada, filtros en la URL) y `/audit/:id` (hashes, datos de lista blanca, sin PII).
- **82** `features/admin/verdict-correction-dialog/` (motivo 10–1000, avisa que la decisión anterior se conserva); el botón «Habilitar corrección» aparece solo si `can_authorize_correction` es `true` y desaparece al confirmar. `VerdictFormComponent` recibe `correction` (`SubmissionDetail.correction_authorization`): muestra el veredicto que sustituiría, nace vacío, nunca envía `previous_verdict_id` y el historial marca ambas decisiones.
- **83** (sin commit) `core/models/notification.model.ts`, `core/services/notification.service.ts` (guarda el contador de no leídos en una señal), `features/notifications/notification-item/` y `notification-list/` (filtro Todos/No leídos y página en la URL, marcar uno o todos, el enlace solo se activa si es `/app/…`), y `ShellComponent` pasa el contador real a la campana. Para las pruebas que montan el shell real existe `core/testing/notification.service.stub.ts`.

## Pendiente / decisiones abiertas
- **TSK-84** consolida pruebas que ya existen por tarea (catálogo, filtros de auditoría, diálogo de corrección, veredicto con autorización, avisos con `403/404/409/410`); revisar qué falta contra sus tres criterios antes de escribir de nuevo. Nombra Jasmine/Karma pero el proyecto usa Vitest (D-12).
- **Contador de la campana (D-23):** se lee al entrar al área autenticada y se ajusta al marcar; no hay sondeo, así que un aviso que llega mientras se navega no aparece hasta recargar o abrir la lista.
- **Avisos del Autor/Revisor** nunca llevan identidades cruzadas por construcción (`payloads.py`); `test_notifications.py` y `test_phase5_notifications.py` lo prueban sobre la notificación construida (cierra el pendiente de la Fase 4).
- **D-11:** las cuatro secciones del panel siguen devolviendo `{}`.
- **D-21:** la descarga real del Revisor y del catálogo a través de Nginx sigue sin probarse en navegador; el humo del volumen solo prueba el control positivo del catálogo.
- Latente (D-20): `resolve_assignment` (`reviews/permissions.py`).

## Trampas ya conocidas
- `docker compose run` usa el código de la **imagen**: monta `-v "$PWD/backend:/app"`; `makemigrations` igual. Nombres de índice ≤ 30 caracteres. `ruff` no está (D-16).
- `Now()` en PostgreSQL es `STATEMENT_TIMESTAMP()`: para probar el borde de `due_at` se congela `evaluations.Now`. Baja lógica = `is_active=False` + `withdrawn_at`.
- Angular: `http.expectOne('/url')` compara con los query params → `expectOne((r) => r.url === '/url')`. Varios `<dialog>`: acota por componente. `RouterTestingHarness.create()` solo una vez por prueba. `forkJoin` cancela la petición hermana ante el primer error.
- Un `effect` que **lee** la señal que él mismo escribe se reinicia en cada cambio: usa `untracked`.
- **Si un componente dispara una petición al crearse y existe un spec que monta `routes` reales**, esas pruebas fallan con «Expected no open requests» (y los siguientes archivos del mismo hilo arrastran «Cannot configure the test module…»): proporciona el stub o responde la petición.
- Un enlace de prueba que navega a una ruta que no existe en `provideRouter([...])` lanza `NG04002` asíncrono y contamina las pruebas siguientes: registra la ruta destino.
- En diálogos con `[ngModel]` el valor y el `disabled` se aplican de forma asíncrona: espera `fixture.whenStable()` antes de afirmar.
- Respuestas de error: `userMessage` sale del **código** (`api-error.model.ts`); para el motivo concreto de un `409` usa `error.message`.
- **No** ejecutes `prettier --write` sobre carpetas ni con globs amplios (reformatea archivos ajenos): comprueba antes con `git show HEAD:<ruta> | npx prettier --stdin-filepath <ruta> --check` y formatea solo los que estaban limpios. Ya incumplían Prettier: `editor.model.ts`, `expired-assignments.component.ts`, `verdict-form.component.ts` (+spec), `submission-detail.component.ts` (+spec), `shell.component.spec.ts`, `audit.service.spec.ts`, `audit-log-detail.component.spec.ts`.
- Pruebas que leen código fuente (`no-authorship.spec.ts`) usan `node:fs` por import dinámico (no hay `@types/node`).

## Reglas de trabajo
Constitución: código en inglés; comentarios, docs y commits en español; SOLID/KISS/DRY/YAGNI; doble ciego estricto. **Sin commits ni push salvo orden** (entregar resultados de pruebas + sugerencia de commit + comandos Docker si aplican). Antes de explorar código: `graphify query`; al terminar: `graphify update .` y actualizar `compliance.md` solo si cambia el estado de la deuda.

## Deuda abierta (una línea)
D-02 TLS · D-03 `db` (5432) y `adminer` (8888) publicados · D-11 panel con 4 secciones `{}` · D-07/D-16/D-18 CI (tolera «sin pruebas», sin pruebas del frontend), linter, logrotate (ahora 5 logs de cron) · D-04/D-12/D-13/D-14/D-15 menores · D-20/D-21/D-22/D-23 bajas. **Resueltas en la Fase 5:** D-09 (`verify_integrity`), D-10 (retirada del catálogo y receptores de las señales), D-17 (catálogo público).
