"""Read-only verification of the audit hash chain (TSK-76, plan section 4.5).

It recomputes ``entry_hash`` of every row with the same canonical JSON the
writer used and checks that each ``previous_hash`` points to the row
before it. It never writes: not to the table (which is append-only by
trigger anyway) and not anywhere else.
"""

from __future__ import annotations

from dataclasses import dataclass

from apps.audit.models import AuditLog
from apps.audit.services import HASH_FIELDS, canonical_event_json, compute_entry_hash

CHUNK_ROWS = 2000


@dataclass(frozen=True)
class ChainDiscrepancy:
    """One broken link of the chain."""

    entry_id: int
    problem: str

    def __str__(self) -> str:
        return f"auditoría #{self.entry_id}: {self.problem}"


@dataclass(frozen=True)
class ChainReport:
    checked: int
    discrepancies: list[ChainDiscrepancy]


def verify_audit_chain() -> ChainReport:
    """Walk the whole chain in order and list every discrepancy found."""
    discrepancies: list[ChainDiscrepancy] = []
    previous_hash: str | None = None
    checked = 0
    for entry in AuditLog.objects.order_by("id").iterator(chunk_size=CHUNK_ROWS):
        checked += 1
        if entry.previous_hash != previous_hash:
            discrepancies.append(
                ChainDiscrepancy(
                    entry.pk,
                    "previous_hash no coincide con la entrada anterior "
                    "(falta o se alteró un registro)",
                )
            )
        event = {field: getattr(entry, field) for field in HASH_FIELDS}
        expected = compute_entry_hash(canonical_event_json(event), entry.previous_hash)
        if entry.entry_hash != expected:
            discrepancies.append(
                ChainDiscrepancy(entry.pk, "entry_hash no coincide con el contenido")
            )
        previous_hash = entry.entry_hash
    return ChainReport(checked=checked, discrepancies=discrepancies)
