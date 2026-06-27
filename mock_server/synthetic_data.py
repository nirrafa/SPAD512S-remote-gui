"""Synthetic data generators and wire encoders for the mock vendor server.

The generators produce numpy arrays resembling SPAD acquisitions; the encoders
serialize them into the exact byte layout the vendor streams, so the real
``cSPAD`` client (and the bridge) decode them without modification.
"""
from __future__ import annotations

import numpy as np

from mock_server.state import SENSOR_ROWS


def _rng(seed: int) -> np.random.Generator:
    return np.random.default_rng(seed)


def intensity_frame(width: int, bit_depth: int, seed: int) -> np.ndarray:
    """A single intensity image as uint16 counts in ``[0, 2**bit_depth - 1]``."""
    rng = _rng(seed)
    rows = SENSOR_ROWS
    yy, xx = np.mgrid[0:rows, 0:width]
    max_val = (1 << bit_depth) - 1
    gradient = (np.sin(xx / width * np.pi) * np.cos(yy / rows * np.pi) + 1.0) / 2.0
    base = gradient * max_val * 0.6
    noise = rng.poisson(np.clip(base, 0, None))
    frame: np.ndarray = np.clip(noise, 0, max_val).astype(np.uint16)
    return frame


def gated_stack(width: int, bit_depth: int, n_frames: int, seed: int) -> np.ndarray:
    """A gated stack shaped ``(rows, width, n_frames)`` with a decaying signal."""
    rows = SENSOR_ROWS
    stack = np.empty((rows, width, n_frames), dtype=np.uint16)
    max_val = (1 << bit_depth) - 1
    for k in range(n_frames):
        decay = np.exp(-k / max(n_frames / 3.0, 1.0))
        frame = intensity_frame(width, bit_depth, seed + k)
        stack[:, :, k] = np.clip(frame * decay, 0, max_val).astype(np.uint16)
    return stack


def flim_phasor(width: int, seed: int) -> tuple[np.ndarray, np.ndarray]:
    """Phasor components ``(g, s)`` for a FLIM acquisition, points on the
    universal semicircle perturbed by noise."""
    rng = _rng(seed)
    n = width * width
    omega_tau = rng.uniform(0.3, 3.0, size=n)
    g = 1.0 / (1.0 + omega_tau**2)
    s = omega_tau / (1.0 + omega_tau**2)
    g = np.clip(g + rng.normal(0, 0.01, size=n), 0.0, 1.0)
    s = np.clip(s + rng.normal(0, 0.01, size=n), 0.0, 1.0)
    return g, s


# --- Wire encoders ------------------------------------------------------------


def encode_intensity_frames(frames: list[np.ndarray], bit_depth: int, pileup: bool) -> bytes:
    """Serialize intensity frames to the vendor wire layout (no DONE sentinel)."""
    out = bytearray()
    for frame in frames:
        out.extend(_encode_one(frame, bit_depth, pileup))
    return bytes(out)


def _encode_one(frame: np.ndarray, bit_depth: int, pileup: bool) -> bytes:
    if bit_depth == 1:
        # Packed bits: rows*rows/8 bytes; client unpacks with np.unpackbits + rot90.
        bits = (frame > 0).astype(np.uint8)
        if bits.shape != (SENSOR_ROWS, SENSOR_ROWS):
            padded = np.zeros((SENSOR_ROWS, SENSOR_ROWS), dtype=np.uint8)
            padded[:, : bits.shape[1]] = bits[:, :SENSOR_ROWS]
            bits = padded
        return np.packbits(bits).tobytes()
    if bit_depth < 9 and not pileup:
        # One byte per pixel, row-major.
        return np.ascontiguousarray(frame.astype(np.uint8)).tobytes()
    # Two bytes per pixel, little-endian (low byte first), as decoded by cSPAD.
    return np.ascontiguousarray(frame.astype("<u2")).tobytes()
