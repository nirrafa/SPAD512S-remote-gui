"""SQLite-backed sweep checkpoints.

Each completed sweep point is recorded so an interrupted sweep (bridge crash,
vendor failure) can resume and skip finished points. Writes are tiny (one row
per point), so plain synchronous sqlite3 from the event loop is acceptable. The
DB lives under ``settings.data_root`` so tests (which route data_root to a tmp
dir) get an isolated store.
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sweeps (
    sweep_id TEXT PRIMARY KEY,
    created_at REAL NOT NULL,
    spec TEXT NOT NULL,
    status TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sweep_points (
    sweep_id TEXT NOT NULL,
    point_index INTEGER NOT NULL,
    label TEXT NOT NULL,
    value TEXT NOT NULL,
    host_path TEXT,
    completed_at REAL NOT NULL,
    PRIMARY KEY (sweep_id, point_index)
);
"""


class CheckpointStore:
    """Persistence for sweep progress.

    ``spec`` carries everything needed to resume a sweep without the original
    HTTP body: mode, the resolved list of points (index/label/value/params), and
    the total count.
    """

    def __init__(self, db_path: str | Path) -> None:
        self._path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path)

    def create_sweep(self, spec: dict[str, Any]) -> str:
        sweep_id = uuid.uuid4().hex[:12]
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO sweeps (sweep_id, created_at, spec, status) VALUES (?, ?, ?, ?)",
                (sweep_id, time.time(), json.dumps(spec), "running"),
            )
        return sweep_id

    def set_status(self, sweep_id: str, status: str) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE sweeps SET status = ? WHERE sweep_id = ?", (status, sweep_id))

    def record_point(
        self,
        sweep_id: str,
        point_index: int,
        label: str,
        value: Any,
        host_path: str | None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO sweep_points "
                "(sweep_id, point_index, label, value, host_path, completed_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (sweep_id, point_index, label, json.dumps(value), host_path, time.time()),
            )

    def completed_indices(self, sweep_id: str) -> set[int]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT point_index FROM sweep_points WHERE sweep_id = ?", (sweep_id,)
            ).fetchall()
        return {int(row[0]) for row in rows}

    def completed_points(self, sweep_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT point_index, label, value, host_path FROM sweep_points "
                "WHERE sweep_id = ? ORDER BY point_index",
                (sweep_id,),
            ).fetchall()
        return [
            {
                "index": int(row[0]),
                "label": row[1],
                "value": json.loads(row[2]),
                "host_path": row[3],
            }
            for row in rows
        ]

    def count_points(self, sweep_id: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM sweep_points WHERE sweep_id = ?", (sweep_id,)
            ).fetchone()
        return int(row[0]) if row else 0

    def latest_incomplete(self) -> tuple[str, dict[str, Any]] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT sweep_id, spec FROM sweeps WHERE status != 'done' "
                "ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
        if row is None:
            return None
        return str(row[0]), dict(json.loads(row[1]))
