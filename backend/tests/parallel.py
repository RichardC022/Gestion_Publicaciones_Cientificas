"""Run requests or service calls at the same time for the concurrency tests.

Each task runs in its own thread, therefore with its own database
connection, and all are released together by a barrier. The tests that
use it must be marked ``django_db(transaction=True)``: threads only see
committed rows.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import TypeVar

from django.db import connection
from rest_framework.test import APIClient

T = TypeVar("T")


def api_task(user, call: Callable[[APIClient], T]) -> Callable[[], T]:
    """A task that calls the API authenticated as ``user``."""

    def task() -> T:
        client = APIClient(raise_request_exception=False)
        client.force_authenticate(user)
        return call(client)

    return task


def run_parallel(tasks: Sequence[Callable[[], T]]) -> list[T]:
    """Run every task at once; results keep the order of ``tasks``."""
    barrier = threading.Barrier(len(tasks))

    def run(task: Callable[[], T]) -> T:
        try:
            barrier.wait(timeout=15)
            return task()
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=len(tasks)) as pool:
        return list(pool.map(run, tasks))


def statuses(responses) -> list[int]:
    """Sorted HTTP statuses of the responses."""
    return sorted(response.status_code for response in responses)
