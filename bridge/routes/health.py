"""Health, status, and safety endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from bridge import __version__
from bridge.core.instrument import InstrumentState
from bridge.protocol import commands
from bridge.protocol.client import NotConnectedError, ProtocolClient, ProtocolError
from bridge.services.health import HealthMonitor

router = APIRouter(prefix="/api")
settings_router = APIRouter(prefix="/api/settings")

# Absolute Vex guardrail: even with explicit confirmation, never command a bias
# above this. The real per-chip breakdown-derived ceiling is a Phase 13 item.
VEX_HARD_CEILING = 50.0


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

    poll_interval_s: float | None = Field(default=None, ge=0.1, le=60.0)
    temp_threshold_chip: float | None = Field(default=None, ge=-50.0, le=200.0)
    vex_max: float | None = Field(default=None, ge=0.0, le=VEX_HARD_CEILING)
    expected_laser_hz: float | None = Field(default=None, gt=0.0)
    laser_tolerance: float | None = Field(default=None, ge=0.0, le=1.0)
    missing_laser_hz: float | None = Field(default=None, ge=0.0)


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

    if body.vex > VEX_HARD_CEILING:
        return {
            "status": "error",
            "message": f"Vex {body.vex} exceeds the {VEX_HARD_CEILING} V safety ceiling",
        }
    if body.vex > monitor.config.vex_max and not body.confirm:
        return {"requires_confirmation": True, "vex_max": monitor.config.vex_max}

    try:
        await protocol.send_command(commands.set_vex(body.vex))
    except (NotConnectedError, ProtocolError) as exc:
        return {"status": "error", "message": str(exc)}
    return {"status": "ok", "vex": body.vex}
