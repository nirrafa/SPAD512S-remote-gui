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


def arbitrary_steps(steps: list[float]) -> str:
    return "Ga," + ";".join(str(s) for s in steps)


def _direction_code(direction: str) -> int:
    return 1 if direction.lower() == "reverse" else 0


def _trigger_code(source: str) -> int:
    return 1 if source.lower() == "external" else 0


def gated(
    *,
    bit_depth: int,
    integration_time: float,
    iterations: int,
    gate_steps: int,
    gate_step_size: float,
    gate_offset: int,
    gate_width: int,
    gate_direction: str,
    gate_trigger_source: str,
    overlap: bool,
    stream: bool,
    arbitrary: bool,
) -> str:
    # G,<bit>,<intTime>,<iters>,<steps>,<stepSize>,<arbitrary>,<width>,
    #   <offset>,<dir>,<trig>,<overlap>,<stream>
    return (
        f"G,{bit_depth},{integration_time},{iterations},{gate_steps},"
        f"{gate_step_size},{1 if arbitrary else 0},{gate_width},{gate_offset},"
        f"{_direction_code(gate_direction)},{_trigger_code(gate_trigger_source)},"
        f"{1 if overlap else 0},{1 if stream else 0}"
    )


def optimal_gated_params(*, gate_step_size: float, gate_width: int) -> str:
    # Gf,1,<stepSize>,<gateWidth>,1
    return f"Gf,1,{gate_step_size},{gate_width},1"
