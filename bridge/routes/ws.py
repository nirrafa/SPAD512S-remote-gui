"""WebSocket endpoint for live state/progress/preview/alarm updates."""
from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from bridge.core.ws_hub import WebSocketHub

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    # No initial frame is pushed on connect: clients fetch a snapshot via
    # GET /api/status and then receive event-driven state/busy/progress/preview
    # frames, so the first frame after an acquire is the `busy` one.
    hub: WebSocketHub = websocket.app.state.hub
    await hub.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        hub.disconnect(websocket)
