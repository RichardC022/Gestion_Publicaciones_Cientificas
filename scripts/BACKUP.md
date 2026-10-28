# Respaldo, restauración y verificación de integridad

Los scripts operan desde el host y usan Docker Compose. No deben ejecutarse dentro del contenedor.

## Respaldo diario

El respaldo se genera con:

```bash
./scripts/backup.sh
```

Variables opcionales en `.env`:

```dotenv
BACKUP_ROOT=/backups
RETENTION_DAYS=30
```

Cada respaldo queda en un directorio con modo `0700` y contiene:

- `database.dump`: respaldo lógico de PostgreSQL en formato custom (`pg_dump -Fc`).
- `media.tar.gz`: contenido completo de `/data/media`.
- `SHA256SUMS`: checksums SHA-256 de los dos artefactos.

La retención elimina respaldos completos con más de `RETENTION_DAYS` días, pero siempre conserva el más reciente. `BACKUP_ROOT` no debe estar dentro del repositorio ni dentro de `/data/media`.

## Restauración

Para restaurar un respaldo:

```bash
./scripts/restore.sh /backups/20261023T021500
```

El script pide confirmación. Para entornos de prueba o automatización:

```bash
./scripts/restore.sh --yes /backups/20261023T021500
```

La restauración:

1. Verifica los checksums del respaldo.
2. Detiene `web` y `backend`.
3. Restaura PostgreSQL con `pg_restore --clean --if-exists`.
4. Reemplaza el contenido de `media_data` y extrae `media.tar.gz`.
5. Normaliza permisos con `scripts/init_media.sh`.
6. Ejecuta `scripts/verify_integrity.sh`.
7. Levanta `db`, `backend` y `web`.
8. Ejecuta `python manage.py check` y valida la estructura del volumen.

No restaures sobre el entorno institucional sin haber probado antes el respaldo en un entorno aislado.

## Verificación de integridad

La verificación recalcula los hashes de los PDFs y comprueba la cadena de auditoría:

```bash
./scripts/verify_integrity.sh
```

El comando no modifica archivos ni registros. Si encuentra una discrepancia, termina con un código de salida distinto de cero.

## Prueba mensual de restauración (smoke restore)

Un respaldo no se considera válido hasta que se restaura y verifica en un entorno aislado.

Procedimiento recomendado:

1. Genera el respaldo más reciente.
2. Copia el directorio del respaldo al entorno de prueba.
3. Ejecuta `./scripts/restore.sh --yes <directorio-del-respaldo>`.
4. Confirma que el comando termina con código `0`.
5. Registra fecha, responsable, respaldo utilizado y resultado.
6. Si la prueba falla, no uses ese respaldo como respaldo válido; genera uno nuevo y repite la prueba.

## Programación en el host

Instala la plantilla incluida:

```bash
sudo cp scripts/cron/gpc.cron /etc/cron.d/gpc
sudo chown root:root /etc/cron.d/gpc
sudo chmod 0644 /etc/cron.d/gpc
```

Ajusta la ruta `/opt/gpc` si el repositorio está en otro directorio.

La plantilla incluye también la expiración de asignaciones (TSK-45 y TSK-49): cada minuto ejecuta `mark_expired_assignments`, que marca como `EXPIRED` las asignaciones `ACTIVE` con `due_at <= now()`, sin revocar ni reasignar, y escribe en `/var/log/gpc-expire.log` solo cuando hubo trabajo o un error. El contenedor `backend` debe estar en ejecución. Para probarla a mano:

```bash
docker compose exec backend python manage.py mark_expired_assignments
```

La plantilla incluye además las tareas de la Fase 5 (TSK-71 y TSK-76), todas dentro del contenedor `backend` y con un `flock` propio cada una:

| Tarea | Comando | Frecuencia | Log |
|---|---|---|---|
| Avisos por correo | `send_pending_notifications` | Cada minuto | `/var/log/gpc-notify.log` |
| Limpieza de idempotencia | `cleanup_idempotency_keys` | Diaria, 03:00 | `/var/log/gpc-cleanup.log` |
| Verificación de integridad | `verify_integrity` | Día 1 de cada mes, 03:30 | `/var/log/gpc-integrity.log` |

- **Reintentos de avisos:** un aviso de correo fallido queda en `FAILED` y se reintenta tras 1 min, 5 min, 15 min, 1 h y 4 h; tras el sexto intento fallido deja de reintentarse y permanece `FAILED` con su `last_error`. Un aviso `SENT` no se reenvía y el aviso del panel no depende del correo. `EMAIL_TIMEOUT` (10 s por defecto) limita la espera al SMTP.
- **Limpieza:** solo elimina las claves con `expires_at` vencido (24 h tras guardarse); las vigentes no se tocan.
- **Verificación:** solo lee. Si encuentra discrepancias de hash en PDFs o en la cadena de auditoría las lista en el log y termina con código distinto de cero; no corrige nada.
- Los logs registran conteos y códigos de error, nunca el contenido de los avisos, correos ni credenciales.

Para probarlas a mano:

```bash
docker compose exec backend python manage.py send_pending_notifications
docker compose exec backend python manage.py cleanup_idempotency_keys
docker compose exec backend python manage.py verify_integrity
```

## Respaldo y privilegios de base de datos (TSK-72)

- El respaldo diario de las 02:15 usa `pg_dump` con el administrador (`POSTGRES_USER`), que puede leer todo, incluida la auditoría; las restricciones del rol de aplicación (`APP_DB_USER`) no lo afectan.
- Los respaldos se toman y se restauran con `--no-privileges`: no guardan los permisos del rol de aplicación. Tras una restauración, `pg_restore --clean` recrea las tablas con los permisos por defecto, incluida `audit_audit_log`. Al levantar `backend`, el entrypoint ejecuta `migrate` y `apply_db_privileges` con el administrador y vuelve a quitar `UPDATE`/`DELETE`/`TRUNCATE` sobre la auditoría. No arranques ni expongas la aplicación por otra vía antes de ese paso.
- Comprueba el respaldo con `scripts/verify_integrity.sh` y, tras restaurar, el `DELETE` sobre la auditoría descrito en el README §3.6.1.
