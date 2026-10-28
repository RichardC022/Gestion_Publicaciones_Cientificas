"""Verify the PDF hashes and the audit hash chain (TSK-76).

Run monthly through ``scripts/verify_integrity.sh``. It is strictly
read-only: it recomputes and compares, and never rewrites a file, a hash
or an audit row. Every discrepancy is listed and the command exits with a
non-zero code, so a cron or CI job notices it.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.audit.integrity import verify_audit_chain
from apps.publications.services.integrity import verify_files


class Command(BaseCommand):
    """Report hash discrepancies without modifying anything."""

    help = "Recalcula los hashes de PDFs y la cadena de auditoría; falla si hay discrepancias."

    def handle(self, *args, **options) -> None:
        files = verify_files()
        chain = verify_audit_chain()
        self.stdout.write(
            f"Archivos verificados: {files.files_checked}; "
            f"entradas de auditoría verificadas: {chain.checked}."
        )
        problems = [str(item) for item in (*files.discrepancies, *chain.discrepancies)]
        if not problems:
            self.stdout.write(self.style.SUCCESS("Integridad correcta: sin discrepancias."))
            return
        for line in problems:
            self.stderr.write(f"DISCREPANCIA — {line}")
        raise CommandError(f"Se encontraron {len(problems)} discrepancia(s) de integridad.")
