"""Minimal host-side data persistence for Phase 3.

Saves the decoded stack as ``movie_arr.npy`` under an auto-incrementing
acquisition folder. The full lab layout (PNG folder + JSON sidecar + reducer
output) lands in Phase 10.
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np

_ACQ_RE = re.compile(r"acq(\d+)")


def _next_acq_dir(mode_root: Path) -> Path:
    mode_root.mkdir(parents=True, exist_ok=True)
    highest = 0
    for child in mode_root.iterdir():
        match = _ACQ_RE.fullmatch(child.name)
        if match:
            highest = max(highest, int(match.group(1)))
    acq_dir = mode_root / f"acq{highest + 1:05d}"
    acq_dir.mkdir(parents=True, exist_ok=True)
    return acq_dir


def save_stack(stack: np.ndarray, *, data_root: str, mode: str) -> str:
    """Persist ``stack`` (nframes, rows, cols) and return the host path."""
    acq_dir = _next_acq_dir(Path(data_root) / f"{mode}_images")
    out_path = acq_dir / "movie_arr.npy"
    np.save(out_path, stack)
    return str(out_path)
