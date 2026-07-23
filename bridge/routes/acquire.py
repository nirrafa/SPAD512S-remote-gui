"""Acquisition endpoints.

The intensity endpoint validates parameters, then hands off to the background
:class:`AcquisitionRunner`. Short acquisitions return their full result
(`done` + preview + host_path); long ones return `running` and finish in the
background. Full decoding/preview/save live in the runner and services.
"""
from __future__ import annotations

import asyncio
import contextlib
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

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
from bridge.services.experiment_log import ExperimentLog
from bridge.services.flim import process_flim
from bridge.services.scheduler import Scheduler
from bridge.services.sweep import SweepRunner

router = APIRouter(prefix="/api/acquire")


def _record_acquisition(
    request: Request, *, mode: str, params_model: BaseModel, result: dict[str, object]
) -> None:
    """Auto-log a completed single-shot acquisition to the experiment log.

    Only fully-finished runs (``done``/``aborted``) are recorded — long async
    runs that return ``running`` have no result path yet.
    """
    if result.get("status") not in ("done", "aborted"):
        return
    log: ExperimentLog = request.app.state.experiment_log
    runner: AcquisitionRunner = request.app.state.runner
    ctx = runner.acquisition_context()
    logged_params: dict[str, object] = dict(params_model.model_dump(exclude_none=True))
    if result.get("dark_corrected"):
        # Record the applied correction with a pointer to the reference file,
        # so the log entry alone documents how the derived views were produced.
        logged_params["dark_corrected"] = True
        logged_params["dark_reference_id"] = result.get("dark_reference_id")
        logged_params["dark_reference_npy_path"] = result.get("dark_reference_path")
    log.log_acquisition(
        mode=mode,
        params=logged_params,
        result_path=result.get("host_path"),  # type: ignore[arg-type]
        calibration_state=ctx["calibration_state"],
        temperatures=ctx["temperatures"],
        sample_name=getattr(params_model, "sample_name", None),
        experiment_name=getattr(params_model, "experiment_name", None),
        notes=getattr(params_model, "notes", None),
    )

# /api/acquire/status briefly waits for the next batch boundary so a freshly
# tripped auto-protect threshold is reflected (the abort fires at the boundary,
# not mid-batch). Bounded so a healthy long acquisition still returns promptly.
STATUS_SETTLE_TRIES = 8
STATUS_SETTLE_S = 0.03

# A stop waits for the in-flight batch/sweep-point to finish at a safe boundary
# so the vendor protocol is left uncorrupted (no interleaved acquire). Bounded so
# the endpoint always returns.
STOP_WAIT_S = 20.0


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
    sample_name: str | None = None
    experiment_name: str | None = None
    notes: str | None = None
    run_reducer: bool = False
    dark_reference_id: str | None = None

    @property
    def resolved_integration_time(self) -> float:
        if self.integration_time is not None:
            return self.integration_time
        if self.integration_time_ms is not None:
            return self.integration_time_ms
        return 100.0


@router.post("/stop")
async def stop(request: Request) -> dict[str, object]:
    """Request a safe-boundary stop.

    The in-flight frame/batch (and, for a sweep, the current point) always
    finishes; the stop takes effect at the next boundary, leaving the vendor
    protocol uncorrupted and the hardware idle. We wait for the current
    operation to settle so a subsequent acquire is not rejected as busy and does
    not interleave on the single TCP socket.
    """
    instrument: InstrumentState = request.app.state.instrument
    runner: AcquisitionRunner = request.app.state.runner
    sweep: SweepRunner = request.app.state.sweep
    acq_queue = request.app.state.queue

    was_sweep = sweep.active
    if acq_queue.active:
        # The instrument flag is cleared whenever an item returns to idle, so
        # the queue keeps its own stop latch (remaining items are skipped).
        acq_queue.request_stop()
    await instrument.request_stop()

    task = (runner.current or {}).get("task")
    if task is not None and not task.done():
        with contextlib.suppress(Exception):
            await asyncio.wait_for(asyncio.shield(task), STOP_WAIT_S)
    # Give the sweep/queue loops time to notice the stop at their next
    # item/point boundary.
    deadline = STOP_WAIT_S
    while (sweep.active or acq_queue.active) and deadline > 0:
        await asyncio.sleep(STATUS_SETTLE_S)
        deadline -= STATUS_SETTLE_S

    if instrument.is_busy:
        await instrument.set(InstrumentStatus.IDLE)

    boundary = "between_sweep_points" if was_sweep else "between_iterations"
    return {
        "status": "stopping",
        "stop_boundary": boundary,
        "in_flight_completed": True,
        "instrument_state": instrument.status.value,
    }


@router.get("/status")
async def acquire_status(request: Request) -> dict[str, object]:
    instrument: InstrumentState = request.app.state.instrument
    runner: AcquisitionRunner = request.app.state.runner
    sweep: SweepRunner = request.app.state.sweep

    # During a batched acquisition the socket is busy mid-batch, so an
    # auto-protect stop may be one batch boundary away. Briefly let the runner
    # reach its next boundary (poll + stop check) so the reported state reflects
    # a just-tripped threshold rather than the instant before it.
    if instrument.is_busy and not instrument.stop_requested:
        for _ in range(STATUS_SETTLE_TRIES):
            await asyncio.sleep(STATUS_SETTLE_S)
            if instrument.stop_requested or not instrument.is_busy:
                break

    last_result = (runner.current or {}).get("result") or {}
    abort_reason = instrument.abort_reason or last_result.get("abort_reason")
    running = instrument.is_busy or sweep.active

    if instrument.stop_requested or instrument.status is InstrumentStatus.STOPPING:
        state = "stopping"
    elif running:
        state = "running"
    else:
        raw = str(last_result.get("status") or "idle")
        state = "completed" if raw == "done" else raw

    return {
        "state": state,
        "running": running,
        "abort_reason": abort_reason,
        "instrument_state": instrument.status.value,
    }


class SweepRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    mode: str = "intensity"
    sweep_parameter: str | None = None
    values: list[Any] | None = None
    sweep_parameters: dict[str, list[Any]] | None = None
    base_params: dict[str, Any] = {}


@router.post("/sweep")
async def acquire_sweep(request: Request, params: SweepRequest) -> dict[str, object]:
    protocol: ProtocolClient = request.app.state.protocol
    sweep: SweepRunner = request.app.state.sweep

    if not protocol.connected:
        return {"status": "error", "message": "vendor disconnected"}
    if params.sweep_parameters is None and (
        params.sweep_parameter is None or params.values is None
    ):
        return {
            "status": "error",
            "message": "provide sweep_parameter+values or sweep_parameters",
        }

    return await sweep.start(
        mode=params.mode,
        base_params=params.base_params,
        sweep_parameter=params.sweep_parameter,
        values=params.values,
        sweep_parameters=params.sweep_parameters,
    )


@router.post("/sweep/resume")
async def resume_sweep(request: Request) -> dict[str, object]:
    protocol: ProtocolClient = request.app.state.protocol
    sweep: SweepRunner = request.app.state.sweep

    if not protocol.connected:
        return {"status": "error", "message": "vendor disconnected"}
    return await sweep.resume()


class ScheduleRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    mode: str = "intensity"
    params: dict[str, Any] = {}
    start_time: str


@router.post("/schedule")
async def schedule_job(request: Request, body: ScheduleRequest) -> dict[str, object]:
    scheduler: Scheduler = request.app.state.scheduler
    job = scheduler.schedule(mode=body.mode, params=body.params, start_time=body.start_time)
    return {"status": "scheduled", "job_id": job.job_id, "start_time": job.start_time}


@router.get("/schedule/{job_id}")
async def schedule_status(request: Request, job_id: str) -> dict[str, object]:
    scheduler: Scheduler = request.app.state.scheduler
    job = scheduler.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job.payload()


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

    result = await runner.run_intensity(
        IntensityParams(
            bit_depth=params.bit_depth,
            integration_time=params.resolved_integration_time,
            iterations=params.iterations,
            roi_width=params.roi_width,
            overlap=params.overlap,
            pileup_correction=params.pileup_correction,
            timeout_s=params.timeout_s,
            sample_name=params.sample_name,
            experiment_name=params.experiment_name,
            notes=params.notes,
            run_reducer=params.run_reducer,
            dark_reference_id=params.dark_reference_id,
        )
    )

    store = request.app.state.calibration
    calibration_valid = store.is_valid("noise") and store.is_valid("dead_pixel")
    result["calibration_valid"] = calibration_valid
    if not calibration_valid:
        result["warning"] = "Noise / dead-pixel calibration missing or stale."
    _record_acquisition(request, mode="intensity", params_model=params, result=result)
    return result


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
    _record_acquisition(request, mode="raw1bit", params_model=params, result=result)
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
    sample_name: str | None = None
    experiment_name: str | None = None
    notes: str | None = None
    run_reducer: bool = False
    dark_reference_id: str | None = None
    cooloff_s: float = Field(default=0.0, ge=0.0, le=600.0)

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

    result = await runner.run_gated(
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
            sample_name=params.sample_name,
            experiment_name=params.experiment_name,
            notes=params.notes,
            run_reducer=params.run_reducer,
            dark_reference_id=params.dark_reference_id,
            cooloff_s=params.cooloff_s,
        )
    )
    _record_acquisition(request, mode="gated", params_model=params, result=result)
    return result


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
    except ValueError as exc:
        result = {"status": "error", "message": f"FLIM decode failed: {exc}"}
    finally:
        await instrument.set(InstrumentStatus.IDLE)

    if result.get("status") == "done" and not getattr(
        request.app.state, "flim_irf_calibrated", False
    ):
        result["warning"] = "FLIM IRF not calibrated"
    _record_acquisition(request, mode="flim", params_model=params, result=result)
    return result
