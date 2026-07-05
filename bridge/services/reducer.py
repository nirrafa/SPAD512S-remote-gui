"""Callable port of the lab's ``Reduce_size_512SPAD.py``.

Input: an acquisition PNG folder. Output, written next to the folder as the
original does: ``meta_<folder>.json`` (the first PNG's metadata dict) and
``movie_arr_<folder>.npy`` (3-D uint16, ``(nframes, x, y)``). Unlike the
original, the crop defaults to the full frame — its hardcoded 512×256 crop
was experiment-specific (docs/learnings.md) — and is configurable per call.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image


def _png_metadata(path: Path) -> dict[str, str]:
    with Image.open(path) as im:
        im.load()
        return {k: v for k, v in im.info.items() if isinstance(v, str)}


def _expected_frames(meta: dict[str, str]) -> int:
    frames = meta.get("Frames")
    if frames is None:
        raise ValueError("Metadata 'Frames' not found in the image")
    gate_steps = meta.get("Gate steps")
    if gate_steps is not None:
        return int(gate_steps) * int(frames)
    return int(frames)


def reduce_folder(
    png_dir: Path,
    out_dir: Path | None = None,
    *,
    crop_x: tuple[int, int] | None = None,
    crop_y: tuple[int, int] | None = None,
) -> dict[str, Any]:
    png_files = sorted(png_dir.glob("*.png"))
    if not png_files:
        raise ValueError(f"No PNG files found in the directory: {png_dir}")

    meta = _png_metadata(png_files[0])
    count = min(_expected_frames(meta), len(png_files))

    first = np.asarray(Image.open(png_files[0]))
    movie_arr = np.zeros((count, *first.shape), dtype=np.uint16)
    movie_arr[0] = first
    for index in range(1, count):
        movie_arr[index] = np.asarray(Image.open(png_files[index]))

    if crop_x is not None:
        movie_arr = movie_arr[:, crop_x[0] : crop_x[1], :]
    if crop_y is not None:
        movie_arr = movie_arr[:, :, crop_y[0] : crop_y[1]]

    target = out_dir or png_dir.parent
    target.mkdir(parents=True, exist_ok=True)
    movie_path = target / f"movie_arr_{png_dir.name}.npy"
    meta_path = target / f"meta_{png_dir.name}.json"
    np.save(movie_path, movie_arr)
    meta_path.write_text(json.dumps(meta))

    return {
        "meta_json": meta_path,
        "movie_npy": movie_path,
        "movie_npy_shape": list(movie_arr.shape),
        "pipeline_compatible": _verify(movie_path, meta_path),
    }


def _verify(movie_path: Path, meta_path: Path) -> bool:
    """Re-load the outputs the way ``512^2_*.py``/``SEP_D.py`` load them."""
    try:
        arr = np.load(movie_path, allow_pickle=True, mmap_mode="r")
        meta = json.loads(meta_path.read_text())
        int(meta["Frames"])
        integration = meta["Integration time"]
        if integration.endswith("ms"):
            float(integration.removesuffix("ms"))
        float(meta["Laser frequency"].removesuffix("MHz"))
        if "Gate steps" in meta:
            int(meta["Gate steps"])
            float(meta["Gate width"].removesuffix("ns"))
            float(meta["Gate step size"].removesuffix("ps"))
        return bool(arr.ndim == 3)
    except (OSError, KeyError, ValueError):
        return False
