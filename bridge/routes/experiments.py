"""Experiment log + preset endpoints (PRD §8 — reproducibility).

The log records every acquisition; presets store reusable parameter sets per
mode; re-run replays a past entry through the acquisition runner (optionally
with parameter overrides). Backed by :class:`ExperimentLog` (SQLite).
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from bridge.core.acquisition import AcquisitionRunner
from bridge.protocol.client import ProtocolClient
from bridge.services.experiment_log import ExperimentLog
from bridge.services.sweep import _gated_params, _intensity_params

router = APIRouter(prefix="/api")


@router.get("/experiment-log")
async def experiment_log(
    request: Request,
    search: str | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> dict[str, object]:
    log: ExperimentLog = request.app.state.experiment_log
    return {"entries": log.entries(search=search, limit=limit, offset=offset)}


class RerunRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    overrides: dict[str, Any] = {}


@router.post("/experiment-log/{entry_id}/rerun")
async def rerun_entry(
    request: Request, entry_id: str, body: RerunRequest | None = None
) -> dict[str, object]:
    log: ExperimentLog = request.app.state.experiment_log
    runner: AcquisitionRunner = request.app.state.runner
    protocol: ProtocolClient = request.app.state.protocol

    entry = log.get(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="log entry not found")
    if not protocol.connected:
        return {"status": "error", "message": "vendor disconnected"}

    overrides = body.overrides if body else {}
    params = {**entry["params"], **overrides}
    mode = entry["mode"]

    if mode == "gated":
        result = await runner.run_gated(_gated_params(params))
    else:
        result = await runner.run_intensity(_intensity_params(params))

    ctx = runner.acquisition_context()
    log.log_acquisition(
        mode=mode,
        params=params,
        result_path=result.get("host_path"),
        calibration_state=ctx["calibration_state"],
        temperatures=ctx["temperatures"],
        sample_name=params.get("sample_name"),
        experiment_name=params.get("experiment_name"),
        notes=params.get("notes"),
    )
    return result


class PresetRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    mode: str
    params: dict[str, Any] = {}


@router.post("/presets")
async def save_preset(request: Request, body: PresetRequest) -> dict[str, object]:
    log: ExperimentLog = request.app.state.experiment_log
    preset_id = log.save_preset(name=body.name, mode=body.mode, params=body.params)
    return {"status": "ok", "preset_id": preset_id}


@router.get("/presets")
async def list_presets(request: Request, mode: str | None = None) -> list[dict[str, Any]]:
    log: ExperimentLog = request.app.state.experiment_log
    return log.list_presets(mode)


@router.get("/presets/{preset_id}")
async def get_preset(request: Request, preset_id: str) -> dict[str, Any]:
    log: ExperimentLog = request.app.state.experiment_log
    preset = log.get_preset(preset_id)
    if preset is None:
        raise HTTPException(status_code=404, detail="preset not found")
    return preset


@router.delete("/presets/{preset_id}")
async def delete_preset(request: Request, preset_id: str) -> dict[str, object]:
    log: ExperimentLog = request.app.state.experiment_log
    if not log.delete_preset(preset_id):
        raise HTTPException(status_code=404, detail="preset not found")
    return {"status": "ok"}
