"""On-demand live view.

A spartan focus/alignment aid for hosts that can't run the vendor's own GUI
(e.g. macOS): a single quick, unpersisted intensity frame per request. Nothing
is written to disk or logged — see :meth:`AcquisitionRunner.capture_live_frame`.
The client decides the cadence (a single click, or a poll loop while a "live"
toggle is on); the bridge holds the single vendor socket only for the
duration of each request, never continuously.
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict

from bridge.core.acquisition import AcquisitionRunner, IntensityParams
from bridge.protocol.client import ProtocolClient
from bridge.protocol.decoder import INT_BIT_DEPTHS, ROI_WIDTHS_512, ROI_WIDTHS_1024

router = APIRouter(prefix="/api/live")

# Short default integration time keeps each frame responsive; iterations is
# always 1 (a live-view frame is never averaged/multi-shot).
DEFAULT_INTEGRATION_TIME_MS = 20.0
LIVE_TIMEOUT_S = 5.0


class LiveFrameRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    bit_depth: int = 8
    integration_time: float = DEFAULT_INTEGRATION_TIME_MS
    roi_width: int = 512


@router.post("/frame")
async def live_frame(request: Request, params: LiveFrameRequest) -> dict[str, object]:
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

    return await runner.capture_live_frame(
        IntensityParams(
            bit_depth=params.bit_depth,
            integration_time=params.integration_time,
            iterations=1,
            roi_width=params.roi_width,
            overlap=False,
            pileup_correction=False,
            timeout_s=LIVE_TIMEOUT_S,
        )
    )
