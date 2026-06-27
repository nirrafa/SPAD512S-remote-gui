"""Decoders for vendor responses.

Text responses carry a trailing ``DONE`` sentinel (see learnings.md: the
sentinel glues onto the last field, so it must be stripped before parsing).
Binary acquisition data is handled by :mod:`bridge.protocol.client`.
"""
from __future__ import annotations

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


def bytes_per_frame(bit_depth: int, rows: int, im_width: int, pileup: bool) -> int:
    """Wire size of one intensity frame, matching the cSPAD decode paths."""
    if bit_depth == 1:
        return rows * rows // 8
    if bit_depth < 9 and not pileup:
        return rows * im_width
    return rows * im_width * 2


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
