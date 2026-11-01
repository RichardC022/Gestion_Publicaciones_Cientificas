# HANDOFF — 29/10/2026

**Estado:** Fases 0–4 completas · Fase 5 completa · Fase 6: **TSK-85, TSK-86 y TSK-87 hechas** (TSK-87 sin commit todavía) · **siguiente: TSK-88** (runbook del piloto) · rama `dev/jostin-setup`.
**Detalle solo si hace falta:** `.spec-kit/compliance.md` (matriz de 61 filas, §2.6 Fase 5, §3 deuda, §4 siguiente paso). Código: `graphify query "<pregunta>"` antes de leer archivos.

## Últimos commits (Fase 5)
```
87e13a7 TSK 83 panel y lista de avisos con contador         f3d47ca TSK 82 diálogo de corrección y veredicto corregido
9a3db07 TSK 81 auditoría global del Administrador            f1c206e TSK 80 catálogo público (búsqueda, listado, ficha)
d665766 TSK 79 pruebas de ciclo completo                      d2d5f3d TSK 78 el veredicto del Editor consume la corrección
aa05996 TSK 77 autorización administrativa de corrección      639cabe TSK 75 notificaciones de panel y correo
fd65399 TSK 74 catálogo público (rotulado «TSK 73» por error) a7c261e TSK 73 consulta administrativa de auditoría
af289de TSK 72 rol sin UPDATE/DELETE en auditoría             fd87eaf TSK 71 cron de avisos, limpieza e integridad
e686f7b TSK 76 comandos de avisos, limpieza e integridad
```
Último commit: `725c9b2` TSK 86 (prueba de carga y límites de memoria).
**Sin commit:** TSK-87 (`scripts/verify_pilot.sh`, `scripts/verify/`, `scripts/make_dev_cert.sh`, `docker-compose.dev.yml`, TLS en `nginx/conf.d/default.conf`, `restore.sh` corregido, `docker-compose.yml` sin `db`/`adminer` publicados y con `443`, `docker-compose.load.yml` con puerto TLS, `smoke_media_isolation.sh` y `load_test.py` por HTTPS, CI con comprobación de puertos, README §3.9/§7/§8.3/§10.5) y esta actualización de `HANDOFF.md`/`compliance.md`.

## Pruebas (último resultado)
| Suite | Resultado | Comando |
|---|---|---|
| Backend | 1580 ✅ · 11 omitidas · 0 `xfail`; cobertura 98 % (97 % en servicios y permisos) — corrida completa del 31/10 con DRF 3.18.3 (≈ 16 min) | `docker compose run --rm --no-deps -v "$PWD/backend:/app" backend sh -c "python -m pip install --quiet --user -r requirements/development.txt; python -m pytest -q -p no:cacheprovider"` (≈ 42 min; añade una carpeta de `tests/` para acotar) |
| Frontend | 1302 ✅ (74 archivos) · `ng build --configuration production` OK (solo el aviso NG8113, D-13) | `cd frontend && npx ng test --watch=false` · `npx ng build --configuration production` |
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
- **83** `core/models/notification.model.ts`, `core/services/notification.service.ts` (guarda el contador de no leídos en una señal), `features/notifications/notification-item/` y `notification-list/` (filtro Todos/No leídos y página en la URL, marcar uno o todos, el enlace solo se activa si es `/app/…`), y `ShellComponent` pasa el contador real a la campana. Para las pruebas que montan el shell real existe `core/testing/notification.service.stub.ts`.
- **84** (sin commit) no añade código: contrasta sus tres criterios con los specs y cierra los huecos. `core/testing/http-error.fixtures.ts` (`HTTP_ERROR_CASES`, `errorResponse`) simula `403/404/409/410` con el sobre real; se usa en avisos, catálogo y lista de auditoría.

## Pendiente / decisiones abiertas
- **Fase 6:** TSK-85, TSK-86 y TSK-87 hechas. Siguen TSK-88 runbook (D-18, D-21), TSK-89 seguridad/IDOR, TSK-90 consultas y cobertura, TSK-91 E2E Playwright, TSK-92 accesibilidad y responsive. Confirmar el inicio de cada una.
- **TSK-87 (cómo quedó):** `./scripts/verify_pilot.sh` (~6 min) levanta el stack aislado `gpc_verify` (HTTPS 19443, HTTP 19080), siembra por la API real y comprueba **61 criterios (61/61 en verde)**: respaldo → un respaldo alterado se rechaza sin tocar la base → se borran los volúmenes y `restore.sh` reconstruye sobre una base vacía → huella idéntica (filas por modelo, SHA-256 de cada archivo, último hash de auditoría) → `verify_integrity` pasa, detecta un PDF alterado y restaurar lo repara → puertos, ubicaciones internas, redirección, TLS, certificado, cookie y cabeceras. **Hallazgos corregidos:** (1) `restore.sh` fallaba sobre una base nueva (el volcado va con `--no-privileges`, no existía el rol `gpc_runtime`): ahora corre `apply_db_privileges` tras `pg_restore`; (2) `db`/`adminer` publicados (D-03): `adminer:6.1.2` y el puerto de `db` pasaron a `docker-compose.dev.yml` (`127.0.0.1`); (3) TLS (D-02): `443` con TLS 1.2/1.3 y `80` solo redirige; Nginx **no arranca sin** `nginx/certs/{fullchain,privkey}.pem` (`./scripts/make_dev_cert.sh` crea uno autofirmado sin sobrescribir); (4) `/api/` repetía tres cabeceras de seguridad (Django y Nginx): `proxy_hide_header`. Todo el acceso local pasa a `https://localhost` (certificado autofirmado, aviso del navegador). **Para aplicarlo al entorno de trabajo:** `docker compose up -d --build --remove-orphans`. No está en CI (D-29).
- **TSK-86 (cómo quedó):** `./scripts/load_test.sh [--timeouts]` levanta un stack aislado (`-p gpc_load`, puerto 18080, otros volúmenes), siembra por la API real y comprueba 28 criterios (50 logins/consultas/descargas, cargas de 50 MB, 51 MB → 413 Django, 61 MB → 413 Nginx sin llegar a Gunicorn, buffer en disco, clientes lentos, corte de 120 s, memoria). **28/28 en verde.** Se definieron los `mem_limit` que no existían: backend 1 GB, db 512 MB, web 256 MB (picos 323/39/68 MiB). Hay que recrear los contenedores para que apliquen. No está en CI; solo `localhost` (D-27 login ≈ 2,5 s con 50 simultáneos, D-28).
- **TSK-85 (cómo quedó):** `ci.yml` con 8 jobs, `backend/.coveragerc` y umbral `COVERAGE_MIN=80` sobre servicios y permisos (medido 97 %). **Aún no se ha ejecutado en GitHub Actions:** revisar la primera corrida. `pip-audit` falla con cualquier aviso; los de herramientas de desarrollo del frontend solo se informan (D-25).
- **Contador de la campana (D-23):** se lee al entrar al área autenticada y se ajusta al marcar; no hay sondeo, así que un aviso que llega mientras se navega no aparece hasta recargar o abrir la lista.
- **Avisos del Autor/Revisor** nunca llevan identidades cruzadas por construcción (`payloads.py`); `test_notifications.py` y `test_phase5_notifications.py` lo prueban sobre la notificación construida (cierra el pendiente de la Fase 4).
- **D-11:** las cuatro secciones del panel siguen devolviendo `{}`.
- **D-21:** la descarga real del Revisor y del catálogo a través de Nginx sigue sin probarse en navegador; el humo del volumen solo prueba el control positivo del catálogo.
- Latente (D-20): `resolve_assignment` (`reviews/permissions.py`).

## Trampas ya conocidas
- TSK-87: tras TLS, `http://localhost` solo redirige (`$host` pierde un puerto distinto de 443, así que en los stacks aislados la verificación del `Location` solo mira esquema, ruta y consulta). `openssl s_client -tls1_1` necesita `-cipher 'ALL:@SECLEVEL=0'`; la línea «Protocol : TLSv1.1» del resultado es el intento, no la negociación: el rechazo se reconoce por «alert protocol version» / «Cipher is (NONE)». `docker compose run backend <comando>` NO ejecuta el `command` del servicio (ni `migrate` ni `apply_db_privileges`). `COMPOSE` de `backup.sh`/`restore.sh` permite apuntarlos a un proyecto aislado.
- Prueba de carga: el sondeo del buffer de Nginx debe ejecutarse como `-u nginx` (root no tiene `CAP_SYS_PTRACE` para leer sus descriptores) y Nginx borra el archivo temporal al crearlo, así que `du` no lo ve. El PDF de prueba debe estar referenciado por la página o la sanitización lo descarta.
- `docker compose run` usa el código de la **imagen**: monta `-v "$PWD/backend:/app"`; `makemigrations` igual. Nombres de índice ≤ 30 caracteres. `ruff` no está (D-16).
- `Now()` en PostgreSQL es `STATEMENT_TIMESTAMP()`: para probar el borde de `due_at` se congela `evaluations.Now`. Baja lógica = `is_active=False` + `withdrawn_at`.
- Angular: `http.expectOne('/url')` compara con los query params → `expectOne((r) => r.url === '/url')`. Varios `<dialog>`: acota por componente. `RouterTestingHarness.create()` solo una vez por prueba. `forkJoin` cancela la petición hermana ante el primer error.
- Un `effect` que **lee** la señal que él mismo escribe se reinicia en cada cambio: usa `untracked`.
- **Si un componente dispara una petición al crearse y existe un spec que monta `routes` reales**, esas pruebas fallan con «Expected no open requests» (y los siguientes archivos del mismo hilo arrastran «Cannot configure the test module…»): proporciona el stub o responde la petición.
- Un enlace de prueba que navega a una ruta que no existe en `provideRouter([...])` lanza `NG04002` asíncrono y contamina las pruebas siguientes: registra la ruta destino.
- En diálogos con `[ngModel]` el valor y el `disabled` se aplican de forma asíncrona: espera `fixture.whenStable()` antes de afirmar.
- Respuestas de error: `userMessage` sale del **código** (`api-error.model.ts`); para el motivo concreto de un `409` usa `error.message`. Un cuerpo sin `{ error: { code } }` se ve como `SERVER_ERROR` aunque el estado sea 403/404/409/410 (D-24): en pruebas usa `HTTP_ERROR_CASES`, no `{}`.
- **No** ejecutes `prettier --write` sobre carpetas ni con globs amplios (reformatea archivos ajenos): comprueba antes con `git show HEAD:<ruta> | npx prettier --stdin-filepath <ruta> --check` y formatea solo los que estaban limpios. Ya incumplían Prettier: `editor.model.ts`, `expired-assignments.component.ts`, `verdict-form.component.ts` (+spec), `submission-detail.component.ts` (+spec), `shell.component.spec.ts`, `audit.service.spec.ts`, `audit-log-detail.component.spec.ts`.
- Pruebas que leen código fuente (`no-authorship.spec.ts`) usan `node:fs` por import dinámico (no hay `@types/node`).

## Reglas de trabajo
Constitución: código en inglés; comentarios, docs y commits en español; SOLID/KISS/DRY/YAGNI; doble ciego estricto. **Sin commits ni push salvo orden** (entregar resultados de pruebas + sugerencia de commit + comandos Docker si aplican). Antes de explorar código: `graphify query`; al terminar: `graphify update .` y actualizar `compliance.md` solo si cambia el estado de la deuda.

## Deuda abierta (una línea)
D-11 panel con 4 secciones `{}` · D-16 sin linter (`ruff`), D-18 logrotate (ahora 5 logs de cron) · D-04/D-12/D-13/D-14/D-15 menores · D-20/D-21/D-22/D-23/D-24/D-25/D-26/D-27/D-28/D-29 bajas; D-06 (HSTS `preload` con certificado autofirmado) media; falta instalar el certificado institucional. **Resueltas en las Fases 5 y 6:** D-02 y D-03 (TSK-87), D-07 (TSK-85), D-09 (`verify_integrity` y restauración probada), D-10 (retirada del catálogo y receptores de las señales), D-17 (catálogo público).
