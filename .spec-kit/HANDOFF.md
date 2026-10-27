# HANDOFF — 27/10/2026

**Estado:** Fases 0–3 completas · Fase 4: TSK-58 ✅ · **siguiente: TSK-59** · rama `dev/jostin-setup`, árbol limpio, 0 commits sin subir.
**Detalle solo si hace falta:** `.spec-kit/compliance.md` §4 (siguiente paso) y §3 (deuda). Código: `graphify query "<pregunta>"` antes de leer archivos.

## Últimos 3 commits
```
ed3b109 feat: TSK 58 prueba de humo del aislamiento del volumen, job de CI y guardas de acceso al PDF
b75d25a docs: actualizar compliance.md con D-19 resuelta y TSK-58
9193345 fix: exponer feedback del veredicto al Autor con lista blanca de tres campos
```

## Pruebas (último resultado)
| Suite | Resultado | Comando |
|---|---|---|
| Backend | 975 ✅ · 8 omitidas · 1 `xfail` (D-10) | `docker compose run --rm --no-deps -v "$PWD/backend:/app" backend sh -c "python -m pip install --quiet --user -r requirements/development.txt; python -m pytest -q -p no:cacheprovider"` (~8 min; añade `tests/reviews` para acotar) |
| Frontend | 775 ✅ (45 archivos) | `cd frontend && npx ng test --watch=false` · build: `npx ng build --configuration production` |
| Volumen | ✅ | `./scripts/smoke_media_isolation.sh` |
| Migraciones | sin pendientes | mismo `docker compose run … python manage.py makemigrations --check --dry-run` |

Docker (tras cambios): `docker compose up -d --build backend web` · apagar: `docker compose stop`.

## 🔴 D-01 — credencial publicada (único crítico)
`credentials.txt` ya no se versiona ni está en el índice, pero **sigue en el historial**: `ad22b2c` está en `origin/dev/jostin-setup`, `origin/develop`, `personal/develop`, `personal/main`. **Rotar esa credencial** (no depende de código). Reescribir el historial exige `push --force` y tu aprobación explícita. No se ha leído su contenido.

## 🎯 TSK-59 — modelo `IncidentReport` (solo modelo y migración; sin endpoints)
- **Dónde:** `backend/apps/reviews/models.py` + migración `0003` · pruebas en `backend/tests/reviews/`. Spec: `tasks.md` TSK-59 · plan §1.14.1 (L511) y reglas §2.4 (L894).
- **Campos:** `assignment`, `manuscript`, `reporter` (FK `PROTECT`), `report_type` (`IDENTITY_LEAK`|`OTHER`), `description`, `status` (`OPEN`|`RESOLVED`, def. `OPEN`), `resolution` (`REQUEST_ANONYMIZED_VERSION`|`REASSIGN`|`DISMISS`, null), `correction_round` (FK null `PROTECT`), `resolved_by` (`SET NULL`), `created_at`, `resolved_at`.
- **BD:** `CHECK status='OPEN' OR (resolution y resolved_at no nulos)` · único parcial `uq_incident_open (assignment) WHERE status='OPEN'` · índice `idx_incident_status_date (status, created_at)`.
- **Criterios:** un 2.º `OPEN` por asignación falla (el `409` HTTP llega con los endpoints, TSK-60+) · `RESOLVED` exige `resolution` + `resolved_at` · el modelo no toca PDF, evaluación ni estado del manuscrito.
- **Patrón a imitar:** `Assignment`/`Evaluation` en el mismo archivo y `tests/reviews/test_models.py` (restricciones probadas con IntegrityError/raw SQL). Factoría nueva en `tests/factories.py`.

## Trampas ya conocidas
- `docker compose run` usa el código de la **imagen**: monta `-v "$PWD/backend:/app"` para probar lo editado; `makemigrations` se ejecuta igual.
- Nombres de índice de Django ≤ 30 caracteres. `ruff` no está disponible (D-16).
- Angular: `http.expectOne('/url')` compara con los query params; usa `expectOne((r) => r.url === '/url')`. Varios `<dialog>` en una página: acota por componente.
- Respuestas de error: `userMessage` sale del **código** (`api-error.model.ts`), no del texto del backend.

## Reglas de trabajo
Constitución: código en inglés; comentarios, docs y commits en español; SOLID/KISS/DRY/YAGNI; doble ciego estricto. **Sin commits ni push salvo orden** (entregar resultados de pruebas + sugerencia de commit). Al terminar: `graphify update .` y actualizar `compliance.md` solo si cambia el estado de la deuda.

## Deuda abierta (una línea)
D-02 TLS · D-03 `adminer` publicado en `0.0.0.0:8888` · D-10 baja lógica no retira el catálogo y señales sin receptores · D-11 panel con 4 secciones `{}` · D-17 sin catálogo público · D-07/D-16/D-18 CI, linter, logrotate · D-04/D-12/D-13/D-14/D-15 menores.
