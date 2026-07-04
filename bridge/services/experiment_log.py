"""Minimal in-memory experiment log.

Phase 12 replaces this with the full SQLite-backed log + presets. Phase 9 only
needs scheduled jobs to be visible in ``GET /api/experiment-log`` (each entry
carries a ``scheduled`` flag), so this keeps a lightweight append-only list.
"""
from __future__ import annotations

import time
import uuid
from typing import Any


class ExperimentLog:
    def __init__(self) -> None:
        self._entries: list[dict[str, Any]] = []

    def add(
        self,
        *,
        mode: str,
        params: dict[str, Any],
        scheduled: bool = False,
        job_id: str | None = None,
        state: str | None = None,
        result_path: str | None = None,
    ) -> dict[str, Any]:
        entry: dict[str, Any] = {
            "id": uuid.uuid4().hex[:12],
            "mode": mode,
            "params": params,
            "scheduled": scheduled,
            "job_id": job_id,
            "state": state,
            "result_path": result_path,
            "created_at": time.time(),
        }
        self._entries.append(entry)
        return entry

    def update(self, job_id: str, **fields: Any) -> None:
        for entry in self._entries:
            if entry.get("job_id") == job_id:
                entry.update(fields)
                return

    def entries(self) -> list[dict[str, Any]]:
        return list(self._entries)
