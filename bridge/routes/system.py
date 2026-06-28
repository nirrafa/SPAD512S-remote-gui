"""System info and trigger diagnostics endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from bridge.protocol import commands
from bridge.protocol.client import NotConnectedError, ProtocolClient, ProtocolError
from bridge.protocol.decoder import SystemInfo, TriggerInfo, parse_readout

router = APIRouter(prefix="/api/system")


@router.get("/info")
async def system_info(request: Request) -> SystemInfo:
    protocol: ProtocolClient = request.app.state.protocol
    if protocol.system_info is None:
        raise HTTPException(status_code=503, detail="vendor disconnected")
    return protocol.system_info


@router.get("/triggers")
async def triggers(request: Request) -> TriggerInfo:
    protocol: ProtocolClient = request.app.state.protocol
    try:
        text = await protocol.send_command(commands.readout())
    except NotConnectedError as exc:
        raise HTTPException(status_code=503, detail="vendor disconnected") from exc
    except ProtocolError as exc:
        raise HTTPException(status_code=502, detail=f"vendor error: {exc}") from exc
    return parse_readout(text)
