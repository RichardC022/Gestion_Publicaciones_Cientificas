"""Huella del estado de un stack (TSK-87): filas por modelo y hash de cada archivo.

Se ejecuta DENTRO del contenedor del backend y solo LEE:

    docker compose -p gpc_verify ... exec -T backend python manage.py shell < scripts/verify/fingerprint.py

Imprime una línea ``FINGERPRINT {json}``. Comparar la huella antes del desastre
y después de restaurar demuestra que la base, los PDF y la auditoría volvieron
idénticos, sin depender de cómo los guarde cada tabla.
"""

import hashlib
import json
from pathlib import Path

from django.apps import apps
from django.conf import settings

from apps.audit.models import AuditLog

rows = {model._meta.label: model.objects.count() for model in apps.get_models()}

files = {}
root = Path(settings.MEDIA_ROOT)
for path in sorted(p for p in root.rglob("*") if p.is_file()):
    files[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()

last = AuditLog.objects.order_by("-id").first()
print(
    "FINGERPRINT "
    + json.dumps(
        {
            "rows": rows,
            "files": files,
            "audit_last": str(last.id) if last else None,
            "audit_last_hash": last.entry_hash if last else None,
        },
        sort_keys=True,
    )
)
