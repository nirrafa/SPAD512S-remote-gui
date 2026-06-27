"""Acquisition endpoints.

Phase 2 provides the connection-guarded skeleton: a safe-boundary stop and a
minimal intensity acquisition that exercises the protocol client end to end.
Full parameter validation, decoding, preview and saving arrive in Phase 3.
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict

from bridge.core.instrument import InstrumentState, InstrumentStatus
from bridge.protocol import commands
from bridge.protocol.client import NotConnectedError, ProtocolClient, ProtocolError
from bridge.protocol.decoder import (
    INT_BIT_DEPTHS,
    ROI_WIDTHS_512,
    ROI_WIDTHS_1024,
    bytes_per_frame,
)

router = APIRouter(prefix="/api/acquire")


class IntensityRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    bit_depth: int = 8
    integration_time: float | None = None
    integration_time_ms: float | None = None
    iterations: int = 1
    roi_width: int = 512
    overlap: bool = False
    pileup_correction: bool = False

    @property
    def resolved_integration_time(self) -> float:
        if self.integration_time is not None:
            return self.integration_time
        if self.integration_time_ms is not None:
            return self.integration_time_ms
        return 100.0


@router.post("/stop")
async def stop(request: Request) -> dict[str, object]:
    instrument: InstrumentState = request.app.state.instrument
    await instrument.request_stop()
    await instrument.set(InstrumentStatus.IDLE)
    return {"status": "stopped", "instrument_state": instrument.status.value}


@router.post("/intensity")
async def acquire_intensity(request: Request, params: IntensityRequest) -> dict[str, object]:
    protocol: ProtocolClient = request.app.state.protocol
    instrument: InstrumentState = request.app.state.instrument

    if not protocol.connected:
        return {"status": "error", "message": "vendor disconnected"}
    if instrument.is_busy:
        return {"status": "busy", "message": "instrument busy"}

    sensor_size = protocol.system_info["sensor_size"] if protocol.system_info else 512
    valid_widths = ROI_WIDTHS_1024 if sensor_size == 1024 else ROI_WIDTHS_512
    if params.bit_depth not in INT_BIT_DEPTHS:
        return {"status": "error", "message": f"invalid bit_depth {params.bit_depth}"}
    if params.roi_width not in valid_widths:
        return {"status": "error", "message": f"invalid roi_width {params.roi_width}"}
    if params.iterations < 1:
        return {"status": "error", "message": "iterations must be >= 1"}

    rows = sensor_size
    expected = params.iterations * bytes_per_frame(
        params.bit_depth, rows, params.roi_width, params.pileup_correction
    )
    command = commands.intensity(
        bit_depth=params.bit_depth,
        integration_time=params.resolved_integration_time,
        iterations=params.iterations,
        overlap=params.overlap,
        im_width=params.roi_width,
    )

    await instrument.set(InstrumentStatus.ACQUIRING)
    try:
        await protocol.send_command(commands.pileup(params.pileup_correction))
        data = await protocol.send_acquire(command, expected_bytes=expected)
    except NotConnectedError:
        return {"status": "error", "message": "vendor disconnected"}
    except ProtocolError as exc:
        return {"status": "error", "message": str(exc)}
    finally:
        await instrument.set(InstrumentStatus.IDLE)

    return {"status": "done", "bytes": len(data), "frames": params.iterations}
