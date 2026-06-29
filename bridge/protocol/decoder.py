"""Decoders for vendor responses.

Text responses carry a trailing ``DONE`` sentinel (see learnings.md: the
sentinel glues onto the last field, so it must be stripped before parsing).
Binary acquisition data is handled by :mod:`bridge.protocol.client`.
"""
from __future__ import annotations

import re

import numpy as np
from typing_extensions import TypedDict

INT_BIT_DEPTHS: list[int] = [1, 4, 6, 7, 8, 9, 10, 11, 12]
GATED_BIT_DEPTHS: list[int] = [6, 7, 8, 9, 10, 11, 12]
ROI_WIDTHS_512: list[int] = [4, 8, 16, 32, 64, 128, 256, 512]
ROI_WIDTHS_1024: list[int] = [8, 16, 32, 64, 128, 256, 512, 1024]

DONE = "DONE"
ERROR = "ERROR"


class SystemInfo(TypedDict):
    fpga_serial_master: str
    fpga_serial_slave: str
    sw_version: str
    fw_version: str
    hw_version: str
    hardware_flavour: str
    sensor_size: int
    enabled_features: dict[str, bool]
    valid_bit_depths: list[int]
    valid_roi_widths: list[int]


class TriggerInfo(TypedDict):
    laser_frequency_hz: float
    frame_clock_frequency_hz: float
    trigger_valid: bool


def strip_done(text: str) -> str:
    """Remove a trailing ``DONE`` sentinel (and surrounding whitespace)."""
    stripped = text.strip()
    if stripped.endswith(DONE):
        stripped = stripped[: -len(DONE)].rstrip()
    return stripped


def is_error(text: str) -> bool:
    return ERROR in text


def _value_after_colon(line: str) -> str:
    _, _, value = line.partition(":")
    return value.strip()


def parse_system_info(text: str) -> SystemInfo:
    lines = [line for line in strip_done(text).splitlines() if line.strip()]
    if len(lines) < 9:
        raise ValueError(f"Unexpected system info ({len(lines)} lines): {text!r}")

    flavour = _value_after_colon(lines[5])
    sensor_size = 1024 if flavour in ("1M", "1024") else 512
    return SystemInfo(
        fpga_serial_master=_value_after_colon(lines[0]),
        fpga_serial_slave=_value_after_colon(lines[1]),
        sw_version=_value_after_colon(lines[2]),
        fw_version=_value_after_colon(lines[3]),
        hw_version=_value_after_colon(lines[4]),
        hardware_flavour=flavour,
        sensor_size=sensor_size,
        enabled_features={
            "intensity": _value_after_colon(lines[6]) == "1",
            "gated": _value_after_colon(lines[7]) == "1",
            "flim": _value_after_colon(lines[8]) == "1",
        },
        valid_bit_depths=list(INT_BIT_DEPTHS),
        valid_roi_widths=ROI_WIDTHS_1024 if sensor_size == 1024 else ROI_WIDTHS_512,
    )


def parse_readout(text: str, *, expected_laser_hz: float | None = None) -> TriggerInfo:
    """Parse the ``R`` response: ``T_MSTR,T_SLV,T_PCB,T_CHIP,laser,frame``."""
    fields = strip_done(text).split(",")
    if len(fields) < 6:
        raise ValueError(f"Unexpected readout: {text!r}")
    laser_hz = float(fields[4])
    frame_hz = float(fields[5])
    if expected_laser_hz is not None:
        trigger_valid = abs(laser_hz - expected_laser_hz) <= 0.05 * expected_laser_hz
    else:
        trigger_valid = laser_hz > 0
    return TriggerInfo(
        laser_frequency_hz=laser_hz,
        frame_clock_frequency_hz=frame_hz,
        trigger_valid=trigger_valid,
    )


def integration_time_unit(bit_depth: int) -> str:
    """1/4-bit acquisitions take integration time in µs; ≥6-bit in ms."""
    return "us" if bit_depth in (1, 4) else "ms"


def bytes_per_frame(bit_depth: int, rows: int, im_width: int, pileup: bool) -> int:
    """Wire size of one intensity frame, matching the cSPAD decode paths."""
    if bit_depth == 1:
        return rows * rows // 8
    if bit_depth < 9 and not pileup:
        return rows * im_width
    return rows * im_width * 2


def decode_intensity(
    data: bytes,
    *,
    bit_depth: int,
    rows: int,
    im_width: int,
    iterations: int,
    pileup: bool,
) -> np.ndarray:
    """Decode raw intensity bytes into a ``(iterations, rows, width)`` uint16 stack.

    Mirrors the three cSPAD decode paths (1-bit packed; ≤8-bit one byte/px;
    ≥9-bit or pileup two bytes little-endian). 1-bit frames are ``rows × rows``.
    """
    if bit_depth == 1:
        per = rows * rows // 8
        frames = np.empty((iterations, rows, rows), dtype=np.uint16)
        for i in range(iterations):
            chunk = np.frombuffer(data[i * per : (i + 1) * per], dtype=np.uint8)
            bits = np.unpackbits(chunk).reshape((rows, rows))
            frames[i] = np.rot90(bits).astype(np.uint16)
        return frames

    if bit_depth < 9 and not pileup:
        per = rows * im_width
        flat = np.frombuffer(data[: iterations * per], dtype=np.uint8).astype(np.uint16)
        return flat.reshape((iterations, rows, im_width))

    per = rows * im_width * 2
    out = np.empty((iterations, rows, im_width), dtype=np.uint16)
    for i in range(iterations):
        frame = np.frombuffer(data[i * per : (i + 1) * per], dtype="<u2")
        out[i] = frame.reshape((rows, im_width))
    return out


class OptimalGated(TypedDict):
    steps: int
    offset: int
    min_step: int


def _last_int(line: str, default: int = 0) -> int:
    matches = re.findall(r"-?\d+", line)
    return int(matches[-1]) if matches else default


def parse_optimal_gated(text: str) -> OptimalGated:
    """Parse the multi-line ``Gf`` response into steps/offset/min_step."""
    steps = offset = min_step = 0
    for line in strip_done(text).splitlines():
        lowered = line.lower()
        if "number of gate steps" in lowered:
            steps = _last_int(line)
        elif "gate offset" in lowered:
            offset = _last_int(line)
        elif "minimum gate step size" in lowered:
            min_step = _last_int(line)
    return OptimalGated(steps=steps, offset=offset, min_step=min_step)


def decode_flim_csv(text: str, *, rows: int, cols: int) -> np.ndarray:
    """Decode the raw-FLIM CSV response into an ``(n_gates, rows, cols)`` stack.

    The vendor streams one pixel intensity per line (frames concatenated,
    row-major), ``DONE``-terminated. ``n_gates`` is derived from the value
    count, mirroring ``python_tcp_stream_flim.py``.
    """
    body = strip_done(text)
    values = np.fromstring(body, sep="\n", dtype=np.float64)
    frame_pixels = rows * cols
    if frame_pixels == 0 or values.size < frame_pixels:
        raise ValueError(f"FLIM payload too small: {values.size} values")
    n_gates = values.size // frame_pixels
    usable = n_gates * frame_pixels
    return values[:usable].reshape(n_gates, rows, cols)


def flim_phasor(frames: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """First-harmonic phasor (g, s) per pixel over the gate axis of ``frames``."""
    n_gates = frames.shape[0]
    theta = 2.0 * np.pi * np.arange(n_gates) / n_gates
    total = frames.sum(axis=0)
    total_safe = np.where(total > 0, total, 1.0)
    g = (frames * np.cos(theta)[:, None, None]).sum(axis=0) / total_safe
    s = (frames * np.sin(theta)[:, None, None]).sum(axis=0) / total_safe
    return g, s


def phasor_to_lifetime(g: np.ndarray, s: np.ndarray, *, omega: float = 1.0) -> np.ndarray:
    """Single-exponential lifetime map from phasor coords: ``tau = (s/g)/omega``."""
    g_safe = np.where(np.abs(g) > 1e-9, g, 1e-9)
    return np.clip((s / g_safe) / omega, 0.0, None)


def parse_temperatures(text: str) -> dict[str, float]:
    fields = strip_done(text).split(",")
    if len(fields) < 4:
        raise ValueError(f"Unexpected temperatures: {text!r}")
    return {
        "t_master": float(fields[0]),
        "t_slave": float(fields[1]),
        "t_pcb": float(fields[2]),
        "t_chip": float(fields[3]),
    }
