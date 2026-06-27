"""Builders for vendor command strings.

Centralizes the exact wire format so the bytes-on-the-wire details live in one
place (see learnings.md for protocol quirks).
"""
from __future__ import annotations


def info() -> str:
    return "D"


def readout() -> str:
    return "R"


def voltages() -> str:
    return "V"


def set_vex(vex: float) -> str:
    return f"V,{vex}"


def cooling(enabled: bool) -> str:
    return f"S,{1 if enabled else 0}"


def pileup(enabled: bool) -> str:
    return f"PU,{1 if enabled else 0}"


def intensity(
    *,
    bit_depth: int,
    integration_time: float,
    iterations: int,
    overlap: bool,
    im_width: int,
) -> str:
    # I,<bitDepth>,<intTime>,<iterations>,0,<overlap>,0,1,<im_width>
    return (
        f"I,{bit_depth},{integration_time},{iterations},0,"
        f"{1 if overlap else 0},0,1,{im_width}"
    )
