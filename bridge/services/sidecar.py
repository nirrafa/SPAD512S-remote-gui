"""JSON sidecar per acquisition.

Full parameter set, calibration snapshot, temperatures at acquisition time,
start/end timestamps, and sample/experiment tags. A superset of the reducer's
meta format: the PNG metadata dict is embedded under ``png_metadata`` so the
sidecar alone reconstructs the vendor context.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SIDECAR_NAME = "sidecar.json"


def write_sidecar(
    acq_dir: Path,
    *,
    params: dict[str, Any],
    calibration_state: dict[str, Any],
    temperatures: dict[str, float],
    timestamp_start: str,
    timestamp_end: str,
    png_metadata: dict[str, str],
    frame_count: int,
) -> Path:
    payload: dict[str, Any] = {
        **params,
        "calibration_state": calibration_state,
        "temperatures": temperatures,
        "timestamp_start": timestamp_start,
        "timestamp_end": timestamp_end,
        "frame_count": frame_count,
        "png_metadata": png_metadata,
    }
    path = acq_dir / SIDECAR_NAME
    path.write_text(json.dumps(payload, indent=2))
    return path


def read_sidecar(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text())
    if not isinstance(payload, dict):
        raise ValueError("sidecar is not a JSON object")
    return payload
