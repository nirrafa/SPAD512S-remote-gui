"""WebSocket endpoint for live state/progress/preview/alarm updates."""
from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from bridge.core.instrument import InstrumentState
from bridge.core.ws_hub import WebSocketHub
from bridge.protocol.client import ProtocolClient

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    hub: WebSocketHub = websocket.app.state.hub
    protocol: ProtocolClient = websocket.app.state.protocol
    instrument: InstrumentState = websocket.app.state.instrument

    await hub.connect(websocket)
    await websocket.send_json(
        {
            "type": "state",
            "data": {
                "vendor_connected": protocol.connected,
                "instrument_state": instrument.status.value,
            },
        }
    )
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        hub.disconnect(websocket)
