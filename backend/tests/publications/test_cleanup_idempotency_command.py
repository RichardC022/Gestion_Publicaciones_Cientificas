"""Tests for the ``cleanup_idempotency_keys`` command (TSK-76).

Acceptance criterion: the cleanup removes the expired keys and never
touches the live ones.
"""

from __future__ import annotations

from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.publications.models import IdempotencyKey
from tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def make_key(user, key: str, *, expires_in: timedelta) -> IdempotencyKey:
    return IdempotencyKey.objects.create(
        user=user,
        endpoint="POST /api/manuscripts/x/submit/",
        key=key,
        request_hash="b" * 64,
        response_status=200,
        response_body={"ok": True},
        expires_at=timezone.now() + expires_in,
    )


def run() -> str:
    out = StringIO()
    call_command("cleanup_idempotency_keys", stdout=out)
    return out.getvalue()


def test_expired_keys_are_deleted_and_live_ones_stay() -> None:
    user = UserFactory()
    make_key(user, "old-1", expires_in=timedelta(hours=-1))
    make_key(user, "old-2", expires_in=timedelta(days=-3))
    live = make_key(user, "live", expires_in=timedelta(hours=23))

    assert "eliminadas: 2" in run()

    assert list(IdempotencyKey.objects.all()) == [live]


def test_nothing_to_delete_is_silent_and_harmless() -> None:
    live = make_key(UserFactory(), "live", expires_in=timedelta(minutes=1))

    assert run() == ""

    assert IdempotencyKey.objects.filter(pk=live.pk).exists()


def test_running_twice_deletes_nothing_more() -> None:
    make_key(UserFactory(), "old", expires_in=timedelta(hours=-1))
    run()

    assert run() == ""
