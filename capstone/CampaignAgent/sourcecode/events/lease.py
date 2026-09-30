"""A lease, so a periodic trigger cannot overlap itself.

Cron is the only source with no event in it. It says "look again", and the agent
manufactures the fact by diffing state. That makes it the source with the
subtlest failure: the 09:00 run takes eleven minutes, the 09:05 tick fires into a
system already doing the same job, and two runs race over one piece of state.

The fix is unglamorous. Take a lease before the work, release it after, and let a
tick that cannot take the lease record a **skip**. A skipped tick is a decision
and belongs in the history like any other, because "I did not run because I was
already running" and "I did not run because the process was dead" are different
facts that a silent skip makes identical.

Two details matter more than the mechanism:

* The lease **expires**. A holder that crashes must not lock the schedule
  forever, so the lease carries a deadline and a later tick may steal an expired
  one — recording that it did.
* The lease is **keyed by schedule**, not by process. Restarting the service does
  not grant it a fresh right to run something that is still in flight elsewhere.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class LeaseVerdict:
    granted: bool
    token: str = ""
    reason: str = ""
    holder: str = ""
    expires_at: str = ""

    def as_record(self) -> dict[str, Any]:
        return {"granted": self.granted, "reason": self.reason,
                "holder": self.holder, "expires_at": self.expires_at}


class ScheduleLease:
    """One durable lease per schedule id."""

    def __init__(self, root: str | Path, *, ttl_seconds: int | None = None) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        configured = os.getenv("S17_LEASE_TTL_SECONDS", "")
        self.ttl = (ttl_seconds if ttl_seconds is not None
                    else int(configured) if configured.strip().isdigit() else 900)

    def _path(self, schedule_id: str) -> Path:
        safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in schedule_id)
        return self.root / f"lease-{safe}.json"

    def _write(self, path: Path, value: dict[str, Any]) -> None:
        fd, temporary = tempfile.mkstemp(prefix=".lease-", suffix=".tmp", dir=self.root)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(value, stream, sort_keys=True, separators=(",", ":"))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def acquire(self, schedule_id: str, *, holder: str = "", now: datetime | None = None) -> LeaseVerdict:
        moment = now or datetime.now(UTC)
        with self._lock:
            path = self._path(schedule_id)
            if path.exists():
                try:
                    held = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    held = None
                if held:
                    expires = datetime.fromisoformat(held["expires_at"])
                    if expires > moment:
                        return LeaseVerdict(
                            False,
                            reason=(f"schedule {schedule_id!r} is still running; "
                                    f"held by {held.get('holder') or 'an earlier tick'} "
                                    f"until {held['expires_at']}"),
                            holder=str(held.get("holder", "")),
                            expires_at=str(held["expires_at"]),
                        )
                    # Expired: the previous holder died mid-work. Steal it, but
                    # say so, because a stolen lease means an interrupted run.
                    token = uuid.uuid4().hex[:16]
                    self._write(path, {"token": token, "holder": holder,
                                       "acquired_at": moment.isoformat(),
                                       "expires_at": (moment + timedelta(seconds=self.ttl)).isoformat(),
                                       "stolen_from": held.get("holder", ""),
                                       "stolen_expired_at": held["expires_at"]})
                    return LeaseVerdict(True, token=token,
                                        reason=f"took over an expired lease from {held.get('holder') or 'an earlier tick'}")
            token = uuid.uuid4().hex[:16]
            self._write(path, {"token": token, "holder": holder,
                               "acquired_at": moment.isoformat(),
                               "expires_at": (moment + timedelta(seconds=self.ttl)).isoformat()})
            return LeaseVerdict(True, token=token)

    def release(self, schedule_id: str, token: str) -> bool:
        """Only the holder may release. A stale token releases nothing."""
        with self._lock:
            path = self._path(schedule_id)
            if not path.exists():
                return False
            try:
                held = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return False
            if held.get("token") != token:
                return False
            path.unlink()
            return True

    def state(self, schedule_id: str) -> dict[str, Any] | None:
        with self._lock:
            path = self._path(schedule_id)
            if not path.exists():
                return None
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return None
