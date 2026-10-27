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
