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

#: The author is withdrawing a manuscript. Sent INSIDE the transaction with
#: ``Signal.send`` — not ``send_robust`` — so a receiver that fails aborts the
#: withdrawal atomically. It is where the reviews app revokes the active
#: assignment and the catalog deactivates its entry (plan section 4.8, steps
#: 4 and 5) without ``publications`` importing them. Args: ``manuscript_id``,
#: ``withdrawn_by_id``, ``previous_status``, ``withdrawn_at``.
manuscript_withdrawing = Signal()

#: The withdrawal is committed. Sent after the commit: notices to the reviewer
#: and the editor, and removal of the public copy. Args: ``manuscript_id``,
#: ``withdrawn_by_id``, ``previous_status``. The reason is left out on purpose:
#: it is free text written by the author and must not travel to the reviewer.
manuscript_withdrawn = Signal()
