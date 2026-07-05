"""Verify produced files load the way the downstream pipeline loads them.

Mirrors the load patterns of ``Reduce_size_512SPAD.py`` / ``512^2_*.py`` /
``SEP_D.py``: ``movie_arr_*.npy`` via ``np.load`` (3-D, frames first) and
``meta_*.json`` keys parsed with ``removesuffix`` unit stripping.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pytest
from bridge.services.file_writer import build_png_metadata, save_acquisition
from bridge.services.reducer import reduce_folder


def _write_acq(base: Path, *, gated: bool) -> Path:
    rows, cols, frames = 32, 32, 6
    rng = np.random.default_rng(7)
    stack = rng.integers(0, 255, size=(frames, rows, cols), dtype=np.uint16)
    metadata = build_png_metadata(
        mode="Gated" if gated else "Intensity",
        integration_time=100.0,
        integration_time_unit="ms",
        iterations=2 if gated else frames,
        overlap=False,
        laser_frequency_hz=40e6,
        software_version="0.1.0",
        taken_at=datetime(2026, 7, 4, 12, 0, 0),
        gate_steps=3 if gated else None,
        gate_step_size_ps=18.0 if gated else None,
        gate_width_ns=5.0 if gated else None,
        gate_offset_ps=0.0 if gated else None,
    )
    saved = save_acquisition(
        stack,
        base_dir=base,
        mode="gated" if gated else "intensity",
        bit_depth=8,
        metadata=metadata,
        gate_steps=3 if gated else None,
    )
    return saved.acq_dir


@pytest.mark.parametrize("gated", [False, True])
def test_reducer_output_loads_like_downstream(tmp_path: Path, gated: bool) -> None:
    acq_dir = _write_acq(tmp_path, gated=gated)
    result = reduce_folder(acq_dir)

    arr = np.load(result["movie_npy"], allow_pickle=True)
    assert arr.ndim == 3
    assert arr.shape[0] == 6
    assert arr.shape[1:] == (32, 32)

    meta = json.loads(Path(result["meta_json"]).read_text())
    assert int(meta["Frames"]) >= 1
    assert float(meta["Integration time"].removesuffix("ms")) == 100.0
    assert float(meta["Laser frequency"].removesuffix("MHz")) == 40.0
    if gated:
        assert int(meta["Gate steps"]) == 3
        assert float(meta["Gate width"].removesuffix("ns")) == 5.0
        assert float(meta["Gate step size"].removesuffix("ps")) == 18.0

    assert result["pipeline_compatible"] is True


def test_reducer_crop_configurable(tmp_path: Path) -> None:
    acq_dir = _write_acq(tmp_path, gated=False)
    result = reduce_folder(acq_dir, crop_y=(0, 16))
    arr = np.load(result["movie_npy"])
    assert arr.shape == (6, 32, 16)
