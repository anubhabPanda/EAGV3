"""Atomic JSON history for events, subscriptions, refusals and liveness.

The event history is intentionally bounded by the scale of a teaching/laptop
harness. A production control plane can implement the same tiny interface over
Kafka or a database without changing the decision engine.

Three properties are worth reading before the code, because each one exists to
stop a specific failure this harness actually hits when it runs unattended:

**The index outlives the payload.** Deduplication is keyed on `(source, id)`, and
that key is kept in a small index even after the event body is compacted away.
An agent that forgets an event body has lost history; an agent that forgets an
event *id* will do the same work twice the next time the provider retries. The
cheap thing is the thing you must never drop.

**History is bounded and compaction is visible.** An hour of webhook traffic
against an append-only file that is fully rewritten per event is quadratic. The
history is capped, the oldest bodies are dropped first, and the store reports
what it dropped, because a silently truncated history reads exactly like a quiet
night.

**Refusals are recorded.** A control that prevents work leaves no trace of the
work it prevented. Every refusal the governor makes is stored here, so an
operator can tell "nothing happened" apart from "a great deal was stopped".

Single-writer only. The read-modify-write around `os.replace` is atomic per
write but is not safe across processes: run one worker, or move the interface
onto a real database.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .models import EventEnvelope, Subscription

DEFAULT_HISTORY_LIMIT = 5_000


def _key(source: str, event_id: str) -> str:
    return f"{source}|{event_id}"


class EventStore:
    def __init__(self, root: str | Path, *, history_limit: int | None = None) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "history.json"
        self._lock = threading.RLock()
        configured = os.getenv("S17_EVENT_HISTORY_MAX", "")
        self.history_limit = (history_limit if history_limit is not None
                              else int(configured) if configured.strip().isdigit()
                              else DEFAULT_HISTORY_LIMIT)
        if not self.path.exists():
            self._save(self._empty())
        else:
            with self._lock:
                self._save(self._migrate(self._load_raw()))

    # ------------------------------------------------------------- persistence

    @staticmethod
    def _empty() -> dict[str, Any]:
        return {"version": 2, "subscriptions": {}, "events": [], "next_sequence": 1,
                "index": {}, "windows": {}, "refusals": [], "compacted_before": 0,
                "liveness": {}}

    @staticmethod
    def _migrate(state: dict[str, Any]) -> dict[str, Any]:
        """A v1 history stays readable; its index is rebuilt from what is there."""
        state.setdefault("subscriptions", {})
        state.setdefault("events", [])
        state.setdefault("next_sequence", 1)
        state.setdefault("windows", {})
        state.setdefault("refusals", [])
        state.setdefault("compacted_before", 0)
        state.setdefault("liveness", {})
        if "index" not in state:
            state["index"] = {_key(record["event"]["source"], record["event"]["id"]): record["sequence"]
                              for record in state["events"]}
        state["version"] = 2
        return state

    def _load_raw(self) -> dict[str, Any]:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _load(self) -> dict[str, Any]:
        return self._load_raw()

    def _save(self, state: dict[str, Any]) -> None:
        fd, temporary = tempfile.mkstemp(prefix=".events-", suffix=".tmp", dir=self.root)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(state, stream, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def _compact(self, state: dict[str, Any]) -> None:
        """Drop the oldest event bodies, never their identities."""
        overflow = len(state["events"]) - self.history_limit
        if overflow <= 0:
            return
        dropped, state["events"] = state["events"][:overflow], state["events"][overflow:]
        state["compacted_before"] = dropped[-1]["sequence"] + 1
        # `index` deliberately keeps every (source, id) key: forgetting a body
        # loses history, forgetting an id repeats work.

    # ---------------------------------------------------------- subscriptions

    def put_subscription(self, subscription: Subscription) -> dict[str, Any]:
        with self._lock:
            state = self._load()
            state["subscriptions"][subscription.id] = subscription.model_dump(mode="json")
            self._save(state)
            return state["subscriptions"][subscription.id]

    def subscriptions(self) -> list[Subscription]:
        with self._lock:
            raw = self._load()["subscriptions"]
            return [Subscription.model_validate(raw[key]) for key in sorted(raw)]

    # ------------------------------------------------------------------ events

    def ingest(self, event: EventEnvelope) -> tuple[dict[str, Any], bool]:
        """Persist before deciding; source+id is the idempotency key."""
        with self._lock:
            state = self._load()
            key = _key(event.source, event.id)
            known = state["index"].get(key)
            if known is not None:
                existing = next((record for record in state["events"]
                                 if record["sequence"] == known), None)
                # The body may have been compacted away; the identity has not,
                # so this is still definitively a duplicate.
                return existing or {"sequence": known, "event": event.model_dump(mode="json"),
                                    "decisions": [], "compacted": True}, False
            record = {"sequence": state["next_sequence"], "event": event.model_dump(mode="json"),
                      "received_at": datetime.now(UTC).isoformat(), "decisions": []}
            state["index"][key] = record["sequence"]
            state["next_sequence"] += 1
            state["events"].append(record)
            self._compact(state)
            self._save(state)
            return record, True

    def add_decision(self, source: str, event_id: str, decision: dict[str, Any]) -> None:
        with self._lock:
            state = self._load()
            record = next((item for item in state["events"]
                           if item["event"]["source"] == source and item["event"]["id"] == event_id), None)
            if record is None:
                # Compacted or unknown: keep the decision visible rather than
                # dropping it silently, which is what the old `next()` did.
                state["refusals"].append({"at": datetime.now(UTC).isoformat(),
                                          "control": "orphan_decision", "source": source,
                                          "event_id": event_id, "decision": decision})
                self._save(state)
                return
            if any(item.get("subscription_id") == decision.get("subscription_id")
                   for item in record["decisions"]):
                return
            record["decisions"].append(decision)
            self._save(state)

    def events(self, *, after: int = 0, limit: int | None = None) -> list[dict[str, Any]]:
        with self._lock:
            found = [record for record in self._load()["events"] if record["sequence"] > after]
            return found[:limit] if limit else found

    def count_recent_events(self, source: str, *, since: datetime) -> int:
        """Arrivals from one source inside a window, for the rate limiter."""
        with self._lock:
            total = 0
            for record in reversed(self._load()["events"]):
                if record["event"]["source"] != source:
                    continue
                received = record.get("received_at")
                if not received:
                    continue
                try:
                    moment = datetime.fromisoformat(received)
                except ValueError:
                    continue
                if moment < since:
                    break
                total += 1
            return total

    # ---------------------------------------------------------- window ledger

    def window_record(self, subscription_id: str, day: str, *, kind: str, usd: float = 0.0,
                      count: int = 1) -> None:
        with self._lock:
            state = self._load()
            bucket = state["windows"].setdefault(f"{subscription_id}|{day}", {})
            entry = bucket.setdefault(kind, {"count": 0, "usd": 0.0})
            entry["count"] += count
            entry["usd"] = round(entry["usd"] + max(0.0, float(usd)), 12)
            self._save(state)

    def window_reserve(self, subscription_id: str, day: str, *, kind: str,
                       limit: int | None) -> tuple[bool, int]:
        """Claim one slot in the window, atomically. Returns (reserved, count).

        Reading a count and incrementing it later is not a ceiling when the two
        halves are separated by an `await`: several concurrent deciders all read
        the same pre-run number, all conclude there is room, and all proceed. The
        increment has to happen in the same critical section as the check, which
        is what this does. `limit=None` means "no ceiling": the slot is still
        claimed, so an operator's snapshot stays truthful either way.

        A reserved slot is not released if the run then fails. That is
        deliberate: a run that started and blew up still consumed the agent's
        attention and possibly money, and the conservative direction for a
        ceiling is to count it.
        """
        with self._lock:
            state = self._load()
            bucket = state["windows"].setdefault(f"{subscription_id}|{day}", {})
            entry = bucket.setdefault(kind, {"count": 0, "usd": 0.0})
            current = int(entry["count"])
            if limit is not None and current >= limit:
                return False, current
            entry["count"] = current + 1
            self._save(state)
            return True, current + 1

    def window_count(self, subscription_id: str, day: str, *, kind: str) -> int:
        with self._lock:
            bucket = self._load()["windows"].get(f"{subscription_id}|{day}", {})
            return int(bucket.get(kind, {}).get("count", 0))

    def window_spend(self, subscription_id: str, day: str, *, kind: str) -> float:
        with self._lock:
            bucket = self._load()["windows"].get(f"{subscription_id}|{day}", {})
            return float(bucket.get(kind, {}).get("usd", 0.0))

    # --------------------------------------------------------------- refusals

    def record_refusal(self, *, control: str, reason: str, event: dict[str, Any] | None = None,
                       subscription_id: str | None = None, detail: dict[str, Any] | None = None) -> None:
        """The safest behaviour must not also be the least observable one."""
        with self._lock:
            state = self._load()
            state["refusals"].append({
                "at": datetime.now(UTC).isoformat(), "control": control, "reason": reason,
                "subscription_id": subscription_id,
                "event": {"source": event.get("source"), "id": event.get("id"), "type": event.get("type")}
                if event else None,
                "detail": detail or {},
            })
            state["refusals"] = state["refusals"][-self.history_limit:]
            self._save(state)

    def refusals(self, *, since: datetime | None = None) -> list[dict[str, Any]]:
        with self._lock:
            found = self._load()["refusals"]
            if since is None:
                return list(found)
            return [item for item in found
                    if item.get("at") and datetime.fromisoformat(item["at"]) >= since]

    # --------------------------------------------------------------- liveness

    def beat(self, *, note: str = "") -> dict[str, Any]:
        with self._lock:
            state = self._load()
            liveness = state["liveness"]
            now = datetime.now(UTC).isoformat()
            liveness.setdefault("started_at", now)
            liveness["last_beat"] = now
            liveness["beats"] = int(liveness.get("beats", 0)) + 1
            if note:
                liveness["note"] = note[:500]
            self._save(state)
            return dict(liveness)

    def liveness(self) -> dict[str, Any]:
        with self._lock:
            state = self._load()
            return {**state["liveness"], "compacted_before": state.get("compacted_before", 0),
                    "events_retained": len(state["events"]),
                    "ids_remembered": len(state["index"])}
