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

from bridge.core.calibration_state import CalibrationStore
from bridge.core.instrument import InstrumentState, InstrumentStatus
from bridge.protocol import commands
from bridge.protocol.client import NotConnectedError, ProtocolClient, ProtocolError
from bridge.protocol.decoder import bytes_per_frame, decode_intensity

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
