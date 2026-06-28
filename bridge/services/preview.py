"""Downsampled preview generation for browser display.

Full arrays stay on the host (see constraints); the browser receives a small
auto-stretched 8-bit grayscale image and applies a colormap client-side.
"""
from __future__ import annotations

import base64

import numpy as np
from typing_extensions import TypedDict

MAX_PREVIEW = 256


class Preview(TypedDict):
    width: int
    height: int
    max_value: int
    data: str  # base64-encoded uint8, row-major


def make_preview(frame: np.ndarray, max_size: int = MAX_PREVIEW) -> Preview:
    """Downsample ``frame`` (2D) to ≤ ``max_size`` and auto-stretch to uint8."""
    rows, cols = frame.shape
    row_step = max(1, rows // max_size)
    col_step = max(1, cols // max_size)
    small = frame[::row_step, ::col_step]

    peak = int(small.max()) if small.size else 0
    if peak > 0:
        stretched = (small.astype(np.float32) * (255.0 / peak)).astype(np.uint8)
    else:
        stretched = np.zeros_like(small, dtype=np.uint8)

    return Preview(
        width=int(stretched.shape[1]),
        height=int(stretched.shape[0]),
        max_value=peak,
        data=base64.b64encode(np.ascontiguousarray(stretched).tobytes()).decode("ascii"),
    )
