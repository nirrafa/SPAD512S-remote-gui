"""SQLite-backed experiment log + named presets.

Every acquisition (single-shot, scheduled, and — via the route layer —
re-runs) is recorded so a run can be reproduced later: parameters, result
path, the calibration state and temperatures at capture time, and free-text
sample/experiment/notes. Named presets store a reusable parameter set per mode.

The DB lives under ``settings.data_root`` (lazy-initialised like
:class:`~bridge.core.checkpoint.CheckpointStore`, so a bridge that never
acquires writes nothing). Writes are tiny, so synchronous ``sqlite3`` from the
event loop is acceptable.
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS experiments (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT UNIQUE NOT NULL,
    created_at REAL NOT NULL,
    mode TEXT NOT NULL,
    params TEXT NOT NULL,
    result_path TEXT,
    calibration_state TEXT,
    temperatures TEXT,
    sample_name TEXT,
    experiment_name TEXT,
    notes TEXT,
    scheduled INTEGER NOT NULL DEFAULT 0,
    job_id TEXT,
    state TEXT
);
CREATE TABLE IF NOT EXISTS presets (
    id TEXT PRIMARY KEY,
    created_at REAL NOT NULL,
    name TEXT NOT NULL,
    mode TEXT NOT NULL,
    params TEXT NOT NULL
);
"""

_UPDATABLE = {"state", "result_path", "mode", "notes"}


def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, tz=UTC).isoformat()


class ExperimentLog:
    def __init__(self, db_path: str | Path) -> None:
        self._path = Path(db_path)
        self._initialized = False

    def _connect(self) -> sqlite3.Connection:
        if not self._initialized:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(self._path) as conn:
                conn.executescript(_SCHEMA)
            self._initialized = True
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        return conn

    # --- writes ---------------------------------------------------------------

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
        """Append a bare entry (used by the scheduler for queued jobs)."""
        return self._insert(
            mode=mode,
            params=params,
            result_path=result_path,
            calibration_state={},
            temperatures={},
            sample_name=None,
            experiment_name=None,
            notes=None,
            scheduled=scheduled,
            job_id=job_id,
            state=state,
        )

    def log_acquisition(
        self,
        *,
        mode: str,
        params: dict[str, Any],
        result_path: str | None,
        calibration_state: dict[str, Any],
        temperatures: dict[str, Any],
        sample_name: str | None = None,
        experiment_name: str | None = None,
        notes: str | None = None,
        state: str = "completed",
    ) -> dict[str, Any]:
        return self._insert(
            mode=mode,
            params=params,
            result_path=result_path,
            calibration_state=calibration_state,
            temperatures=temperatures,
            sample_name=sample_name,
            experiment_name=experiment_name,
            notes=notes,
            scheduled=False,
            job_id=None,
            state=state,
        )

    def _insert(
        self,
        *,
        mode: str,
        params: dict[str, Any],
        result_path: str | None,
        calibration_state: dict[str, Any],
        temperatures: dict[str, Any],
        sample_name: str | None,
        experiment_name: str | None,
        notes: str | None,
        scheduled: bool,
        job_id: str | None,
        state: str | None,
    ) -> dict[str, Any]:
        entry_id = uuid.uuid4().hex[:12]
        created_at = time.time()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO experiments (id, created_at, mode, params, result_path, "
                "calibration_state, temperatures, sample_name, experiment_name, notes, "
                "scheduled, job_id, state) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    entry_id,
                    created_at,
                    mode,
                    json.dumps(params),
                    result_path,
                    json.dumps(calibration_state),
                    json.dumps(temperatures),
                    sample_name,
                    experiment_name,
                    notes,
                    1 if scheduled else 0,
                    job_id,
                    state,
                ),
            )
        return self.get(entry_id) or {}

    def update(self, job_id: str, **fields: Any) -> None:
        sets = {k: v for k, v in fields.items() if k in _UPDATABLE}
        if not sets:
            return
        assignments = ", ".join(f"{col} = ?" for col in sets)
        with self._connect() as conn:
            conn.execute(
                f"UPDATE experiments SET {assignments} WHERE job_id = ?",
                (*sets.values(), job_id),
            )

    # --- reads ----------------------------------------------------------------

    def entries(
        self, *, search: str | None = None, limit: int | None = None, offset: int = 0
    ) -> list[dict[str, Any]]:
        """Chronological (oldest first, newest last) list of log entries.

        ``search`` matches sample/experiment name and notes (case-insensitive
        substring). ``limit``/``offset`` page the result.
        """
        query = "SELECT * FROM experiments"
        args: list[Any] = []
        if search:
            like = f"%{search}%"
            query += (
                " WHERE sample_name LIKE ? OR experiment_name LIKE ? OR notes LIKE ?"
            )
            args += [like, like, like]
        query += " ORDER BY seq ASC"
        if limit is not None:
            query += " LIMIT ? OFFSET ?"
            args += [limit, offset]
        with self._connect() as conn:
            rows = conn.execute(query, args).fetchall()
        return [self._row_to_entry(row) for row in rows]

    def get(self, entry_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM experiments WHERE id = ?", (entry_id,)
            ).fetchone()
        return self._row_to_entry(row) if row is not None else None

    @staticmethod
    def _row_to_entry(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "mode": row["mode"],
            "params": json.loads(row["params"]),
            "result_path": row["result_path"],
            "calibration_state": json.loads(row["calibration_state"] or "{}"),
            "temperatures": json.loads(row["temperatures"] or "{}"),
            "sample_name": row["sample_name"],
            "experiment_name": row["experiment_name"],
            "notes": row["notes"],
            "scheduled": bool(row["scheduled"]),
            "job_id": row["job_id"],
            "state": row["state"],
            "created_at": row["created_at"],
            "timestamp": _iso(row["created_at"]),
        }

    # --- presets --------------------------------------------------------------

    def save_preset(self, *, name: str, mode: str, params: dict[str, Any]) -> str:
        preset_id = uuid.uuid4().hex[:12]
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO presets (id, created_at, name, mode, params) VALUES (?,?,?,?,?)",
                (preset_id, time.time(), name, mode, json.dumps(params)),
            )
        return preset_id

    def list_presets(self, mode: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM presets"
        args: list[Any] = []
        if mode:
            query += " WHERE mode = ?"
            args.append(mode)
        query += " ORDER BY created_at ASC"
        with self._connect() as conn:
            rows = conn.execute(query, args).fetchall()
        return [self._preset_row(row) for row in rows]

    def get_preset(self, preset_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM presets WHERE id = ?", (preset_id,)).fetchone()
        return self._preset_row(row) if row is not None else None

    def delete_preset(self, preset_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM presets WHERE id = ?", (preset_id,))
            return cur.rowcount > 0

    @staticmethod
    def _preset_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "name": row["name"],
            "mode": row["mode"],
            "params": json.loads(row["params"]),
            "created_at": row["created_at"],
        }
