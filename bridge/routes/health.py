"""Health and status endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Request

from bridge import __version__
from bridge.core.instrument import InstrumentState
from bridge.protocol.client import ProtocolClient

router = APIRouter(prefix="/api")


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
