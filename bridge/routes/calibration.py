"""Calibration endpoints.

Phase 5 covers FLIM IRF calibration; Phase 7 extends this with noise / dead-pixel
/ master-slave-offset flows and a calibration state store. The
``app.state.flim_irf_calibrated`` flag still tracks whether a FLIM acquisition
should warn about a missing IRF; it is surfaced under ``flim_irf`` in the status.
"""
from __future__ import annotations

import asyncio

import numpy as np
from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict

from bridge.core.acquisition import AcquisitionRunner
from bridge.core.calibration_state import CalibrationStore
from bridge.core.instrument import InstrumentState, InstrumentStatus
from bridge.protocol import commands
from bridge.protocol.client import NotConnectedError, ProtocolClient, ProtocolError
from bridge.protocol.decoder import GATED_BIT_DEPTHS, bytes_per_frame, decode_intensity
from bridge.services.gated_dark_reference import (
    MIN_MEDIAN_REPEATS,
    GatedDarkReferenceStore,
    build_reference,
    gated_fingerprint,
)
from bridge.services.sweep import _gated_params

router = APIRouter(prefix="/api/calibrate")
status_router = APIRouter(prefix="/api/calibration")

_GATE_WIDTH_CODE = {"short": 0, "medium": 1, "long": 2}
_CALIBRATION_MODE = {"mono_exponential": 0, "bi_exponential": 1}

_SETUP_PROMPTS = {
    "noise": "Cap the objective / ensure dark conditions before calibrating.",
    "dead_pixel": "Cap the objective / ensure dark conditions before calibrating.",
    "master_slave_offset": "Provide uniform pulsed illumination before calibrating.",
}

_DCR_BIT_DEPTH = 8
_DCR_ROI_WIDTH = 512


class FlimIrfRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    calibration_type: str = "mono_exponential"
    expected_tau_ns: float | list[float] = 4.0
    gate_width: str = "medium"
    integration_time_ms: float = 1000.0


@router.post("/flim-irf")
async def calibrate_flim_irf(request: Request, params: FlimIrfRequest) -> dict[str, object]:
    protocol: ProtocolClient = request.app.state.protocol
    instrument: InstrumentState = request.app.state.instrument

    if not protocol.connected:
        return {"status": "error", "message": "vendor disconnected"}
    if instrument.is_busy:
        return {"status": "error", "message": "instrument busy"}

    mode = _CALIBRATION_MODE.get(params.calibration_type, 0)
    gate_width = _GATE_WIDTH_CODE.get(params.gate_width, 1)
    tau = params.expected_tau_ns
    tau_value = sum(tau) / len(tau) if isinstance(tau, list) and tau else float(tau)  # type: ignore[arg-type]

    await instrument.set(InstrumentStatus.CALIBRATING)
    try:
        await protocol.send_command(
            commands.flim_calibrate(
                mode=mode,
                integration_time=params.integration_time_ms,
                expected_tau_ns=tau_value,
                gate_width=gate_width,
            )
        )
    except (NotConnectedError, ProtocolError) as exc:
        return {"status": "error", "message": str(exc)}
    finally:
        await instrument.set(InstrumentStatus.IDLE)

    request.app.state.flim_irf_calibrated = True
    return {
        "status": "done",
        "calibration_type": params.calibration_type,
        "gate_width": params.gate_width,
    }


async def _run_calibration(request: Request, kind: str) -> dict[str, object]:
    protocol: ProtocolClient = request.app.state.protocol
    instrument: InstrumentState = request.app.state.instrument
    store: CalibrationStore = request.app.state.calibration

    if not protocol.connected:
        return {"status": "error", "message": "vendor disconnected"}
    if instrument.is_busy:
        return {"status": "error", "message": "instrument busy"}

    store.mark_running(kind)
    await instrument.set(InstrumentStatus.CALIBRATING)
    try:
        await protocol.send_command(commands.calibrate(kind))
    except (NotConnectedError, ProtocolError) as exc:
        store.mark_failed(kind)
        return {"status": "error", "message": str(exc)}
    finally:
        await instrument.set(InstrumentStatus.IDLE)

    store.mark_done(kind)
    response: dict[str, object] = {"status": "done"}
    prompt = _SETUP_PROMPTS.get(kind)
    if prompt is not None:
        response["setup_prompt"] = prompt
    return response


@router.post("/breakdown")
async def calibrate_breakdown(request: Request) -> dict[str, object]:
    return await _run_calibration(request, "breakdown")


@router.post("/noise")
async def calibrate_noise(request: Request) -> dict[str, object]:
    return await _run_calibration(request, "noise")


@router.post("/dead-pixel")
async def calibrate_dead_pixel(request: Request) -> dict[str, object]:
    return await _run_calibration(request, "dead_pixel")


@router.post("/master-slave-offset")
async def calibrate_master_slave_offset(request: Request) -> dict[str, object]:
    return await _run_calibration(request, "master_slave_offset")


@status_router.get("/status")
async def calibration_status(request: Request) -> dict[str, object]:
    store: CalibrationStore = request.app.state.calibration
    protocol: ProtocolClient = request.app.state.protocol

    # Breakdown calibration runs automatically as part of the vendor connect
    # handshake; reflect that the first time we observe a live connection.
    if protocol.connected and not store.is_valid("breakdown"):
        store.mark_done("breakdown")

    status: dict[str, object] = dict(store.snapshot())

    flim_done = bool(getattr(request.app.state, "flim_irf_calibrated", False))
    flim_entry: dict[str, object] = {"state": "done" if flim_done else "none"}
    if flim_done:
        flim_entry["stale"] = False
    status["flim_irf"] = flim_entry
    return status


class GatedDarkReferenceRequest(BaseModel):
    """Same gate-configuration surface as a gated acquisition — a dark
    reference is only valid for the exact config it was measured with, so the
    request mirrors ``GatedRequest`` (minus naming/reducer/correction)."""

    model_config = ConfigDict(extra="ignore")

    bit_depth: int = 8
    integration_time: float | None = None
    integration_time_ms: float | None = None
    iterations: int = 1
    gate_steps: int = 10
    gate_step_size_ps: float = 18.0
    gate_width: int = 5
    gate_offset: int = 0
    gate_direction: str = "forward"
    gate_trigger_source: str = "external"
    overlap: bool = False
    stream: bool = False
    pileup_correction: bool = False
    arbitrary_steps: list[float] | None = None


@router.post("/gated-dark-reference")
async def measure_gated_dark_reference(
    request: Request, body: GatedDarkReferenceRequest
) -> dict[str, object]:
    """Measure a covered-sensor gated acquisition and store its per-pixel,
    per-gate-step dark map. ``iterations`` is the repeat axis (median when
    >= 3, mean otherwise); the raw dark acquisition is persisted to disk like
    any gated run, as a lab record."""
    protocol: ProtocolClient = request.app.state.protocol
    runner: AcquisitionRunner = request.app.state.runner
    store: GatedDarkReferenceStore = request.app.state.dark_references

    if not protocol.connected:
        return {"status": "error", "message": "vendor disconnected"}
    if body.bit_depth not in GATED_BIT_DEPTHS:
        return {"status": "error", "message": f"invalid gated bit_depth {body.bit_depth}"}
    if body.gate_direction not in ("forward", "reverse"):
        return {"status": "error", "message": f"invalid gate_direction {body.gate_direction}"}
    if body.gate_trigger_source not in ("internal", "external"):
        return {"status": "error", "message": f"invalid trigger {body.gate_trigger_source}"}
    if body.iterations < 1:
        return {"status": "error", "message": "iterations must be >= 1"}

    params = _gated_params(body.model_dump(exclude_none=True))
    result = await runner.run_gated(params, keep_stack=True)
    stack = result.pop("_stack", None)
    if result.get("status") != "done" or stack is None:
        return result

    reference = await asyncio.to_thread(
        build_reference,
        stack,
        iterations=params.iterations,
        gate_steps=params.effective_steps,
    )
    reference_id = store.save(
        fingerprint=gated_fingerprint(params),
        reference=reference,
        iterations=params.iterations,
    )
    return {
        "status": "done",
        "reference_id": reference_id,
        "gate_steps": params.effective_steps,
        "iterations": params.iterations,
        "method": "median" if params.iterations >= MIN_MEDIAN_REPEATS else "mean",
        "setup_prompt": "Cap the sensor / ensure dark conditions before measuring.",
        "host_path": result.get("host_path"),
    }


@status_router.get("/gated-dark-references")
async def list_gated_dark_references(request: Request) -> dict[str, object]:
    store: GatedDarkReferenceStore = request.app.state.dark_references
    return {"references": store.list()}


def _dcr_curve(values: np.ndarray) -> dict[str, object]:
    sorted_values = np.sort(values.astype(np.float64))
    percentages = list(np.linspace(0.0, 100.0, num=101).tolist())
    dcr_values = list(np.percentile(sorted_values, percentages).tolist())
    return {"percentages": percentages, "dcr_values": dcr_values}


@status_router.get("/dcr-curve")
async def dcr_curve(request: Request) -> dict[str, object]:
    protocol: ProtocolClient = request.app.state.protocol
    if not protocol.connected:
        return {"status": "error", "message": "vendor disconnected"}

    rows = protocol.system_info["sensor_size"] if protocol.system_info else 512
    expected = bytes_per_frame(_DCR_BIT_DEPTH, rows, _DCR_ROI_WIDTH, pileup=False)
    command = commands.intensity(
        bit_depth=_DCR_BIT_DEPTH,
        integration_time=10.0,
        iterations=1,
        overlap=False,
        im_width=_DCR_ROI_WIDTH,
    )
    try:
        await protocol.send_command(commands.pileup(False))
        data = await protocol.send_acquire(command, expected_bytes=expected)
        stack = await asyncio.to_thread(
            decode_intensity,
            data,
            bit_depth=_DCR_BIT_DEPTH,
            rows=rows,
            im_width=_DCR_ROI_WIDTH,
            iterations=1,
            pileup=False,
        )
    except (NotConnectedError, ProtocolError) as exc:
        return {"status": "error", "message": str(exc)}
    except ValueError as exc:
        return {"status": "error", "message": f"DCR decode failed: {exc}"}

    return _dcr_curve(stack[0].reshape(-1))
