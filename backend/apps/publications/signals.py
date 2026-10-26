"""Domain events of the publications app.

They are sent AFTER the transaction commits, never inside it: a
receiver can fail or be slow without undoing the action it reacts to.
The notifications app subscribes to them (TSK-75); publications knows
nothing about who listens. Receivers get identifiers only and build
their own sanitized payloads.
"""

from django.dispatch import Signal

#: A formal submission created a version. Args: ``manuscript_id``,
#: ``version_id``, ``submitted_by_id``.
manuscript_submitted = Signal()

#: The author answered a correction request with a new version. Args:
#: ``manuscript_id``, ``version_id``, ``submitted_by_id``.
new_version_submitted = Signal()
