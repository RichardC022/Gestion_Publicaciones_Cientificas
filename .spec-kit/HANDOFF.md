# HANDOFF — 27/10/2026

**Estado:** Fases 0–4 completas (Fase 4: TSK-58 a TSK-70 ✅) · **siguiente: Fase 5, TSK-71** · rama `dev/jostin-setup`, árbol limpio, 0 commits sin subir.
**Detalle solo si hace falta:** `.spec-kit/compliance.md` (matriz, §2.5 Revisor, §3 deuda con D-20 a D-22, §4 siguiente paso): ya recoge la Fase 4. Código: `graphify query "<pregunta>"` antes de leer archivos.

## Últimos commits (Fase 4)
```
5a27a9b TSK 70 bandeja de incidentes confidenciales del Editor        eb3bbce TSK 66 bandeja, detalle y descarga del Revisor
f3cc4c1 TSK 69 historial del Revisor e integración con rutas reales   df75135 TSK 65 doble ciego E2E, concurrencia, inmutabilidad
628181f TSK 68 diálogos de conflicto y fuga de identidad              24bee83 TSK 64 · 962329e TSK 63 · 2b05c99 TSK 62
32d65fd TSK 67 formulario de evaluación                               172cc81 TSK 60+61 · 9a96a14 TSK 59
```

## Pruebas (último resultado)
| Suite | Resultado | Comando |
|---|---|---|
| Backend | 1312 ✅ · 8 omitidas · 1 `xfail` (D-10) — corrida completa repetida hoy tras la TSK-70 | `docker compose run --rm --no-deps -v "$PWD/backend:/app" backend sh -c "python -m pip install --quiet --user -r requirements/development.txt; python -m pytest -q -p no:cacheprovider"` (~12 min; añade `tests/reviews` para acotar) |
| Frontend | 1045 ✅ (57 archivos) · `ng build` OK (solo el aviso NG8113, D-13) | `cd frontend && npx ng test --watch=false` · `npx ng build --configuration production` |
| Volumen | ✅ (TSK-58, no repetido hoy) | `./scripts/smoke_media_isolation.sh` |
| Migraciones | sin pendientes (`reviews/0003_incident_report` es la última) | mismo `docker compose run … python manage.py makemigrations --check --dry-run` |

Docker (tras cambios): `docker compose up -d --build backend web` · apagar: `docker compose stop`.

## 🔴 D-01 — credencial publicada (único crítico)
`credentials.txt` ya no se versiona ni está en el índice, pero **sigue en el historial**: `ad22b2c` está en `origin/dev/jostin-setup`, `origin/develop`, `personal/develop`, `personal/main`. **Rotar esa credencial** (no depende de código). Reescribir el historial exige `push --force` y tu aprobación explícita. No se ha leído su contenido.

## Qué entregó la Fase 4 (hoy)
**Backend (TSK-59 a 65)** — `backend/apps/reviews/`, API en `/api/reviewer/**` (`reviewer_urls.py`) y `/api/editor/incidents/**`:
- **59** `IncidentReport` + `uq_incident_open` + CHECK de resuelto · **60/61** `Assignment.objects.for_reviewer`, serializadores de lista blanca, bandeja y detalle, PDF sanitizado (`410` si no `ACTIVE`, nombre genérico, `X-Accel-Redirect`, auditoría previa → `503` si falla).
- **62** `GET/PUT …/evaluation/` (ETag = `lock_version`, nace en **1**; el borrador vacío es `"0"`) y `POST …/evaluation/submit/`; corte por `due_at` con el reloj de la BD (`410`), `FINAL` inmutable (trigger `0002`), asignación → `COMPLETED`, auditoría y señal `evaluation_submitted`.
- **63** `POST …/conflict/` (bloquea la evaluación, no revoca) e historial `GET /api/reviewer/evaluations/[{id}/]` (solo `FINAL`, sin `confidential_comments`, resultado editorial = decisión + fecha).
- **64** `POST …/identity-leak/` (un `OPEN` por asignación → `409`) y Editor `GET incidents/?status=` + `POST incidents/{id}/resolve/` (una sola vez; `REQUEST_ANONYMIZED_VERSION` abre ronda sin veredicto y revoca; `REASSIGN` revoca; `DISMISS` solo cierra).
- **65** +40 pruebas: ciclo completo con PDFs reales y recorrido recursivo del grafo del PDF (sin `/Info`, XMP, `/EmbeddedFiles`, JS, `/OpenAction`, `/AA`, `/Launch`), señales solo con identificadores, 404 uniforme en 8 endpoints, concurrencia con dos conexiones (estable en 5 corridas), `FINAL` intocable por API, trigger y SQL crudo.

**Frontend (TSK-66 a 70)** — `features/reviewer/**`, `ReviewerService`, `reviewer.model.ts`:
- **66** bandeja (página en URL), detalle anonimizado, descarga del PDF **bajo demanda** (cada lectura se audita; se cachea en memoria), nombre `manuscript-<código>-v<n>.pdf` ignorando `Content-Disposition`, `deadline-countdown` (cuenta contra `due_at` con el desfase de la cabecera `Date`; emite `expired`).
- **67** formulario: 5 puntajes, recomendación, comentarios, declaración «sin conflicto» (solo en pantalla, no se persiste); guardar borrador / enviar (guarda primero si hay cambios; confirmación); `If-Match`; `409` versión → «conservar mi texto» / «usar lo guardado»; `410` y `409` de estado → solo lectura **con el texto a la vista**; `UnsavedChangesAware`.
- **68** `conflict-dialog` e `identity-leak-dialog` autónomos (llaman al servicio, no dan nada por enviado hasta el `2xx`); en el formulario ambos, en el detalle solo la fuga.
- **69** `evaluation-history` (solo lectura, detalle en la misma fila), `reviewer-module.integration.spec.ts` (rutas reales, roles, 404 ajeno, vencimiento, 409/410, guard de cambios) y `no-authorship.spec.ts` (lee el código fuente: ningún archivo del Revisor referencia campos de autoría ni del Editor).
- **70** `incident-list` del Editor: filtro `Abiertos` (def.) / `Resueltos` / `Todos` y `page` en la URL; tres resoluciones con efectos explicados y confirmación; `409` → mensaje y relectura.
- Refactors compartidos: `core/http/blob-download.ts` (`filenameFrom`, error en `Blob`; `manuscript.service` los reexporta) y `toPage` en `core/http/query-params.ts` (`expired-assignments` lo reexporta); `status-badge` con `ON_TIME`/`OVERDUE`/`EVALUATED`.

## Pendiente / decisiones abiertas
- **`compliance.md` actualizado con la Fase 4** (44 filas, ≈ 94,8 % global; nuevas deudas D-20 `resolve_assignment` latente, D-21 descarga del Revisor sin probar a través de Nginx, D-22 precisión del reloj del contador). Backend re-ejecutado hoy: 1312 ✅ · 8 omitidas · 1 `xfail`; migraciones sin cambios.
- **Notificaciones (TSK-75):** `notifications` está vacía; las señales `evaluation_submitted`, `reviewer_conflict_declared`, `incident_reported`, `incident_resolved` ya existen. Al llegar la TSK-75 añadir la comprobación de no fuga **sobre la notificación construida** (plan §2.9 punto 3); hoy solo se prueba el contrato del payload.
- **Reloj del contador (D-22):** el desfase sale de la cabecera `Date` (precisión de segundos). Si se quiere exactitud absoluta, añadir `server_now` al detalle del Revisor.
- **D-11:** no se verificó si la sección `reviewer` del panel se llena con datos reales; no se tocó.
- Latente (D-20): `resolve_assignment` (`reviews/permissions.py`) trata como asignación cualquier objeto con `reviewer_id` (p. ej. `Evaluation`); no usar `IsAssignedReviewer` sobre evaluaciones.

## Siguiente: Fase 5 (catálogo, auditoría y avisos)
Orden de `tasks.md`: DevOps **71** cron de avisos/limpieza/integridad, **72** privilegios de BD sobre auditoría · Backend **73** consulta de auditoría, **74** catálogo público, **75** notificaciones, **76** comandos `send_pending_notifications`/`cleanup_idempotency_keys`/`verify_integrity`, **77–79** corrección de veredicto y pruebas · Frontend **80–84** · DevOps **85–86**. Ojo: el cron de la 71 invoca comandos que crea la 76 (D-09, `verify_integrity` aún no existe); valorar hacer 76 antes o programarlos sin habilitar.

## Trampas ya conocidas
- `docker compose run` usa el código de la **imagen**: monta `-v "$PWD/backend:/app"`; `makemigrations` igual. Nombres de índice ≤ 30 caracteres. `ruff` no está (D-16).
- `Now()` en PostgreSQL es `STATEMENT_TIMESTAMP()` (avanza dentro de una transacción): para probar el borde de `due_at` se congela `evaluations.Now`. Baja lógica = `is_active=False` + `withdrawn_at`. El helper `submitted()` de `test_editor_api` no crea `StatusEvent`.
- Angular: `http.expectOne('/url')` compara con los query params → `expectOne((r) => r.url === '/url')`. Varios `<dialog>`: acota por componente (`app-confirm-dialog dialog`). `RouterTestingHarness.create()` solo una vez por prueba (para varias rutas usa `it.each`). `forkJoin` cancela la petición hermana ante el primer error (no la vuelvas a esperar).
- Un `effect` que **lee** la señal que él mismo escribe se reinicia en cada cambio (`deadline-countdown`): usa `untracked`.
- Respuestas de error: `userMessage` sale del **código** (`api-error.model.ts`); para el motivo concreto de un `409` usa `error.message`.
- **No** ejecutes `prettier --write` sobre carpetas enteras (reformatea archivos ajenos): solo los archivos tocados. `editor.model.ts` y `expired-assignments.component.ts` ya incumplían Prettier antes de la Fase 4.
- Pruebas que leen código fuente (`no-authorship.spec.ts`) usan `node:fs` por import dinámico (no hay `@types/node`).

## Reglas de trabajo
Constitución: código en inglés; comentarios, docs y commits en español; SOLID/KISS/DRY/YAGNI; doble ciego estricto. **Sin commits ni push salvo orden** (entregar resultados de pruebas + sugerencia de commit + comandos Docker si aplican). Antes de explorar código: `graphify query`; al terminar: `graphify update .` y actualizar `compliance.md` solo si cambia el estado de la deuda.

## Deuda abierta (una línea)
D-02 TLS · D-03 `adminer` publicado en `0.0.0.0:8888` · D-09 `verify_integrity` inexistente (TSK-76) · D-10 baja lógica no retira el catálogo y señales sin receptores · D-11 panel con 4 secciones `{}` · D-17 sin catálogo público (TSK-74) · D-07/D-16/D-18 CI, linter, logrotate · D-04/D-12/D-13/D-14/D-15 menores · D-20/D-21/D-22 (Fase 4) bajas.
