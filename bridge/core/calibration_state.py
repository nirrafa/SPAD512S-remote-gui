"""In-memory calibration state store.

Tracks per-calibration ``state`` (none/running/done/failed), the time it last
completed, and a ``stale`` flag. The store is per app instance; Phase 13 will
add persistence and real staleness rules (noise/dead-pixel calibration goes
stale after ~24h or when Vex changes). For the mock, ``stale`` is a simple flag
defaulting to ``False``.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from threading import Lock

CalibrationState = str  # "none" | "running" | "done" | "failed"

CALIBRATION_KINDS = ("breakdown", "noise", "dead_pixel", "master_slave_offset")


@dataclass
class CalibrationEntry:
    state: CalibrationState = "none"
    timestamp: float | None = None
    stale: bool = False

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {"state": self.state}
        if self.state == "done":
            payload["timestamp"] = self.timestamp
            payload["stale"] = self.stale
        return payload


class CalibrationStore:
    def __init__(self) -> None:
        self._lock = Lock()
        self._entries: dict[str, CalibrationEntry] = {
            kind: CalibrationEntry() for kind in CALIBRATION_KINDS
        }

    def mark_running(self, kind: str) -> None:
        with self._lock:
            self._entries[kind].state = "running"

    def mark_done(self, kind: str) -> None:
        with self._lock:
            entry = self._entries[kind]
            entry.state = "done"
            entry.timestamp = time.time()
            entry.stale = False

    def mark_failed(self, kind: str) -> None:
        with self._lock:
            self._entries[kind].state = "failed"

    def is_valid(self, kind: str) -> bool:
        with self._lock:
            entry = self._entries[kind]
            return entry.state == "done" and not entry.stale

    def snapshot(self) -> dict[str, dict[str, object]]:
        with self._lock:
            return {kind: entry.to_dict() for kind, entry in self._entries.items()}
