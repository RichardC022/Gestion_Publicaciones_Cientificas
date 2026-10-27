"""Receivers of other apps' events that act on assignments."""

from __future__ import annotations

from django.dispatch import receiver

from apps.publications.signals import manuscript_withdrawing
from apps.reviews.services.assignments import revoke_on_withdrawal


@receiver(manuscript_withdrawing, dispatch_uid="reviews-revoke-on-withdrawal")
def revoke_assignment_on_withdrawal(sender, manuscript_id, withdrawn_by_id, **kwargs) -> None:
    """Withdrawing a manuscript revokes its active assignment (plan section 4.8).

    The signal is sent with ``Signal.send`` inside the withdrawal's
    transaction, so a failure here aborts the whole withdrawal.
    """
    revoke_on_withdrawal(manuscript_id=manuscript_id, withdrawn_by_id=withdrawn_by_id)
