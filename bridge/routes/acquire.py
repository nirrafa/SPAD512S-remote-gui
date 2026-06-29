"""Acquisition endpoints.

The intensity endpoint validates parameters, then hands off to the background
:class:`AcquisitionRunner`. Short acquisitions return their full result
(`done` + preview + host_path); long ones return `running` and finish in the
background. Full decoding/preview/save live in the runner and services.
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from bridge.core.acquisition import AcquisitionRunner, GatedParams, IntensityParams
from bridge.core.instrument import InstrumentState, InstrumentStatus
from bridge.protocol import commands
from bridge.protocol.client import NotConnectedError, ProtocolClient, ProtocolError
from bridge.protocol.decoder import (
    GATED_BIT_DEPTHS,
    INT_BIT_DEPTHS,
    ROI_WIDTHS_512,
    ROI_WIDTHS_1024,
    OptimalGated,
    parse_optimal_gated,
)
from bridge.services.flim import process_flim

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


class Raw1BitRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    integration_time_us: float = 100.0
    iterations: int = 1
    roi_width: int = 512
    overlap: bool = False
    timeout_s: float | None = None


@router.post("/raw-1bit")
async def acquire_raw_1bit(request: Request, params: Raw1BitRequest) -> dict[str, object]:
    protocol: ProtocolClient = request.app.state.protocol
    runner: AcquisitionRunner = request.app.state.runner

    if not protocol.connected:
        return {"status": "error", "message": "vendor disconnected"}

    sensor_size = protocol.system_info["sensor_size"] if protocol.system_info else 512
    valid_widths = ROI_WIDTHS_1024 if sensor_size == 1024 else ROI_WIDTHS_512
    if params.roi_width not in valid_widths:
        return {"status": "error", "message": f"invalid roi_width {params.roi_width}"}
    if params.iterations < 1:
        return {"status": "error", "message": "iterations must be >= 1"}

    result = await runner.run_intensity(
        IntensityParams(
            bit_depth=1,
            integration_time=params.integration_time_us,
            iterations=params.iterations,
            roi_width=params.roi_width,
            overlap=params.overlap,
            pileup_correction=False,
            timeout_s=params.timeout_s,
        )
    )
    result["decode_method"] = "binary_unpack"
    result["bit_depth"] = 1
    return result


class GatedRequest(BaseModel):
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

    @property
    def resolved_integration_time(self) -> float:
        if self.integration_time_ms is not None:
            return self.integration_time_ms
        if self.integration_time is not None:
            return self.integration_time
        return 100.0


@router.get("/gated/optimal-params")
async def gated_optimal_params(
    request: Request, gate_step_size: float = 18.0, gate_width: int = 5
) -> OptimalGated:
    protocol: ProtocolClient = request.app.state.protocol
    try:
        text = await protocol.send_command(
            commands.optimal_gated_params(gate_step_size=gate_step_size, gate_width=gate_width)
        )
    except NotConnectedError as exc:
        raise HTTPException(status_code=503, detail="vendor disconnected") from exc
    except ProtocolError as exc:
        raise HTTPException(status_code=502, detail=f"vendor error: {exc}") from exc
    return parse_optimal_gated(text)


@router.post("/gated")
async def acquire_gated(request: Request, params: GatedRequest) -> dict[str, object]:
    protocol: ProtocolClient = request.app.state.protocol
    runner: AcquisitionRunner = request.app.state.runner

    if not protocol.connected:
        return {"status": "error", "message": "vendor disconnected"}
    if params.bit_depth not in GATED_BIT_DEPTHS:
        return {"status": "error", "message": f"invalid gated bit_depth {params.bit_depth}"}
    if params.gate_direction not in ("forward", "reverse"):
        return {"status": "error", "message": f"invalid gate_direction {params.gate_direction}"}
    if params.gate_trigger_source not in ("internal", "external"):
        return {"status": "error", "message": f"invalid trigger {params.gate_trigger_source}"}

    return await runner.run_gated(
        GatedParams(
            bit_depth=params.bit_depth,
            integration_time=params.resolved_integration_time,
            iterations=params.iterations,
            gate_steps=params.gate_steps,
            gate_step_size=params.gate_step_size_ps,
            gate_offset=params.gate_offset,
            gate_width=params.gate_width,
            gate_direction=params.gate_direction,
            gate_trigger_source=params.gate_trigger_source,
            overlap=params.overlap,
            stream=params.stream,
            pileup_correction=params.pileup_correction,
            arbitrary_steps=params.arbitrary_steps,
        )
    )


class FLIMRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    calibration_type: str = "mono_exponential"
    expected_tau_ns: float | list[float] = 4.0
    gate_width: str = "medium"
    integration_time_ms: float = 200.0
    gate_subsampling: int = 1
    output_format: str = "image"


@router.post("/flim")
async def acquire_flim(request: Request, params: FLIMRequest) -> dict[str, object]:
    protocol: ProtocolClient = request.app.state.protocol
    instrument: InstrumentState = request.app.state.instrument

    if not protocol.connected:
        return {"status": "error", "message": "vendor disconnected"}
    if instrument.is_busy:
        return {"status": "error", "message": "instrument busy"}

    sensor = protocol.system_info["sensor_size"] if protocol.system_info else 512

    await instrument.set(InstrumentStatus.ACQUIRING)
    result: dict[str, object]
    try:
        text = await protocol.send_command(
            commands.flim_acquire(
                integration_time=params.integration_time_ms,
                subsampling=max(params.gate_subsampling, 1),
                raw=True,
            )
        )
        result = await asyncio.to_thread(
            process_flim, text, rows=sensor, cols=sensor, output_format=params.output_format
        )
    except (NotConnectedError, ProtocolError) as exc:
        result = {"status": "error", "message": str(exc)}
    finally:
        await instrument.set(InstrumentStatus.IDLE)

    if result.get("status") == "done" and not getattr(
        request.app.state, "flim_irf_calibrated", False
    ):
        result["warning"] = "FLIM IRF not calibrated"
    return result
