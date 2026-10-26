"""Idempotent ``POST`` operations (plan section 2.11).

A client-chosen ``Idempotency-Key`` makes a retry safe:

* the SAME key with the SAME request returns the stored answer and
  repeats no effect;
* the same key with a DIFFERENT request is a ``409``;
* a key expires 24 hours after it was stored and is then forgotten.

A key is scoped to the user and to the method and path of the request,
and the request is identified by a hash of what makes it unique (for
instance the manuscript and the SHA-256 of the uploaded PDF).

The answer is stored INSIDE the transaction of the operation, so both
commit or roll back together: a crash can never leave the effect done
without its key. A transaction-scoped advisory lock per
``(user, endpoint, key)`` serializes duplicates: a retry that arrives
while the first request is still running waits for it and then replays
its answer instead of failing on the state the first one produced.

Only successful answers are stored. A failure (validation, conflict,
storage, audit) rolls everything back, so the key is not consumed and
the client can retry with the same key once the cause is fixed.

``delete_expired_keys`` is what the daily cleanup command calls
(TSK-76).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from django.db import connection
from django.utils import timezone

from apps.publications.models import IdempotencyKey
from apps.users.models import User
from config.exceptions import DomainError, ErrorCode

#: How long a stored answer can be replayed (plan section 2.11).
IDEMPOTENCY_TTL = timedelta(hours=24)

KEY_REUSED_MESSAGE = (
    "La clave de idempotencia ya se usó con una solicitud distinta; use una clave nueva."
)


@dataclass(frozen=True)
class StoredResponse:
    """Status and body that were answered the first time."""

    status: int
    body: Any


class IdempotentReplay(Exception):
    """Raised inside the transaction to leave it and answer with the stored response."""

    def __init__(self, stored: StoredResponse) -> None:
        super().__init__("idempotent replay")
        self.stored = stored


def request_hash(*parts: Any) -> str:
    """Hex SHA-256 over the canonical JSON of the parts that identify a request."""
    canonical = json.dumps(parts, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class IdempotencyScope:
    """One ``(user, endpoint, key)`` and the request it is bound to.

    ``request_hash`` is a callable so the hash is only computed when a
    stored key actually has to be compared (hashing a 50 MB upload costs
    time). ``render`` turns the operation's result into the
    ``(status, body)`` pair to store and answer.
    """

    def __init__(
        self,
        *,
        user: User,
        endpoint: str,
        key: str,
        request_hash: Callable[[], str],
        render: Callable[[Any], tuple[int, Any]],
    ) -> None:
        self.user = user
        self.endpoint = endpoint
        self.key = key
        self._request_hash = request_hash
        self.render = render

    def _row_filter(self):
        return IdempotencyKey.objects.filter(user=self.user, endpoint=self.endpoint, key=self.key)

    def _replay(self, row: IdempotencyKey) -> StoredResponse:
        if row.request_hash != self._request_hash():
            raise DomainError(
                KEY_REUSED_MESSAGE,
                code=ErrorCode.STATE_CONFLICT,
                details={"idempotency": "KEY_REUSED_WITH_DIFFERENT_REQUEST"},
            )
        return StoredResponse(status=row.response_status, body=row.response_body)

    def find(self) -> StoredResponse | None:
        """Stored answer of a live key, or ``None``; read-only, no lock."""
        row = self._row_filter().filter(expires_at__gt=timezone.now()).first()
        return self._replay(row) if row else None

    def lock_and_find(self) -> StoredResponse | None:
        """Serialize duplicates, then look the key up. Call inside the transaction."""
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_advisory_xact_lock(hashtext(%s))",
                [f"idempotency:{self.user.pk}:{self.endpoint}:{self.key}"],
            )
        row = self._row_filter().first()
        if row is None:
            return None
        if row.expires_at <= timezone.now():
            # Vencida: se olvida, y la solicitud se trata como nueva.
            row.delete()
            return None
        return self._replay(row)

    def store_result(self, result: Any) -> None:
        """Store the answer of a successful operation. Call inside the transaction."""
        status, body = self.render(result)
        now = timezone.now()
        IdempotencyKey.objects.create(
            user=self.user,
            endpoint=self.endpoint,
            key=self.key,
            request_hash=self._request_hash(),
            response_status=status,
            response_body=body,
            expires_at=now + IDEMPOTENCY_TTL,
        )


def delete_expired_keys(now=None) -> int:
    """Remove the keys that expired; live keys are never touched. Returns how many."""
    deleted, _ = IdempotencyKey.objects.filter(expires_at__lte=now or timezone.now()).delete()
    return deleted
