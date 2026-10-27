"""Domain events of the reviews app.

They are sent AFTER the transaction commits, never inside it: a
receiver can fail or be slow without undoing the assignment it reacts
to. The notifications app subscribes to them (TSK-75); reviews knows
nothing about who listens. Receivers get identifiers only and build
their own sanitized payloads: the free-text reason of a revocation is
left out on purpose, because it is written by the editor and must not
travel to the reviewer.
"""

from __future__ import annotations

import logging

from django.dispatch import Signal

logger = logging.getLogger(__name__)

#: A reviewer was assigned to a manuscript. Args: ``assignment_id``,
#: ``manuscript_id``, ``reviewer_id``, ``assigned_by_id``.
assignment_created = Signal()

#: An assignment was revoked, by an editor or by the withdrawal of the
#: manuscript. Args: ``assignment_id``, ``manuscript_id``, ``reviewer_id``,
#: ``cause``.
assignment_revoked = Signal()


#: The deadline of an assignment passed and the scheduled task marked it
#: ``EXPIRED``. It is sent once per assignment, because only an ``ACTIVE``
#: one can expire. The editor decides what follows; nothing is revoked or
#: reassigned automatically. Args: ``assignment_id``, ``manuscript_id``,
#: ``reviewer_id``, ``assigned_by_id``.
assignment_expired = Signal()


def announce(signal: Signal, **kwargs) -> None:
    """Send ``signal`` robustly: a failing receiver is logged, never raised."""
    for receiver, error in signal.send_robust(sender=None, **kwargs):
        if isinstance(error, Exception):
            logger.error("Un receptor de %s falló (%s): %s", signal, receiver, error)
