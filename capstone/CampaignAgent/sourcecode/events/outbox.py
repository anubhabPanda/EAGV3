"""A tiny idempotency outbox for capability side effects."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any, Awaitable, Callable

from sourcecode.core.live_graph import Deferred


class ActionOutbox:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    @staticmethod
    def key(run_id: str, node_id: str, capability: str, arguments: dict[str, Any]) -> str:
        body = json.dumps([run_id, node_id, capability, arguments], sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(body.encode()).hexdigest()

    def _path(self, key: str) -> Path:
        return self.root / f"{key}.json"

    def _write(self, key: str, value: dict[str, Any]) -> None:
        path = self._path(key)
        fd, temporary = tempfile.mkstemp(prefix=f".{key}-", suffix=".tmp", dir=self.root)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(value, stream, sort_keys=True, separators=(",", ":"))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    @staticmethod
    def _encode(value: dict[str, Any] | Deferred) -> dict[str, Any]:
        if isinstance(value, Deferred):
            return {"kind": "deferred", "handle": value.handle,
                    "event_type": value.event_type, "metadata": value.metadata}
        return {"kind": "result", "value": value}

    @staticmethod
    def _decode(value: dict[str, Any]) -> dict[str, Any] | Deferred:
        if value["kind"] == "deferred":
            return Deferred(value["handle"], value["event_type"], value.get("metadata", {}))
        return value["value"]

    async def execute(self, key: str,
                      operation: Callable[[], Awaitable[dict[str, Any] | Deferred]]) -> dict[str, Any] | Deferred:
        """Reuse a receipt; never blindly repeat an operation left in-flight by a crash."""
        with self._lock:
            path = self._path(key)
            if path.exists():
                record = json.loads(path.read_text(encoding="utf-8"))
                if record["status"] == "completed":
                    return self._decode(record["receipt"])
                if record["status"] == "started":
                    return Deferred(key, "outbox.reconcile", {"uncertain": True})
                if record["status"] == "failed":
                    raise RuntimeError(record["error"])
            self._write(key, {"status": "started"})
        try:
            result = await operation()
        except Exception as error:
            with self._lock:
                self._write(key, {"status": "failed", "error": f"{type(error).__name__}: {error}"})
            raise
        with self._lock:
            self._write(key, {"status": "completed", "receipt": self._encode(result)})
        return result
