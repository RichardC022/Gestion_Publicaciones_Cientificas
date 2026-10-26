"""Immutable, chronological history of a manuscript (HU-23, plan section 2.3).

It merges what the system has recorded and never rewrites it:

* ``CREATED`` / ``STATUS_CHANGED`` / ``WITHDRAWN`` — the status events;
* ``VERSION_SUBMITTED`` — each formal iteration, with the integrity seal
  of the exact PDF and the seal of the metadata sent with it;
* ``ROUND_OPENED`` — each correction round and the version that closed it.

An interrupted submission leaves no row, so it never appears. Entries
carry no actor, no file path and nothing of the sanitized copy: they
are safe to show to every role that can reach the manuscript.
Assignments, evaluations and verdicts join this timeline when their
apps exist (TSK-46 onwards).
"""

from __future__ import annotations

from typing import Any

from apps.publications.models import Manuscript

# Orden a igualdad de instante: el envío escribe versión, ronda y evento
# de estado en la misma transacción.
_RANK = {"VERSION_SUBMITTED": 0, "ROUND_OPENED": 1, "STATUS": 2}


def _status_entry(event) -> tuple[Any, ...]:
    if event.from_status is None:
        kind = "CREATED"
    elif event.metadata.get("withdrawn"):
        kind = "WITHDRAWN"
    else:
        kind = "STATUS_CHANGED"
    entry = {
        "type": kind,
        "occurred_at": event.created_at,
        "from_status": event.from_status,
        "to_status": event.to_status,
        "reason": event.reason,
        "version_number": event.metadata.get("version_number"),
        "round_number": event.metadata.get("round_number"),
    }
    return event.created_at, _RANK["STATUS"], event.pk, entry


def _version_entry(version) -> tuple[Any, ...]:
    entry = {
        "type": "VERSION_SUBMITTED",
        "occurred_at": version.submitted_at,
        "version_id": version.pk,
        "version_number": version.version_number,
        "round_number": version.round_number,
        "original_filename": version.original_filename,
        "original_size_bytes": version.original_size_bytes,
        "integrity_seal": f"sha256:{version.original_sha256}",
        "metadata_sha256": version.metadata_sha256,
    }
    return version.submitted_at, _RANK["VERSION_SUBMITTED"], version.version_number, entry


def _round_entry(correction_round) -> tuple[Any, ...]:
    closing = correction_round.closed_by_version
    entry = {
        "type": "ROUND_OPENED",
        "occurred_at": correction_round.opened_at,
        "round_number": correction_round.round_number,
        "closed_at": correction_round.closed_at,
        "closed_by_version_number": closing.version_number if closing else None,
    }
    return correction_round.opened_at, _RANK["ROUND_OPENED"], correction_round.round_number, entry


def build_history(manuscript: Manuscript) -> list[dict[str, Any]]:
    """The manuscript's timeline, oldest first."""
    rows = [_status_entry(e) for e in manuscript.status_events.all()]
    rows += [_version_entry(v) for v in manuscript.versions.all()]
    rows += [_round_entry(r) for r in manuscript.rounds.select_related("closed_by_version")]
    rows.sort(key=lambda row: row[:3])
    return [row[3] for row in rows]
