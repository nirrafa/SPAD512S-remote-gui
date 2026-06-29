"""Calibration endpoints.

Phase 5 covers FLIM IRF calibration; Phase 7 extends this with noise / dead-pixel
/ master-slave-offset flows and a persistent calibration store. For now an
``app.state.flim_irf_calibrated`` flag tracks whether a FLIM acquisition should
warn about a missing IRF.
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict

from bridge.core.instrument import InstrumentState, InstrumentStatus
from bridge.protocol import commands
from bridge.protocol.client import NotConnectedError, ProtocolClient, ProtocolError

router = APIRouter(prefix="/api/calibrate")

_GATE_WIDTH_CODE = {"short": 0, "medium": 1, "long": 2}
_CALIBRATION_MODE = {"mono_exponential": 0, "bi_exponential": 1}


class FlimIrfRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    calibration_type: str = "mono_exponential"
    expected_tau_ns: float | list[float] = 4.0
    gate_width: str = "medium"


@router.post("/flim-irf")
async def calibrate_flim_irf(request: Request, params: FlimIrfRequest) -> dict[str, object]:
    protocol: ProtocolClient = request.app.state.protocol
    instrument: InstrumentState = request.app.state.instrument

    if not protocol.connected:
        return {"status": "error", "message": "vendor disconnected"}

    mode = _CALIBRATION_MODE.get(params.calibration_type, 0)
    gate_width = _GATE_WIDTH_CODE.get(params.gate_width, 1)
    tau = params.expected_tau_ns
    tau_value = sum(tau) / len(tau) if isinstance(tau, list) and tau else float(tau)  # type: ignore[arg-type]

    await instrument.set(InstrumentStatus.CALIBRATING)
    try:
        await protocol.send_command(
            commands.flim_calibrate(mode=mode, expected_tau_ns=tau_value, gate_width=gate_width)
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
