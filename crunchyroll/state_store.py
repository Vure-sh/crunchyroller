"""
crunchyroll.state_store — atomic, crash-resilient persistence for DownloadQueue state.
Stores queue, active tasks, and history to <config_dir>/queue_state.json.
Uses background debounced writes outside queue locks to eliminate deadlock risk.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import logging
import os
import tempfile
import threading
import time
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

SCHEMA_VERSION: int = 1


@dataclass
class PersistedState:
    schema: int = SCHEMA_VERSION
    saved_at: float = field(default_factory=time.time)
    tasks: List[Dict[str, Any]] = field(default_factory=list)
    queue: List[Dict[str, Any]] = field(default_factory=list)
    history: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema": self.schema,
            "saved_at": self.saved_at,
            "tasks": self.tasks,
            "queue": self.queue,
            "history": self.history,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "PersistedState":
        return cls(
            schema=int(d.get("schema", SCHEMA_VERSION)),
            saved_at=float(d.get("saved_at", time.time())),
            tasks=list(d.get("tasks") or []),
            queue=list(d.get("queue") or []),
            history=list(d.get("history") or []),
        )


class StateStore:
    """Thread-safe, coalescing, debounced persistent store for queue state.

    Defaults to storing `queue_state.json` at the application project root.
    """

    def __init__(
        self,
        state_path: Optional[str] = None,
        debounce_s: float = 1.0,
    ) -> None:
        if state_path:
            self.state_path = os.path.abspath(state_path)
        else:
            from .auth import DATA_DIR
            self.state_path = os.path.join(DATA_DIR, "queue_state.json")

        self.debounce_s = max(0.05, float(debounce_s))
        self._lock = threading.Lock()
        self._pending_snapshot: Optional[Dict[str, Any]] = None
        self._save_event = threading.Event()
        self._stop_event = threading.Event()
        self._writer_thread: Optional[threading.Thread] = None
        self._start_writer()

    def _start_writer(self) -> None:
        self._writer_thread = threading.Thread(
            target=self._worker_loop,
            daemon=True,
            name="StateStoreWriter",
        )
        self._writer_thread.start()

    def load(self) -> PersistedState:
        """Load persisted state from disk. Missing file or bad JSON returns empty state safely."""
        with self._lock:
            target_path = self.state_path

        if not os.path.exists(target_path):
            return PersistedState()

        try:
            with open(target_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                logger.warning(f"Malformed state file at {target_path}; returning empty state")
                return PersistedState()
            return PersistedState.from_dict(data)
        except Exception as e:
            logger.warning(f"Failed to load queue state from {target_path}: {e}")
            return PersistedState()

    def schedule_save(self, snapshot_data: Dict[str, Any]) -> None:
        """
        Schedule a save operation. Overwrites any pending snapshot with the latest
        state so rapid mutations coalesce to a single write.
        """
        if self._stop_event.is_set():
            return
        with self._lock:
            self._pending_snapshot = snapshot_data
            self._save_event.set()

    def _write_to_disk(self, data: Dict[str, Any]) -> bool:
        target_dir = os.path.dirname(self.state_path) or "."
        os.makedirs(target_dir, exist_ok=True)

        tmp_file = None
        try:
            fd, tmp_path = tempfile.mkstemp(prefix="qstate_", suffix=".tmp", dir=target_dir)
            tmp_file = tmp_path
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
                f.flush()
                try:
                    os.fsync(f.fileno())
                except (OSError, AttributeError):
                    pass

            # Atomic replace
            os.replace(tmp_path, self.state_path)
            return True
        except Exception as e:
            logger.warning(f"Failed to save state to {self.state_path}: {e}")
            if tmp_file and os.path.exists(tmp_file):
                try:
                    os.remove(tmp_file)
                except Exception:
                    pass
            return False

    def save_sync(self, data: Dict[str, Any]) -> bool:
        """Synchronously write state atomically with fsync and clear pending debounced saves."""
        with self._lock:
            self._pending_snapshot = None
            return self._write_to_disk(data)

    def _worker_loop(self) -> None:
        while not self._stop_event.is_set():
            signaled = self._save_event.wait(timeout=self.debounce_s)
            if self._stop_event.is_set():
                break

            if signaled:
                time.sleep(self.debounce_s)
                self._save_event.clear()

            with self._lock:
                if self._pending_snapshot is None:
                    continue
                data = self._pending_snapshot
                self._pending_snapshot = None

            try:
                self._write_to_disk(data)
            except Exception as e:
                logger.debug(f"StateStore worker write error: {e}")

    def flush(self, timeout: float = 3.0) -> None:
        """Flush any pending snapshot immediately."""
        with self._lock:
            pending = self._pending_snapshot
            self._pending_snapshot = None
            self._save_event.clear()
        if pending:
            self._write_to_disk(pending)

    def close(self) -> None:
        """Stop background worker and flush remaining writes."""
        self.flush()
        self._stop_event.set()
        self._save_event.set()
        if self._writer_thread and self._writer_thread.is_alive():
            self._writer_thread.join(timeout=2.0)
