"""Acquisition endpoints.

The intensity endpoint validates parameters, then hands off to the background
:class:`AcquisitionRunner`. Short acquisitions return their full result
(`done` + preview + host_path); long ones return `running` and finish in the
background. Full decoding/preview/save live in the runner and services.
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict

from bridge.core.acquisition import AcquisitionRunner, IntensityParams
from bridge.core.instrument import InstrumentState, InstrumentStatus
from bridge.protocol.client import ProtocolClient
from bridge.protocol.decoder import INT_BIT_DEPTHS, ROI_WIDTHS_512, ROI_WIDTHS_1024

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
    timeout_s: float | None = None

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
    runner: AcquisitionRunner = request.app.state.runner

    if not protocol.connected:
        return {"status": "error", "message": "vendor disconnected"}

    sensor_size = protocol.system_info["sensor_size"] if protocol.system_info else 512
    valid_widths = ROI_WIDTHS_1024 if sensor_size == 1024 else ROI_WIDTHS_512
    if params.bit_depth not in INT_BIT_DEPTHS:
        return {"status": "error", "message": f"invalid bit_depth {params.bit_depth}"}
    if params.roi_width not in valid_widths:
        return {"status": "error", "message": f"invalid roi_width {params.roi_width}"}
    if params.iterations < 1:
        return {"status": "error", "message": "iterations must be >= 1"}

    return await runner.run_intensity(
        IntensityParams(
            bit_depth=params.bit_depth,
            integration_time=params.resolved_integration_time,
            iterations=params.iterations,
            roi_width=params.roi_width,
            overlap=params.overlap,
            pileup_correction=params.pileup_correction,
            timeout_s=params.timeout_s,
        )
    )
