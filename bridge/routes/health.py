"""Health, status, and safety endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict

from bridge import __version__
from bridge.core.instrument import InstrumentState
from bridge.protocol import commands
from bridge.protocol.client import NotConnectedError, ProtocolClient, ProtocolError
from bridge.services.health import HealthMonitor

router = APIRouter(prefix="/api")
settings_router = APIRouter(prefix="/api/settings")


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@router.get("/status")
async def status(request: Request) -> dict[str, object]:
    protocol: ProtocolClient = request.app.state.protocol
    instrument: InstrumentState = request.app.state.instrument
    return {
        "vendor_connected": protocol.connected,
        "instrument_state": instrument.status.value,
    }


@router.get("/health/readings")
async def health_readings(request: Request) -> dict[str, object]:
    monitor: HealthMonitor = request.app.state.health
    await monitor.poll()
    return monitor.readings_payload()


@router.get("/health/config")
async def health_config(request: Request) -> dict[str, float]:
    monitor: HealthMonitor = request.app.state.health
    return monitor.config_payload()


class HealthConfigUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    poll_interval_s: float | None = None
    temp_threshold_chip: float | None = None
    vex_max: float | None = None
    expected_laser_hz: float | None = None
    laser_tolerance: float | None = None


@router.put("/health/config")
async def update_health_config(
    request: Request, update: HealthConfigUpdate
) -> dict[str, str]:
    monitor: HealthMonitor = request.app.state.health
    monitor.update_config(**update.model_dump(exclude_none=True))
    return {"status": "ok"}


class VexRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    vex: float
    confirm: bool = False


@settings_router.post("/vex")
async def set_vex(request: Request, body: VexRequest) -> dict[str, object]:
    monitor: HealthMonitor = request.app.state.health
    protocol: ProtocolClient = request.app.state.protocol

    if body.vex > monitor.config.vex_max and not body.confirm:
        return {"requires_confirmation": True, "vex_max": monitor.config.vex_max}

    try:
        await protocol.send_command(commands.set_vex(body.vex))
    except (NotConnectedError, ProtocolError) as exc:
        return {"status": "error", "message": str(exc)}
    return {"status": "ok", "vex": body.vex}
