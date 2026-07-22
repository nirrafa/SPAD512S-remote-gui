"""Dark-count (DCR) reference: build, store, and apply per-pixel correction.

DCR on the SPAD512² is heat-driven and timing-dependent, so a dark reference is
only physically meaningful for the *exact* acquisition configuration it was
measured with. The reference is a per-pixel map built from a covered-sensor
acquisition: the acquisition's ``iterations`` serve as the repeat axis (median
when >= 3 repeats, mean otherwise), and the stored map is **per-iteration**, so
it applies to a signal acquisition with any iteration count — everything else
in the fingerprint must match exactly.

Two modes share the same math: a gated reference is ``(gate_steps, H, W)``;
an intensity reference is the degenerate ``gate_steps = 1`` case, ``(1, H, W)``.
Fingerprints are mode-specific dicts with disjoint key sets, so a gated
reference can never accidentally match an intensity acquisition (and the store
also records ``mode`` explicitly for listing/filtering).

Correction is ``clip(signal - reference, 0)`` — counts cannot go negative.
The raw acquisition data persisted to disk is never modified; correction is
applied only to the derived views (previews / response stack).

Storage follows the existing ``CheckpointStore``/``ExperimentLog`` pattern:
lazy-initialised SQLite metadata under ``data_root``, with the array itself in
an adjacent ``.npy`` file.
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    from bridge.core.acquisition import GatedParams, IntensityParams

_SCHEMA = """
CREATE TABLE IF NOT EXISTS dark_references (
    id TEXT PRIMARY KEY,
    created_at REAL NOT NULL,
    mode TEXT NOT NULL DEFAULT 'gated',
    fingerprint TEXT NOT NULL,
    iterations INTEGER NOT NULL,
    gate_steps INTEGER NOT NULL,
    npy_path TEXT NOT NULL,
    source_path TEXT
);
"""

MIN_MEDIAN_REPEATS = 3


def gated_fingerprint(params: GatedParams) -> dict[str, Any]:
    """The gate configuration a gated dark reference is only valid for.

    ``iterations`` is deliberately excluded — the stored reference is
    per-iteration, so it broadcasts over any signal iteration count. Everything
    that shapes per-gate counts (timing, bit depth, integration time, pileup)
    must match exactly.
    """
    return {
        "bit_depth": params.bit_depth,
        "integration_time": params.integration_time,
        "gate_steps": params.effective_steps,
        "gate_step_size": params.gate_step_size,
        "gate_offset": params.gate_offset,
        "gate_width": params.gate_width,
        "gate_direction": params.gate_direction,
        "gate_trigger_source": params.gate_trigger_source,
        "overlap": params.overlap,
        "pileup_correction": params.pileup_correction,
        "arbitrary_steps": list(params.arbitrary_steps) if params.arbitrary_steps else None,
    }


def intensity_fingerprint(params: IntensityParams) -> dict[str, Any]:
    """The intensity configuration an intensity dark reference is valid for.

    Same ``iterations`` exclusion as :func:`gated_fingerprint`. The
    ``roi_width`` key (absent from gated fingerprints, which are always full
    width) also guarantees the two fingerprint shapes can never collide.
    """
    return {
        "bit_depth": params.bit_depth,
        "integration_time": params.integration_time,
        "roi_width": params.roi_width,
        "overlap": params.overlap,
        "pileup_correction": params.pileup_correction,
    }


def build_reference(stack: np.ndarray, *, iterations: int, gate_steps: int) -> np.ndarray:
    """Reduce a dark ``(iterations*gate_steps, H, W)`` stack to a per-iteration
    ``(gate_steps, H, W)`` float32 reference.

    Median across the iteration axis when there are enough repeats for it to be
    meaningful (robust to afterpulsing/hot-pixel bursts), mean otherwise. Frame
    ordering follows the existing decode/preview convention: the first
    ``gate_steps`` frames are one complete sweep (iteration-major).
    """
    expected = iterations * gate_steps
    if stack.shape[0] != expected:
        raise ValueError(
            f"dark stack has {stack.shape[0]} frames, expected {expected} "
            f"({iterations} iterations x {gate_steps} steps)"
        )
    per_iteration = stack.reshape(iterations, gate_steps, *stack.shape[1:]).astype(np.float32)
    if iterations >= MIN_MEDIAN_REPEATS:
        return np.asarray(np.median(per_iteration, axis=0))
    return np.asarray(per_iteration.mean(axis=0))


def apply_dark_correction(stack: np.ndarray, reference: np.ndarray) -> np.ndarray:
    """Subtract the per-iteration reference from a ``(N*gate_steps, H, W)``
    signal stack, clipped at zero, preserving the input dtype.

    The subtraction runs in float (the input is unsigned — a negative
    intermediate would wrap), then rounds back.
    """
    gate_steps = reference.shape[0]
    if stack.shape[0] % gate_steps != 0:
        raise ValueError(
            f"signal stack ({stack.shape[0]} frames) is not a whole number of "
            f"{gate_steps}-step sweeps"
        )
    if stack.shape[1:] != reference.shape[1:]:
        raise ValueError(
            f"signal frame shape {stack.shape[1:]} != reference {reference.shape[1:]}"
        )
    iterations = stack.shape[0] // gate_steps
    shaped = stack.reshape(iterations, gate_steps, *stack.shape[1:]).astype(np.float64)
    corrected = np.clip(shaped - reference[None, :, :, :], 0.0, None)
    return np.asarray(np.rint(corrected).reshape(stack.shape).astype(stack.dtype))


class DarkReferenceStore:
    def __init__(self, db_path: str | Path) -> None:
        self._path = Path(db_path)
        self._npy_dir = self._path.parent / "dark_references"
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

    def save(
        self,
        *,
        mode: str,
        fingerprint: dict[str, Any],
        reference: np.ndarray,
        iterations: int,
        source_path: str | None = None,
    ) -> str:
        """Store a reference; ``source_path`` links back to the persisted raw
        dark acquisition folder it was built from (the lab record)."""
        ref_id = uuid.uuid4().hex[:12]
        self._npy_dir.mkdir(parents=True, exist_ok=True)
        npy_path = self._npy_dir / f"darkref_{ref_id}.npy"
        np.save(npy_path, reference)
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO dark_references "
                "(id, created_at, mode, fingerprint, iterations, gate_steps, npy_path, source_path) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (
                    ref_id,
                    time.time(),
                    mode,
                    json.dumps(fingerprint, sort_keys=True),
                    iterations,
                    int(reference.shape[0]),
                    str(npy_path),
                    source_path,
                ),
            )
        return ref_id

    def get(self, ref_id: str) -> tuple[dict[str, Any], np.ndarray] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT fingerprint, npy_path FROM dark_references WHERE id = ?",
                (ref_id,),
            ).fetchone()
        if row is None:
            return None
        npy_path = Path(row["npy_path"])
        if not npy_path.exists():
            return None
        return dict(json.loads(row["fingerprint"])), np.load(npy_path)

    def meta(self, ref_id: str) -> dict[str, Any] | None:
        """Provenance metadata for one reference (no array load)."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM dark_references WHERE id = ?", (ref_id,)
            ).fetchone()
        return self._row_to_meta(row) if row is not None else None

    def list(self, mode: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM dark_references"
        args: list[Any] = []
        if mode:
            query += " WHERE mode = ?"
            args.append(mode)
        query += " ORDER BY created_at ASC"
        with self._connect() as conn:
            rows = conn.execute(query, args).fetchall()
        return [self._row_to_meta(row) for row in rows]

    @staticmethod
    def _row_to_meta(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "created_at": row["created_at"],
            "mode": row["mode"],
            "fingerprint": json.loads(row["fingerprint"]),
            "iterations": row["iterations"],
            "gate_steps": row["gate_steps"],
            "npy_path": row["npy_path"],
            "source_path": row["source_path"],
        }
