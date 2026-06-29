"""Pure command dispatch for the mock vendor protocol.

``handle()`` maps an ASCII command line to a :class:`CommandResult`. It performs
no I/O — the TCP server and the in-process test harness both call it and apply
their own framing (text + ``DONE`` vs. raw binary + ``DONE``).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from mock_server import synthetic_data as synth
from mock_server.state import (
    GATED_BIT_DEPTHS,
    INT_BIT_DEPTHS,
    SENSOR_ROWS,
    VALID_WIDTHS,
    MockState,
)

DONE = "DONE"


@dataclass
class CommandResult:
    """Outcome of a command.

    - ``text``: textual payload (framed with a trailing ``DONE`` by the caller).
    - ``wire_bytes``: pre-encoded binary payload for acquisitions (``DONE``
      appended as raw bytes by the TCP server).
    - ``image`` / ``phasor``: numpy views for test introspection.
    - ``is_error``: unknown/failed command (returned verbatim, no ``DONE``).
    """

    text: str = ""
    wire_bytes: bytes | None = None
    image: np.ndarray | None = None
    phasor: tuple[np.ndarray, np.ndarray] | None = None
    is_error: bool = False


def _system_info(state: MockState) -> str:
    return "\n".join(
        [
            "Master FPGA serial: MOCK-MSTR-0001",
            "Slave FPGA serial: MOCK-SLV-0001",
            "Software version: 3.1.4-mock",
            "Firmware version: 2.0.0-mock",
            "Hardware version: 1.0",
            f"Hardware flavour: {state.hardware_flavour}",
            "Intensity imaging: 1",
            "Gated imaging: 1",
            "FLIM imaging: 1",
        ]
    )


def _coerce_int(value: str, default: int) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def handle(command_line: str, state: MockState) -> CommandResult:
    state.command_count += 1
    if state.should_fail():
        return CommandResult(text="ERROR: simulated failure", is_error=True)

    raw = command_line.strip()
    if not raw:
        return CommandResult(text="ERROR: empty command", is_error=True)

    head, _, rest = raw.partition(",")
    args = rest.split(",") if rest else []

    handlers = {
        "D": _handle_info_or_path,
        "V": _handle_voltage,
        "R": _handle_readout,
        "AE": _handle_auto_exposure,
        "S": _handle_cooling,
        "PU": _handle_pileup,
        "CALIB": _handle_calibration,
        "I": _handle_intensity,
        "G": _handle_gated,
        "Ga": _handle_arbitrary_steps,
        "Gf": _handle_optimal_params,
        "F": _handle_flim,
    }
    handler = handlers.get(head)
    if handler is None:
        return CommandResult(text=f"ERROR: unknown command '{head}'", is_error=True)
    return handler(args, state)


def _handle_info_or_path(args: list[str], state: MockState) -> CommandResult:
    if args:  # D,<path> -> set save path
        path = ",".join(args)
        return CommandResult(text=f"Path set to {path}")
    return CommandResult(text=_system_info(state))


def _handle_voltage(args: list[str], state: MockState) -> CommandResult:
    if args:
        state.vex = float(args[0]) if args[0] else state.vex
        return CommandResult(text=f"Excess bias set to {state.vex} V")
    return CommandResult(text=f"{state.vq},{state.vex}")


def _handle_readout(_args: list[str], state: MockState) -> CommandResult:
    return CommandResult(
        text=f"{state.t_master},{state.t_slave},{state.t_pcb},{state.t_chip},"
        f"{state.laser_freq},{state.frame_freq}"
    )


def _handle_auto_exposure(args: list[str], _state: MockState) -> CommandResult:
    mode = args[0] if args else "0"
    return CommandResult(text=f"Auto-exposure mode {mode}")


def _handle_cooling(args: list[str], state: MockState) -> CommandResult:
    if args:
        state.cooling_enabled = args[0] == "1"
    status = "enabled" if state.cooling_enabled else "disabled"
    return CommandResult(text=f"Cooling {status}")


def _handle_pileup(args: list[str], state: MockState) -> CommandResult:
    if args:
        state.pileup_correction = args[0] == "1"
    status = "on" if state.pileup_correction else "off"
    return CommandResult(text=f"Pileup correction {status}")


def _handle_calibration(args: list[str], state: MockState) -> CommandResult:
    if not args:
        return CommandResult(text="Calibration ready")
    kind = args[0].strip().upper()
    if kind in ("3", "BREAKDOWN"):
        state.breakdown_calibrated = True
        return CommandResult(
            text="The breakdown calibration process has started.\n"
            "The breakdown is around 24.5"
        )
    if kind == "0":
        state.noise_calibrated = True
        return CommandResult(text="Noise calibration complete.")
    if kind == "1":
        state.dead_pixel_calibrated = True
        return CommandResult(text="Dead pixel calibration complete.")
    if kind == "2":
        state.master_slave_offset_calibrated = True
        return CommandResult(text="Master/slave offset calibration complete.")
    return CommandResult(text=f"Calibration {kind} complete.")


def _resolve_width(value: int) -> int:
    return value if value in VALID_WIDTHS else SENSOR_ROWS


def _resolve_bit_depth(value: int) -> int:
    return value if value in INT_BIT_DEPTHS else 8


def _resolve_gated_bit_depth(value: int) -> int:
    # Gated mode does not support 1-bit or 4-bit (vendor: depths 6-12 only).
    return value if value in GATED_BIT_DEPTHS else 8


def _handle_intensity(args: list[str], state: MockState) -> CommandResult:
    # I,<bit>,<intTime>,<iters>,0,<overlap>,0,1,<width>  (width is arg index 7)
    bit_depth = _resolve_bit_depth(_coerce_int(args[0], 8)) if len(args) > 0 else 8
    iterations = _coerce_int(args[2], 1) if len(args) > 2 else 1
    width = _resolve_width(_coerce_int(args[7], SENSOR_ROWS)) if len(args) > 7 else SENSOR_ROWS

    # One representative frame is encoded once and tiled across iterations: the
    # frame *shape/format* is what consumers verify, and this keeps large
    # iteration counts cheap (O(1) numpy work, no per-frame allocation).
    frame = synth.intensity_frame(width, bit_depth, state.seed)
    one = synth.encode_intensity_frames([frame], bit_depth, state.pileup_correction)
    wire = one * iterations
    return CommandResult(
        text=f"Intensity acquisition complete ({iterations} frame(s), {bit_depth}-bit)",
        wire_bytes=wire,
        image=frame,
    )


def _handle_gated(args: list[str], state: MockState) -> CommandResult:
    # G,<bit>,<intTime>,<iters>,<steps>,...
    bit_depth = _resolve_gated_bit_depth(_coerce_int(args[0], 8)) if len(args) > 0 else 8
    iterations = _coerce_int(args[2], 1) if len(args) > 2 else 1
    gate_steps = _coerce_int(args[3], 10) if len(args) > 3 else 10
    width = SENSOR_ROWS
    n_frames = max(iterations * gate_steps, 1)

    stack = synth.gated_stack(width, bit_depth, n_frames, state.seed)
    frames = [stack[:, :, k] for k in range(n_frames)]
    wire = synth.encode_intensity_frames(frames, bit_depth, state.pileup_correction)
    return CommandResult(
        text=f"Gated acquisition complete ({n_frames} frame(s), {bit_depth}-bit)",
        wire_bytes=wire,
        image=stack,
    )


def _handle_arbitrary_steps(args: list[str], state: MockState) -> CommandResult:
    raw = ",".join(args)
    steps = [float(s) for s in raw.replace(";", ",").split(",") if s.strip()]
    state.arbitrary_steps = steps
    return CommandResult(text=f"Arbitrary steps set ({len(steps)} steps)")


def _handle_optimal_params(args: list[str], _state: MockState) -> CommandResult:
    # Gf,1,<stepSize>,<gateWidth>,1 -> multi-line parsed by cSPAD.get_opt_gated_param
    step_size = _coerce_int(args[1], 18) if len(args) > 1 else 18
    gate_width = _coerce_int(args[2], 5) if len(args) > 2 else 5
    nbr_steps = max(int(round(1000.0 / max(step_size, 1))), 1)
    offset = gate_width * 10
    text = "\n".join(
        [
            "Optimal gated parameters:",
            "Computed for one full gate cycle.",
            f"The number of gate steps is {nbr_steps}",
            f"The gate offset is {offset} ps",
            f"The minimum gate step size is {step_size} ps",
        ]
    )
    return CommandResult(text=text)


_FLIM_BASE_GATES = 8


def _handle_flim(args: list[str], state: MockState) -> CommandResult:
    sub = args[0].strip() if args else ""
    if sub.startswith("c"):
        state.flim_irf_calibrated = True
        return CommandResult(text="FLIM IRF calibration complete.")
    # Acquisition (F,i,<t>,<subsample>,<raw>,1) or bare F: stream raw-FLIM CSV.
    subsample = _coerce_int(args[2], 1) if sub == "i" and len(args) > 2 else 1
    n_gates = max(_FLIM_BASE_GATES // max(subsample, 1), 4)
    wire = synth.flim_decay_csv(SENSOR_ROWS, SENSOR_ROWS, n_gates, state.seed)
    g, s = synth.flim_phasor(64, state.seed)  # for the in-process harness path
    return CommandResult(
        text="FLIM acquisition complete.", wire_bytes=wire, phasor=(g, s)
    )
