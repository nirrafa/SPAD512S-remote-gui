"""Host-side data persistence: vendor-convention PNG folders.

Layout matches the lab pipeline (docs/learnings.md "Data pipeline
compatibility"): ``<base>/<mode>_images/acqXXXXX/IMGxxxxx.png`` with the exact
vendor metadata keys embedded as PNG text chunks. Key names and unit suffixes
are load-bearing — the downstream reducer and analysis scripts
(``Reduce_size_512SPAD.py``, ``512^2_*.py``, ``SEP_D.py``) parse them with
``removesuffix``, so a missing or renamed key silently breaks analysis.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image
from PIL.PngImagePlugin import PngInfo

_ACQ_RE = re.compile(r"acq(\d+).*")
_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")

AUTHOR = "Pi Imaging Technology"
SYSTEM = "SPAD512S"


@dataclass
class SavedAcquisition:
    acq_dir: Path
    acq_name: str
    png_files: list[Path]


def _fmt(value: float) -> str:
    return f"{value:g}"


def build_png_metadata(
    *,
    mode: str,
    integration_time: float,
    integration_time_unit: str,
    iterations: int,
    overlap: bool,
    laser_frequency_hz: float,
    software_version: str,
    taken_at: datetime,
    gate_steps: int | None = None,
    gate_step_size_ps: float | None = None,
    gate_width_ns: float | None = None,
    gate_offset_ps: float | None = None,
    gate_trigger_external: bool = False,
    gate_arbitrary: bool = False,
) -> dict[str, str]:
    """Common (per-acquisition) metadata; per-frame keys are added at save time.

    Gate keys are only present for gated mode — the reducer multiplies
    ``Frames`` by ``Gate steps`` when the latter exists, so intensity PNGs
    must omit it.
    """
    meta: dict[str, str] = {
        "Author": AUTHOR,
        "System": SYSTEM,
        "Date taken": taken_at.strftime("%Y-%m-%d"),
        "Time taken": taken_at.strftime("%H:%M:%S"),
        "Mode": mode.capitalize(),
        "Integration time": f"{_fmt(integration_time)}{integration_time_unit}",
        "Laser frequency": f"{_fmt(laser_frequency_hz / 1e6)}MHz",
        "Overlap": "1" if overlap else "0",
        "Frames": str(iterations),
        "External frame trigger": "0",
        "External gate trigger": "1" if gate_trigger_external else "0",
        "Software version": software_version,
    }
    if gate_steps is not None:
        meta["Gate steps"] = str(gate_steps)
        meta["Gate step arbitrary"] = "1" if gate_arbitrary else "0"
        if gate_step_size_ps is not None:
            meta["Gate step size"] = f"{_fmt(gate_step_size_ps)}ps"
            meta["Gate increment"] = f"{_fmt(gate_step_size_ps)}ps"
        if gate_width_ns is not None:
            meta["Gate width"] = f"{_fmt(gate_width_ns)}ns"
        if gate_offset_ps is not None:
            meta["Gate offset"] = f"{_fmt(gate_offset_ps)}ps"
    return meta


def name_suffix(sample_name: str | None, experiment_name: str | None) -> str | None:
    parts = [_SAFE_NAME_RE.sub("-", p) for p in (sample_name, experiment_name) if p]
    return "_".join(parts) or None


def _next_acq_dir(mode_root: Path, suffix: str | None) -> Path:
    mode_root.mkdir(parents=True, exist_ok=True)
    highest = 0
    for child in mode_root.iterdir():
        match = _ACQ_RE.fullmatch(child.name)
        if match:
            highest = max(highest, int(match.group(1)))
    name = f"acq{highest + 1:05d}"
    if suffix:
        name = f"{name}_{suffix}"
    acq_dir = mode_root / name
    acq_dir.mkdir(parents=True, exist_ok=True)
    return acq_dir


def _frame_image(frame: np.ndarray, bit_depth: int) -> Image.Image:
    if bit_depth <= 8:
        return Image.fromarray(frame.astype(np.uint8), mode="L")
    return Image.fromarray(frame.astype(np.uint16))


def save_acquisition(
    stack: np.ndarray,
    *,
    base_dir: Path,
    mode: str,
    bit_depth: int,
    metadata: dict[str, str],
    gate_steps: int | None = None,
    folder_suffix: str | None = None,
) -> SavedAcquisition:
    """Write ``stack`` (nframes, rows, cols) as ``IMGxxxxx.png`` files.

    For gated data (frames ordered gate-steps-within-iteration) ``Frame`` is
    the iteration index and ``Gate step`` the step index, matching the vendor.
    """
    acq_dir = _next_acq_dir(base_dir / f"{mode}_images", folder_suffix)
    png_files: list[Path] = []
    for index, frame in enumerate(stack):
        info = PngInfo()
        for key, value in metadata.items():
            info.add_text(key, value)
        if gate_steps is None:
            info.add_text("Frame", str(index))
        else:
            info.add_text("Frame", str(index // gate_steps))
            info.add_text("Gate step", str(index % gate_steps))
        path = acq_dir / f"IMG{index:05d}.png"
        _frame_image(frame, bit_depth).save(path, pnginfo=info, compress_level=1)
        png_files.append(path)
    return SavedAcquisition(acq_dir=acq_dir, acq_name=acq_dir.name, png_files=png_files)
