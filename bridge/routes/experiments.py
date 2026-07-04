"""Experiment log endpoints.

Phase 9 ships the minimal read endpoint so scheduled jobs are visible. Phase 12
expands this into the full log + preset CRUD backed by SQLite.
"""
from __future__ import annotations

from fastapi import APIRouter, Request

from bridge.services.experiment_log import ExperimentLog

router = APIRouter(prefix="/api")


@router.get("/experiment-log")
async def experiment_log(request: Request) -> dict[str, object]:
    log: ExperimentLog = request.app.state.experiment_log
    return {"entries": log.entries()}
