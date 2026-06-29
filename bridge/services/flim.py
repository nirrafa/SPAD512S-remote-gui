"""FLIM processing: decode the raw-FLIM CSV, compute phasor + lifetime.

The bridge always requests raw FLIM data and computes phasor/lifetime host-side
(rather than relying on vendor-saved image files). ``output_format`` only shapes
the response. Per-pixel g/s is downsampled before transport so the JSON stays
small (full arrays stay on the host, per constraints).
"""
from __future__ import annotations

from typing import Any

import numpy as np

from bridge.protocol.decoder import decode_flim_csv, flim_phasor, phasor_to_lifetime
from bridge.services.preview import make_preview

_PHASOR_SAMPLE = 4096  # cap on g/s points sent to the browser


def process_flim(text: str, *, rows: int, cols: int, output_format: str) -> dict[str, Any]:
    frames = decode_flim_csv(text, rows=rows, cols=cols)
    n_gates = int(frames.shape[0])
    g, s = flim_phasor(frames)
    lifetime = phasor_to_lifetime(g, s, omega=2.0 * np.pi / n_gates)
    intensity = frames.sum(axis=0)

    g_flat = g.reshape(-1)
    s_flat = s.reshape(-1)
    if g_flat.size > _PHASOR_SAMPLE:
        idx = np.linspace(0, g_flat.size - 1, _PHASOR_SAMPLE).astype(int)
        g_flat, s_flat = g_flat[idx], s_flat[idx]

    result: dict[str, Any] = {
        "status": "done",
        "phasor": {
            "g": np.round(g_flat, 4).tolist(),
            "s": np.round(s_flat, 4).tolist(),
        },
        "total_gate_steps": n_gates,
        "output_format": output_format,
    }
    if output_format == "image":
        result["lifetime_map"] = make_preview(lifetime)
        result["preview"] = make_preview(intensity)
    return result
