"""Checks of the cron template for the Phase 5 jobs (TSK-71).

Each job runs inside the ``backend`` container, with its own ``flock`` so
it never overlaps itself or the backup, and with the schedule the plan
fixes (section 5.8). The template is not in the backend image, so the
tests skip there.
"""

from __future__ import annotations

from pathlib import Path

import pytest

TEMPLATE = Path(__file__).resolve().parents[2] / "scripts" / "cron" / "gpc.cron"

#: command -> (schedule fields, lock file)
JOBS = {
    "send_pending_notifications": ("* * * * *", "gpc-notify.lock"),
    "cleanup_idempotency_keys": ("0 3 * * *", "gpc-cleanup.lock"),
    "verify_integrity": ("30 3 1 * *", "gpc-integrity.lock"),
}


def active_lines() -> list[str]:
    if not TEMPLATE.exists():
        pytest.skip("La plantilla de cron no está en la imagen del backend.")
    return [
        line
        for line in TEMPLATE.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    ]


@pytest.mark.parametrize("command", JOBS)
def test_job_is_scheduled_once_inside_backend_with_its_own_lock(command: str) -> None:
    schedule, lock = JOBS[command]
    lines = [line for line in active_lines() if f"manage.py {command}" in line]

    assert len(lines) == 1
    line = lines[0]
    assert line.startswith(f"{schedule} root ")
    assert f"flock -n /var/lock/{lock}" in line
    assert "docker compose exec -T backend python manage.py" in line


def test_jobs_do_not_share_a_lock() -> None:
    locks = [lock for _, lock in JOBS.values()]
    assert len(set(locks)) == len(locks)
    assert "gpc-backup.lock" not in locks
